"""interfaces web implementation."""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv

load_dotenv()

from paper_agent.services.auth import (
    AuthenticationError,
    AuthenticationService,
    RedisSessionStore,
    SessionStoreError,
)
from paper_agent.services.catalog import PaperCatalog, PdfDownloadError
from paper_agent.services.research import ResearchOptions, ResearchService
from paper_agent.core.errors import public_error_message
from paper_agent.core.models import ResearchStageEvent
from paper_agent.agents.mindmap import MindMapGenerator, build_mind_map_agent
from paper_agent.services.model_routing import (
    AgentSettingUpdate,
    ModelConfigurationError,
    PersonalModelSettings,
    ProviderUpdate,
)
from paper_agent.interfaces.report import save_report
from paper_agent.tools.search import SearchError
from paper_agent.storage.library import PaperLibrary
from paper_agent.core.protocols import ResearchTeam

try:
    from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover - only reached without the web extra
    FastAPI = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]
    Request = None  # type: ignore[assignment,misc]
    Response = None  # type: ignore[assignment,misc]
    WebSocket = None  # type: ignore[assignment,misc]
    WebSocketDisconnect = None  # type: ignore[assignment,misc]
    FileResponse = None  # type: ignore[assignment,misc]
    HTMLResponse = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]
    StaticFiles = None  # type: ignore[assignment,misc]


TERMINAL_STATUSES = {"completed", "failed"}
SESSION_COOKIE = "paperflow_session"


class PaperReference(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    paper_id: str = Field(min_length=1, max_length=255)


class ResearchRequest(ResearchOptions):
    topic: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=3, ge=1, le=20)
    category: Literal["cs.CL", "cs.AI"] | None = None
    collection_id: int | None = Field(default=None, ge=1)
    selected_papers: list[PaperReference] = Field(default_factory=list, max_length=20)

    @field_validator("topic")
    @classmethod
    def clean_topic(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("研究主题不能为空")
        return value

    @model_validator(mode="after")
    def validate_selection(self):
        if self.selected_papers and self.collection_id is None:
            raise ValueError("selected_papers 必须指定所属 collection_id")
        identities = [(p.source, p.paper_id) for p in self.selected_papers]
        if len(identities) != len(set(identities)):
            raise ValueError("所选论文不能重复")
        return self


class TaskEvent(BaseModel):
    type: Literal["task", "node", "completed", "error"]
    message: str
    node: str | None = None
    stage: str | None = None
    status: Literal["started", "completed", "failed"] | None = None
    paper_id: str | None = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class TaskView(BaseModel):
    task_id: str
    status: Literal["queued", "running", "completed", "failed"]
    request: ResearchRequest
    files: list[str] = Field(default_factory=list)
    library_run_id: str | None = None
    error: str | None = None


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)


