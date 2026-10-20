"""Single-process, durable execution worker for the Java business backend.

Run with ``python -m paper_agent.interfaces.worker``. This service deliberately
has no browser authentication, CORS, user database, or personal model settings.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from paper_agent.core.models import Paper, ResearchReport, ResearchStageEvent
from paper_agent.core.errors import PublicResearchError
from paper_agent.core.study import StudyReport
from paper_agent.services.research import ResearchOptions, ResearchService
from paper_agent.services.study import StudyService
from paper_agent.services.paper_search import search_papers, search_paper_page
from paper_agent.tools.search import SearchError, SearchTimeout, SearchRateLimit
from paper_agent.services.model_runtime import (RuntimeCredentials, ModelProbe,
    require_personal_credentials, probe_model, probe_error_message, close_runtime_credentials)

MAX_BODY = 2 * 1024 * 1024
MAX_PENDING = 16
CONCURRENCY = 2


class WorkerOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    mode: Literal['demo', 'live']
    rag: Literal['none', 'abstract'] = 'abstract'
    provider: Literal['qwen', 'openai'] = 'qwen'
    model: str | None = Field(default=None, min_length=1, max_length=128)
    credential_source: Literal['server', 'personal'] = 'server'


class WorkerPaper(Paper):
    model_config = ConfigDict(extra='forbid', strict=True)
    paper_id: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=1024)
    abstract: str = Field(max_length=10000)
    authors: list[str] = Field(max_length=50)
    categories: list[str] = Field(default_factory=list, max_length=50)
    published: str | None = Field(default=None, max_length=128)
    page_url: str = Field(max_length=2048)
    pdf_url: str | None = Field(default=None, max_length=2048)

    @field_validator('authors', 'categories')
    @classmethod
    def bounded_metadata(cls, value):
        if any(len(item) > 128 for item in value):
            raise ValueError('Metadata item is too long')
        return value


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    contract_version: Literal[1]
    topic: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=3, ge=1, le=20)
    options: WorkerOptions
    papers: list[WorkerPaper] | None = Field(default=None, min_length=1, max_length=20)
    task_type: Literal['research', 'study_report'] = 'research'
    index_namespace: str | None = Field(default=None, min_length=1, max_length=128,
                                        pattern=r'^[A-Za-z0-9:_-]+$')
    rebuild_index: bool = False
    runtime_credentials: RuntimeCredentials | None = Field(default=None, exclude=True, repr=False)
    learning_goal: str = Field(default='', max_length=4000)
    reflection: str = Field(default='', max_length=50000)
    collection_note: str = Field(default='', max_length=50000)
    notes: dict[str, str] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def study_inputs(self):
        if any(len(key) > 255 or len(value) > 50000 for key, value in self.notes.items()):
            raise ValueError('Study notes exceed limits')
        if self.task_type == 'study_report':
            if not self.papers or self.options.mode != 'live':
                raise ValueError('Study reports require selected papers and live mode')
            if not set(self.notes).issubset({p.paper_id for p in self.papers}):
                raise ValueError('Study notes must belong to selected papers')
        return self

    @field_validator('topic')
    @classmethod
    def topic_not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Topic is required')
        return value

    @field_validator('papers')
    @classmethod
    def distinct_paper_ids(cls, value):
        if value is not None and len({p.paper_id for p in value}) != len(value):
            raise ValueError('Paper identifiers must be distinct')
        return value


class Ledger:
    """SQLite is the source of truth; the OS lock prevents competing executors."""

    def __init__(self, path: Path):
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = path.with_suffix(path.suffix + '.lock').open('a+b')
        try:
            self.lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                if self.lock.read(1) == b'':
                    self.lock.write(b'0')
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lock.close()
            raise RuntimeError('Worker ledger is already in use') from exc
        try:
            self.db = sqlite3.connect(path)
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('''CREATE TABLE IF NOT EXISTS worker_tasks (
                task_id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL, events TEXT NOT NULL DEFAULT '[]', report TEXT,
                error_code TEXT, error_message TEXT)''')
            self.interrupt()
        except BaseException:
            self.lock.close()
            raise

    def interrupt(self):
        with self.db:
            self.db.execute("""UPDATE worker_tasks SET status='interrupted', report=NULL,
                error_code='worker_interrupted', error_message='研究执行已中断，请创建新的任务。'
                WHERE status IN ('queued','running')""")

    def get(self, task_id):
        row = self.db.execute('SELECT * FROM worker_tasks WHERE task_id=?', (task_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Task not found')
        return row

    def snapshot(self, task_id):
        row = self.get(task_id)
        return {'contract_version': 1, 'task_id': task_id, 'status': row['status'],
                'events': json.loads(row['events']),
                'report': json.loads(row['report']) if row['status'] == 'completed' else None,
                'error_code': row['error_code'], 'error_message': row['error_message']}

    def close(self):
        self.db.close()
        self.lock.close()


def create_app(db_path: str | Path | None = None, service_token: str | None = None,
               service_factory=None, search_factory=None, study_factory=None, model_tester=None) -> FastAPI:
    token = service_token if service_token is not None else os.getenv('PAPERFLOW_SERVICE_TOKEN', '')
    if len(token.strip()) < 32:
        raise ValueError('PAPERFLOW_SERVICE_TOKEN must contain at least 32 characters')
    path = Path(db_path or os.getenv('PAPERFLOW_WORKER_DB', 'outputs/worker/tasks.sqlite3'))
    factory = service_factory or ResearchService

    @asynccontextmanager
    async def lifespan(app):
        ledger = Ledger(path)
        queue = asyncio.Queue(maxsize=MAX_PENDING)
        app.state.ledger = ledger
        app.state.queue = queue
        app.state.runtime_credentials = {}

        async def executor():
            while True:
                task_id = await queue.get()
                payload = None
                options = None
                try:
                    row = ledger.get(task_id)
                    payload = TaskInput.model_validate_json(row['payload'])
                    with ledger.db:
                        ledger.db.execute("UPDATE worker_tasks SET status='running' WHERE task_id=?", (task_id,))
                    events = []

                    async def on_event(event: ResearchStageEvent):
                        events.append(event.model_dump(mode='json'))
                        del events[:-200]
                        with ledger.db:
                            ledger.db.execute('UPDATE worker_tasks SET events=? WHERE task_id=?',
                                              (json.dumps(events, ensure_ascii=False), task_id))

                    options = ResearchOptions(**payload.options.model_dump(),
                        index_namespace=payload.index_namespace or f'task:{task_id}',
                        rebuild_index=payload.rebuild_index,
                        runtime_credentials=app.state.runtime_credentials.get(task_id))
                    if options.mode == 'live' and options.credential_source == 'personal':
                        require_personal_credentials(options)
                    if payload.task_type == 'study_report':
                        study = (study_factory or StudyService)(options)
                        report = await study.run(payload.topic, papers=payload.papers, on_event=on_event,
                            notes=payload.notes, learning_goal=payload.learning_goal,
                            reflection=payload.reflection, collection_note=payload.collection_note)
                        report = StudyReport.model_validate(report)
                        if (report.mode != 'live' or
                                [p.model_dump() for p in report.papers] !=
                                [p.model_dump() for p in payload.papers]):
                            raise ValueError('Study report must preserve selected paper snapshot')
                    else:
                        report = await factory(options).run(payload.topic, payload.limit,
                                                            papers=payload.papers, on_event=on_event)
                        # Validate even injected implementations before persisting a completed state.
                        report = ResearchReport.model_validate(report)
                    with ledger.db:
                        ledger.db.execute("UPDATE worker_tasks SET status='completed', report=? WHERE task_id=?",
                                          (report.model_dump_json(), task_id))
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    is_study = payload is not None and payload.task_type == 'study_report'
                    code = 'study_report_failed' if is_study else 'research_failed'
                    message = (str(exc)[:1000] if isinstance(exc, PublicResearchError)
                               else ('学习报告生成失败，请检查模型配置和 PDF 后重试。' if is_study else
                                     '研究执行失败，请检查执行端配置或稍后新建任务。'))
                    with ledger.db:
                        ledger.db.execute("""UPDATE worker_tasks SET status='failed', report=NULL,
                            error_code=?, error_message=? WHERE task_id=?""", (code, message, task_id))
                finally:
                    credentials = app.state.runtime_credentials.pop(task_id, None)
                    if options is not None:
                        options.runtime_credentials = None
                    await close_runtime_credentials(credentials)
                    credentials = None
                    queue.task_done()

        workers = [asyncio.create_task(executor()) for _ in range(CONCURRENCY)]
        try:
            yield
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            app.state.runtime_credentials.clear()
            ledger.interrupt()
            ledger.close()

    app = FastAPI(title='PaperFlow execution worker', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    async def authenticate(request: Request):
        header = request.headers.get('authorization', '')
        if not hmac.compare_digest(header.encode(), f'Bearer {token}'.encode()):
            raise HTTPException(401, 'Invalid service credentials')

    @app.middleware('http')
    async def bounded_body(request, call_next):
        # Authenticate before reading request content, including validation errors.
        try:
            await authenticate(request)
        except HTTPException:
            return JSONResponse({'detail': 'Invalid service credentials'}, status_code=401)
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY:
                return JSONResponse({'detail': 'Request is too large'}, status_code=413)
            chunks.append(chunk)
        request._body = b''.join(chunks)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({'detail': 'Invalid task request'}, status_code=422)

    @app.post('/internal/v1/tasks/{task_id}', dependencies=[Depends(authenticate)])
    async def submit(task_id: UUID, payload: TaskInput):
        task_id = str(task_id)
        ledger = app.state.ledger
        durable = payload.model_dump(mode='json')
        # Preserve hashes of pre-settings server-mode tasks on duplicate replay.
        if durable['options']['credential_source'] == 'server':
            durable['options'].pop('credential_source')
        canonical = json.dumps(durable, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        existing = ledger.db.execute('SELECT input_hash FROM worker_tasks WHERE task_id=?', (task_id,)).fetchone()
        if existing:
            if existing['input_hash'] != digest:
                raise HTTPException(409, 'Task ID already has different input')
            return JSONResponse(ledger.snapshot(task_id), status_code=200)
        if app.state.queue.full():
            raise HTTPException(503, 'Worker queue is full; retry the same task ID later')
        # No await between capacity check, durable insert and enqueue: one event loop
        # makes admission atomic and duplicate submissions never consume capacity.
        with ledger.db:
            ledger.db.execute('INSERT INTO worker_tasks(task_id,input_hash,payload,status) VALUES (?,?,?,?)',
                              (task_id, digest, canonical, 'queued'))
        if payload.runtime_credentials is not None:
            app.state.runtime_credentials[task_id] = payload.runtime_credentials
        app.state.queue.put_nowait(task_id)
        return JSONResponse(ledger.snapshot(task_id), status_code=202)

    @app.post('/internal/v1/models/test', dependencies=[Depends(authenticate)])
    async def test_model(body: ModelProbe):
        try:
            async with asyncio.timeout(15):
                await (model_tester or probe_model)(body, body.model)
        except Exception as error:
            return {'success': False, 'message': probe_error_message(error)}
        return {'success': True, 'message': '模型连接成功，已验证已保存的密钥与模型。'}

    @app.get('/internal/v1/tasks/{task_id}', dependencies=[Depends(authenticate)])
    async def snapshot(task_id: UUID):
        return app.state.ledger.snapshot(str(task_id))

    @app.post('/internal/v1/study-reports/document', dependencies=[Depends(authenticate)])
    async def study_document(report: StudyReport):
        from paper_agent.interfaces.study_document import DOCX_MIME, render_study_document
        content = await asyncio.to_thread(render_study_document, report)
        return Response(content, media_type=DOCX_MIME,
            headers={'Content-Disposition': 'attachment; filename="study-report.docx"'})

    @app.get('/internal/v1/papers/search', dependencies=[Depends(authenticate)])
    async def paper_search(query: str | None = Query(default=None, min_length=1, max_length=500),
                           source: Literal['auto', 'arxiv', 'openalex', 'crossref'] = 'auto',
                           limit: int = Query(default=10, ge=1, le=20),
                           page: int | None = Query(default=None, ge=1, le=10000),
                           sort: Literal['relevance', 'latest', 'citations'] = 'relevance',
                           keywords: str | None = Query(default=None, max_length=12000)):
        try:
            values = None
            if keywords is not None:
                from paper_agent.core.search_query import normalize_keywords, display_query
                values = normalize_keywords(json.loads(keywords))
                query = display_query(values)
            else:
                query = (query or '').strip()
            if not query:
                raise ValueError('A query or structured keyword list is required')
            if page is not None or keywords is not None or source == 'crossref':
                return await search_paper_page(query, source, limit, page or 1, sort, search_factory,
                                               keywords=values)
            return await search_papers(query, source, limit, search_factory)
        except ValueError:
            raise HTTPException(422, '分页或排序参数无效，翻页请指定实际来源。') from None
        except SearchRateLimit:
            raise HTTPException(429, '论文来源请求受到限流，请稍后重试。')
        except SearchTimeout:
            raise HTTPException(504, '论文来源响应超时，请稍后重试或更换来源。') from None
        except SearchError as exc:
            # Search service owns these short, safe messages, never raw upstream errors.
            raise HTTPException(502, str(exc)) from None

    return app


def main():
    from dotenv import load_dotenv
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    load_dotenv()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == '__main__':
    main()