class CollectionPaperAdd(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    paper_id: str = Field(min_length=1, max_length=255)


class NoteUpdate(BaseModel):
    content: str = Field(default="", max_length=50000)


class PaperNoteUpdate(NoteUpdate):
    source: str = Field(min_length=1, max_length=64)
    paper_id: str = Field(min_length=1, max_length=255)


class MindMapCreate(BaseModel):
    direction: str = Field(min_length=1, max_length=500)
    date_from: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    selected_papers: list[PaperReference] = Field(default_factory=list, max_length=50)


class TagAdd(BaseModel):
    tag: str = Field(min_length=1, max_length=128)


class PaperImportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    paper_id: str = Field(min_length=1, max_length=255)
    collection_id: int | None = Field(default=None, ge=1)
    collection_name: str | None = Field(default=None, max_length=255)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


@dataclass
class _TaskRecord:
    view: TaskView
    team: ResearchTeam | None = None
    events: list[TaskEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[TaskEvent]] = field(default_factory=set)
    done: asyncio.Event = field(default_factory=asyncio.Event)


class ResearchTaskManager:
    """Run the shared research service and retain events for WebSocket clients."""

    def __init__(
        self,
        output_root: Path,
        library: PaperLibrary | None = None,
        team: ResearchTeam | None = None,
    ) -> None:
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, _TaskRecord] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self.library = library
        self.team = team

    async def start(
        self, request: ResearchRequest, team: ResearchTeam | None = None,
        *, user_id: int | None = None,
    ) -> TaskView:
        task_id = uuid4().hex
        # Namespace is trusted server context, never a browser-selected option.
        # Direct/local calls without an authenticated account stay task-local.
        namespace = f'web-user:{user_id}' if user_id is not None else f'web-task:{task_id}'
        request = request.model_copy(deep=True, update={'index_namespace': namespace,
            'runtime_credentials': None, 'credential_source': 'server'})
        record = _TaskRecord(
            view=TaskView(
                task_id=task_id,
                status="queued",
                request=request,
            ),
            team=team,
        )
        async with self._lock:
            self._records[task_id] = record

        handle = asyncio.create_task(self._run(task_id))
        self._background_tasks.add(handle)
        handle.add_done_callback(self._background_tasks.discard)
        return record.view.model_copy(deep=True)

    async def get(self, task_id: str) -> TaskView | None:
        async with self._lock:
            record = self._records.get(task_id)
            return record.view.model_copy(deep=True) if record else None

    async def wait(self, task_id: str, timeout: float = 10.0) -> TaskView:
        async with self._lock:
            record = self._records.get(task_id)
        if record is None:
            raise KeyError(task_id)
        await asyncio.wait_for(record.done.wait(), timeout=timeout)
        return record.view.model_copy(deep=True)

    async def subscribe(
        self, task_id: str
    ) -> tuple[list[TaskEvent], asyncio.Queue[TaskEvent], bool] | None:
        async with self._lock:
            record = self._records.get(task_id)
            if record is None:
                return None
            queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
            record.subscribers.add(queue)
            return (
                [event.model_copy(deep=True) for event in record.events],
                queue,
                record.view.status in TERMINAL_STATUSES,
            )

    async def unsubscribe(
        self, task_id: str, queue: asyncio.Queue[TaskEvent]
    ) -> None:
        async with self._lock:
            record = self._records.get(task_id)
            if record is not None:
                record.subscribers.discard(queue)

    def resolve_artifact(self, task_id: str, filename: str) -> Path | None:
        if Path(filename).name != filename:
            return None
        task_dir = (self.output_root / task_id).resolve()
        candidate = (task_dir / filename).resolve()
        if candidate.parent != task_dir or not candidate.is_file():
            return None
        return candidate

    async def _publish(self, task_id: str, event: TaskEvent) -> None:
        async with self._lock:
            record = self._records[task_id]
            record.events.append(event)
            subscribers = list(record.subscribers)
        for queue in subscribers:
            queue.put_nowait(event)

    async def _run(self, task_id: str) -> None:
        async with self._lock:
            record = self._records[task_id]
            record.view.status = "running"
            request = record.view.request.model_copy(deep=True)
            task_team = record.team or self.team

        await self._publish(
            task_id, TaskEvent(type="task", message="研究任务开始"),
        )

        async def forward_event(event: ResearchStageEvent) -> None:
            # The existing UI counts six completed nodes. Indexing and started/
            # failed details remain visible without inflating that counter.
            counted = event.status == "completed" and event.stage != "index"
            await self._publish(task_id, TaskEvent(
                type="node" if counted else "task",
                node=event.stage if counted else None,
                stage=event.stage, status=event.status,
                paper_id=event.paper_id, message=event.message,
                timestamp=event.timestamp,
            ))

        try:
            papers = None
            if request.collection_id is not None:
                if self.library is None:
                    raise RuntimeError("collection research requires the paper library")
                references = [(p.source, p.paper_id) for p in request.selected_papers]
                papers = await asyncio.to_thread(
                    self.library.get_collection_papers,
                    request.collection_id, references or None,
                )
                if not papers:
                    raise ValueError("收藏夹中没有符合条件的论文")
            options = ResearchOptions.model_validate(request.model_dump())
            service = ResearchService(options, team=task_team)
            report = await service.run(
                request.topic, request.limit, request.category,
                papers=papers, on_event=forward_event,
            )

            task_dir = self.output_root / task_id
            paths = await asyncio.to_thread(save_report, report, task_dir)
            filenames = [path.name for path in paths]
            await self._publish(task_id, TaskEvent(
                type="node", node="render", stage="render", status="completed",
                message="研究报告文件已生成",
            ))

            if self.library is not None:
                await asyncio.to_thread(
                    self.library.save_report, report, task_id, request.category,
                )
                if request.collection_id is not None:
                    await asyncio.to_thread(
                        self.library.link_research_run, request.collection_id, task_id,
                    )
                async with self._lock:
                    self._records[task_id].view.library_run_id = task_id
            await self._publish(task_id, TaskEvent(
                type="node", node="persist", stage="persist", status="completed",
                message="研究结果已保存",
            ))

            async with self._lock:
                record = self._records[task_id]
                record.view.status = "completed"
                record.view.files = filenames
            await self._publish(task_id, TaskEvent(type="completed", message=(
                f"研究报告已生成：成功 {len(report.analyses)} 篇，"
                f"失败 {len(report.analysis_failures)} 篇"
            )))
        except Exception as exc:
            async with self._lock:
                record = self._records[task_id]
                record.view.status = "failed"
                record.view.error = f"{type(exc).__name__}: {public_error_message(exc)}"
            await self._publish(
                task_id, TaskEvent(type="error", message="研究任务执行失败"),
            )
        finally:
            async with self._lock:
                self._records[task_id].done.set()


def create_app(
    output_root: Path | None = None,
    manager: ResearchTaskManager | None = None,
    catalog: PaperCatalog | None = None,
    auth_service: AuthenticationService | None = None,
    mind_map_agent: MindMapGenerator | None = None,
    model_settings_service: PersonalModelSettings | None = None,
    require_auth: bool | None = None,
):
    """Create the optional FastAPI application without affecting CLI users."""

    if FastAPI is None:  # pragma: no cover - exercised by installation usage
        raise RuntimeError(
            'Web UI dependencies are missing; install with pip install -e ".[web]"'
        )

    if manager is None:
        database_url = os.getenv("PAPER_AGENT_DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "Web 服务需要 MySQL：请设置 PAPER_AGENT_DATABASE_URL "
                "(mysql+pymysql://用户:密码@主机:3306/数据库?charset=utf8mb4)"
            )
        library = PaperLibrary(database_url)
        if library.engine.dialect.name != "mysql":
            library.close()
            raise RuntimeError("Web 服务的 PAPER_AGENT_DATABASE_URL 必须指向 MySQL")
        library.initialize()
        web_manager = ResearchTaskManager(
            output_root or Path("outputs/web"),
            library=library,
        )
    else:
        web_manager = manager
    app = FastAPI(title="Paper Research Agent", version="0.3.0")
    app.state.task_manager = web_manager
    paper_catalog = catalog
    if paper_catalog is None and web_manager.library is not None:
        paper_catalog = PaperCatalog(
            web_manager.library,
            Path("outputs/library/pdfs"),
        )
    app.state.paper_catalog = paper_catalog
    map_agent = mind_map_agent or build_mind_map_agent()
    app.state.mind_map_agent = map_agent
    personal_settings = model_settings_service
    if personal_settings is None and web_manager.library is not None:
        personal_settings = PersonalModelSettings(
            web_manager.library,
            web_manager.output_root / ".model-settings.key",
        )
    app.state.model_settings = personal_settings
    authentication = auth_service
    if authentication is None and web_manager.library is not None:
        redis_url = os.getenv(
            "PAPER_AGENT_REDIS_URL", "redis://127.0.0.1:6379/0"
        )
        session_ttl = int(
            os.getenv("PAPER_AGENT_SESSION_TTL_SECONDS", str(7 * 24 * 3600))
        )
        authentication = AuthenticationService(
            web_manager.library,
            RedisSessionStore.from_url(redis_url, session_ttl),
        )
    auth_is_required = (manager is None) if require_auth is None else require_auth
    app.state.auth_service = authentication
    app.state.auth_required = auth_is_required
    cookie_secure = os.getenv("PAPER_AGENT_COOKIE_SECURE", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    def require_authentication() -> AuthenticationService:
        if authentication is None:
            raise HTTPException(status_code=503, detail="authentication is disabled")
        return authentication

    async def resolve_user(token: str):
        service = require_authentication()
        try:
            return await service.current_user(token)
        except SessionStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.middleware("http")
    async def protect_api(request: Request, call_next):
        path = request.url.path
        protected = path.startswith("/api/") and not path.startswith("/api/auth/")
        if auth_is_required and protected:
            token = request.cookies.get(SESSION_COOKIE, "")
            try:
                user = await resolve_user(token)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            if user is None:
                return JSONResponse(status_code=401, content={"detail": "请先登录"})
            request.state.user = user
        return await call_next(request)
    static_root = Path(__file__).resolve().parents[1] / "web_static"
    assets_root = static_root / "assets"
    if assets_root.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_root), name="web-assets")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        page = static_root / "index.html"
        return page.read_text(encoding="utf-8")

    def set_session_cookie(response: Response, token: str) -> None:
        service = require_authentication()
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=service.sessions.ttl_seconds,
            httponly=True,
            secure=cookie_secure,
            samesite="lax",
            path="/",
        )

    @app.post("/api/auth/register", status_code=201)
    async def register(request: RegisterRequest, response: Response):
        service = require_authentication()
        try:
            session = await service.register(
                request.username, request.email, request.password
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SessionStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        set_session_cookie(response, session.token)
        return session.user.model_dump(mode="json")

    @app.post("/api/auth/login")
    async def login(request: LoginRequest, response: Response):
        service = require_authentication()
        try:
            session = await service.login(request.identifier, request.password)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except SessionStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        set_session_cookie(response, session.token)
        return session.user.model_dump(mode="json")

    @app.get("/api/auth/me")
    async def auth_me(request: Request):
        user = await resolve_user(request.cookies.get(SESSION_COOKIE, ""))
        if user is None:
            raise HTTPException(status_code=401, detail="登录会话不存在或已过期")
        return user.model_dump(mode="json")

    @app.post("/api/auth/logout", status_code=204)
    async def logout(request: Request, response: Response):
        service = require_authentication()
        try:
            await service.logout(request.cookies.get(SESSION_COOKIE, ""))
        except SessionStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=cookie_secure,
            httponly=True,
            samesite="lax",
        )

    @app.post("/api/research", status_code=202)
    async def start_research(request: Request, body: ResearchRequest):
        team = None
        user = getattr(request.state, "user", None)
        if body.mode == "live" and user is not None and personal_settings is not None:
            try:
                overrides = {}
                if 'provider' in body.model_fields_set:
                    overrides['provider'] = body.provider
                if 'model' in body.model_fields_set:
                    overrides['model_name'] = body.model
                team = await asyncio.to_thread(
                    personal_settings.build_research_team, user.id, **overrides,
                )
            except (ModelConfigurationError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        task = await web_manager.start(body, team=team,
                                       user_id=user.id if user is not None else None)
        return task.model_dump(mode="json")

    @app.get("/api/tasks/{task_id}")
    async def get_task(task_id: str):
        task = await web_manager.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        payload = task.model_dump(mode="json")
        payload["artifacts"] = [
            f"/api/tasks/{task_id}/files/{filename}" for filename in task.files
        ]
        return payload

    @app.get("/api/tasks/{task_id}/files/{filename}")
    async def get_artifact(task_id: str, filename: str):
        path = web_manager.resolve_artifact(task_id, filename)
        if path is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(path, filename=path.name)

    def require_library() -> PaperLibrary:
        if web_manager.library is None:
            raise HTTPException(status_code=503, detail="paper library is disabled")
        return web_manager.library

    def require_catalog() -> PaperCatalog:
        if paper_catalog is None:
            raise HTTPException(status_code=503, detail="paper catalog is disabled")
        return paper_catalog

    def require_model_settings() -> PersonalModelSettings:
        if personal_settings is None:
            raise HTTPException(status_code=503, detail="model settings are disabled")
        return personal_settings

    def current_user_id(request: Request) -> int:
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        return user.id

    @app.get("/api/search/papers")
    async def search_papers(
        query: str,
        limit: int = 10,
        category: str | None = None,
        source: str = "auto",
    ):
        service = require_catalog()
        try:
            papers = await service.search(query, limit, category, source)
        except (ValueError, SearchError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"papers": [paper.model_dump(mode="json") for paper in papers]}

    @app.post("/api/library/import", status_code=201)
    async def import_paper(request: PaperImportRequest):
        service = require_catalog()
        try:
            paper = await service.download_to_collection(
                request.source,
                request.paper_id,
                collection_id=request.collection_id,
                collection_name=request.collection_name,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, PdfDownloadError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = paper.model_dump(mode="json")
        if paper.download_id is not None:
            payload["local_download_url"] = (
                f"/api/library/downloads/{paper.download_id}"
            )
        return payload

    @app.get("/api/library/downloads/{download_id}")
    async def get_downloaded_pdf(download_id: int):
        resolved = require_catalog().resolve_download(download_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="downloaded PDF not found")
        path, filename = resolved
        return FileResponse(path, filename=filename, media_type="application/pdf")

    @app.get("/api/library/papers")
    async def list_library_papers(query: str | None = None, limit: int = 50):
        library = require_library()
        papers = await asyncio.to_thread(library.list_papers, query, limit)
        return {"papers": [paper.model_dump(mode="json") for paper in papers]}

    @app.get("/api/library/papers/{source}/{paper_id}")
    async def get_library_paper(source: str, paper_id: str):
        library = require_library()
        paper = await asyncio.to_thread(library.get_paper, source, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="paper not found")
        return paper.model_dump(mode="json")

    @app.get("/api/library/collections")
    async def list_collections(query: str | None = None):
        library = require_library()
        collections = await asyncio.to_thread(library.list_collections, query)
        return {
            "collections": [item.model_dump(mode="json") for item in collections]
        }

    @app.post("/api/library/collections", status_code=201)
    async def create_collection(request: CollectionCreate):
        library = require_library()
        collection = await asyncio.to_thread(
            library.create_collection, request.name, request.description
        )
        return collection.model_dump(mode="json")

    @app.delete("/api/library/collections/{collection_id}", status_code=204)
    async def delete_collection(collection_id: int):
        deleted = await asyncio.to_thread(
            require_library().delete_collection, collection_id
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="collection not found")

    @app.get("/api/library/collections/{collection_id}")
    async def get_collection(collection_id: int):
        collection = await asyncio.to_thread(
            require_library().get_collection, collection_id
        )
        if collection is None:
            raise HTTPException(status_code=404, detail="collection not found")
        return collection.model_dump(mode="json")

    @app.put("/api/library/collections/{collection_id}/note")
    async def update_collection_note(collection_id: int, request: NoteUpdate):
        try:
            content = await asyncio.to_thread(
                require_library().update_collection_note,
                collection_id,
                request.content,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"content": content}

    @app.put("/api/library/collections/{collection_id}/paper-note")
    async def update_paper_note(collection_id: int, request: PaperNoteUpdate):
        try:
            content = await asyncio.to_thread(
                require_library().update_paper_note,
                collection_id,
                request.source,
                request.paper_id,
                request.content,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"content": content}

    @app.post("/api/library/collections/{collection_id}/mind-maps", status_code=201)
    async def create_mind_map(
        collection_id: int, request: Request, body: MindMapCreate
    ):
        if body.date_from and body.date_to and body.date_from > body.date_to:
            raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
        references = [
            (reference.source, reference.paper_id)
            for reference in body.selected_papers
        ]
        library = require_library()
        try:
            papers = await asyncio.to_thread(
                library.get_collection_papers,
                collection_id,
                references or None,
                body.date_from,
                body.date_to,
            )
        except (KeyError, ValueError) as exc:
            status = 404 if isinstance(exc, KeyError) else 422
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        if not papers:
            raise HTTPException(status_code=422, detail="所选日期和论文范围内没有数据")
        collection_note, paper_notes = await asyncio.to_thread(
            library.get_collection_notes, collection_id
        )
        selected_map_agent = map_agent
        user = getattr(request.state, "user", None)
        if user is not None and personal_settings is not None:
            try:
                selected_map_agent = await asyncio.to_thread(
                    personal_settings.build_mind_map_agent, user.id
                )
            except ModelConfigurationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        draft = await selected_map_agent.generate(
            body.direction,
            papers,
            paper_notes,
            collection_note,
        )
        selected_references = [(paper.source, paper.paper_id) for paper in papers]
        saved = await asyncio.to_thread(
            library.save_mind_map,
            collection_id,
            body.direction,
            body.date_from,
            body.date_to,
            getattr(selected_map_agent, "name", type(selected_map_agent).__name__),
            draft,
            selected_references,
        )
        return saved.model_dump(mode="json")

    @app.get("/api/settings/models")
    async def get_model_settings(request: Request):
        settings = await asyncio.to_thread(
            require_model_settings().view, current_user_id(request)
        )
        return settings.model_dump(mode="json")

    @app.put("/api/settings/providers/{provider}", status_code=204)
    async def update_provider(
        provider: str, request: Request, body: ProviderUpdate
    ):
        try:
            await asyncio.to_thread(
                require_model_settings().save_provider,
                current_user_id(request),
                provider,
                body.api_key,
                body.base_url,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/settings/providers/{provider}", status_code=204)
    async def delete_provider(provider: str, request: Request):
        try:
            await asyncio.to_thread(
                require_model_settings().delete_provider,
                current_user_id(request),
                provider,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/settings/agents/{agent_role}")
    async def update_agent_setting(
        agent_role: str, request: Request, body: AgentSettingUpdate
    ):
        try:
            setting = await asyncio.to_thread(
                require_model_settings().save_agent,
                current_user_id(request),
                agent_role,
                body.provider,
                body.model_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return setting.model_dump(mode="json")

    @app.put("/api/settings/presets/{preset}", status_code=204)
    async def apply_model_preset(preset: str, request: Request):
        try:
            await asyncio.to_thread(
                require_model_settings().apply_preset,
                current_user_id(request),
                preset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/library/collections/{collection_id}/papers", status_code=204)
    async def add_collection_paper(
        collection_id: int, request: CollectionPaperAdd
    ):
        library = require_library()
        try:
            await asyncio.to_thread(
                library.add_to_collection,
                collection_id,
                request.source,
                request.paper_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/library/papers/{source}/{paper_id}/tags", status_code=204)
    async def add_paper_tag(source: str, paper_id: str, request: TagAdd):
        library = require_library()
        try:
            await asyncio.to_thread(
                library.add_tag, source, paper_id, request.tag
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.websocket("/ws/{task_id}")
    async def task_events(websocket: WebSocket, task_id: str):
        if auth_is_required:
            try:
                user = await resolve_user(
                    websocket.cookies.get(SESSION_COOKIE, "")
                )
            except HTTPException:
                await websocket.close(code=1013, reason="session service unavailable")
                return
            if user is None:
                await websocket.close(code=4401, reason="authentication required")
                return
        subscription = await web_manager.subscribe(task_id)
        if subscription is None:
            await websocket.close(code=4404, reason="task not found")
            return

        history, queue, terminal = subscription
        await websocket.accept()
        try:
            for event in history:
                await websocket.send_json(event.model_dump(mode="json"))
            if terminal:
                return

            while True:
                event = await queue.get()
                await websocket.send_json(event.model_dump(mode="json"))
                if event.type in {"completed", "error"}:
                    return
        except WebSocketDisconnect:
            pass
        finally:
            await web_manager.unsubscribe(task_id, queue)

    @app.get("/library", response_class=HTMLResponse)
    @app.get("/tasks", response_class=HTMLResponse)
    @app.get("/collections", response_class=HTMLResponse)
    @app.get("/settings", response_class=HTMLResponse)
    async def spa_page():
        page = static_root / "index.html"
        return page.read_text(encoding="utf-8")

    if authentication is not None:
        app.router.add_event_handler("shutdown", authentication.close)

    return app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="论文研究助手 Web 服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    return parser


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            'Web UI dependencies are missing; install with pip install -e ".[web]"'
        ) from exc

    args = build_parser().parse_args()
    uvicorn.run(
        "paper_agent.interfaces.web:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
