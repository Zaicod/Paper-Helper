import asyncio
import importlib
import importlib.util
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


TOKEN = 'worker-test-service-token-at-least-32-characters'
HEADERS = {'Authorization': f'Bearer {TOKEN}'}
BODY = {'contract_version': 1, 'topic': 'RAG', 'limit': 2,
        'options': {'mode': 'demo', 'rag': 'abstract', 'provider': 'qwen'}, 'papers': None}


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'worker.sqlite3'

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.interfaces.worker'),
                             'An independent authenticated worker entry point is required')
        return importlib.import_module('paper_agent.interfaces.worker')

    def app(self, **kwargs):
        return self.module().create_app(db_path=self.db, service_token=TOKEN, **kwargs)

    def submit(self, client, body=None, task_id=None):
        return client.post(f'/internal/v1/tasks/{task_id or uuid4()}',
                           headers=HEADERS, json=body or BODY)

    def finished(self, client, task_id):
        for _ in range(300):
            response = client.get(f'/internal/v1/tasks/{task_id}', headers=HEADERS)
            value = response.json()
            if value['status'] not in ('queued', 'running'):
                return value
            time.sleep(.01)
        self.fail('Worker did not reach a terminal state')

    def test_auth_and_bounded_contract(self):
        with TestClient(self.app()) as client:
            url = f'/internal/v1/tasks/{uuid4()}'
            self.assertEqual(client.post(url, json=BODY).status_code, 401)
            self.assertEqual(client.get(url).status_code, 401)
            self.assertEqual(client.get(url, headers=HEADERS).status_code, 404)
            self.assertEqual(self.submit(client, {**BODY, 'secret': 'no-echo'}).status_code, 422)
            bad = self.submit(client, {**BODY, 'options': {**BODY['options'], 'rag': 'pdf'}})
            self.assertEqual(bad.status_code, 422)
            self.assertNotIn('input', bad.text)
            self.assertEqual(self.submit(client, {**BODY, 'limit': 21}).status_code, 422)
            self.assertEqual(self.submit(client, {**BODY, 'topic': '   '}).status_code, 422)
            self.assertEqual(client.post(url, headers=HEADERS, content=b'x' * (2*1024*1024+1)).status_code, 413)

    def test_demo_completion_events_report_persist_and_idempotency(self):
        task_id = str(uuid4())
        with TestClient(self.app()) as client:
            self.assertEqual(self.submit(client, task_id=task_id).status_code, 202)
            value = self.finished(client, task_id)
            self.assertEqual(value['status'], 'completed')
            self.assertEqual(value['contract_version'], 1)
            self.assertEqual(len(value['report']['papers']), 2)
            self.assertTrue(value['report']['context_audits'])
            self.assertTrue(any(e['stage'] == 'ideate' for e in value['events']))
            self.assertIsNone(value['error_code'])
            self.assertEqual(self.submit(client, task_id=task_id).status_code, 200)
            self.assertEqual(self.submit(client, {**BODY, 'topic': 'changed'}, task_id).status_code, 409)
        with TestClient(self.app()) as client:
            self.assertEqual(self.finished(client, task_id), value)

    def test_failure_is_safe(self):
        class Broken:
            async def run(self, *args, **kwargs):
                raise RuntimeError('sk-private-secret /private/path traceback')
        with TestClient(self.app(service_factory=lambda options: Broken())) as client:
            task_id = str(uuid4())
            self.submit(client, task_id=task_id)
            value = self.finished(client, task_id)
            self.assertEqual(value['status'], 'failed')
            self.assertIsNone(value['report'])
            self.assertEqual(value['error_code'], 'research_failed')
            self.assertNotIn('private', json.dumps(value))

    def test_shutdown_interrupts_and_ledger_has_one_process(self):
        class Blocked:
            async def run(self, *args, **kwargs):
                await asyncio.Event().wait()
        task_id = str(uuid4())
        with TestClient(self.app(service_factory=lambda options: Blocked())) as client:
            self.submit(client, task_id=task_id)
            with self.assertRaisesRegex(RuntimeError, 'already in use'):
                with TestClient(self.app()):
                    pass
        with TestClient(self.app()) as client:
            value = self.finished(client, task_id)
            self.assertEqual(value['status'], 'interrupted')
            self.assertIsNone(value['report'])
            self.assertEqual(self.submit(client, task_id=task_id).status_code, 200)

    def test_crash_recovery_marks_unfinished_interrupted(self):
        with TestClient(self.app()) as client:
            task_id = str(uuid4())
            self.submit(client, task_id=task_id)
            self.finished(client, task_id)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("UPDATE worker_tasks SET status='running', report=NULL")
            connection.commit()
        with TestClient(self.app()) as client:
            self.assertEqual(self.finished(client, task_id)['status'], 'interrupted')

    def test_events_are_bounded_and_queue_duplicates_are_not_charged(self):
        from paper_agent.core.models import ResearchStageEvent
        from paper_agent.services.research import ResearchService
        calls = []
        class ManyEvents:
            async def run(self, topic, limit, papers, on_event):
                calls.append(topic)
                for _ in range(230):
                    await on_event(ResearchStageEvent(stage='search', status='started', message='ok'))
                return await ResearchService(self.options).run(topic, limit, papers=papers)
        def factory(options):
            value = ManyEvents()
            value.options = options
            return value
        with TestClient(self.app(service_factory=factory)) as client:
            task_id = str(uuid4())
            self.submit(client, task_id=task_id)
            value = self.finished(client, task_id)
            self.assertEqual(len(value['events']), 200)
            for _ in range(20):
                self.assertEqual(self.submit(client, task_id=task_id).status_code, 200)
            self.assertEqual(calls, ['RAG'])

    def test_service_token_is_required(self):
        with self.assertRaises(ValueError):
            self.module().create_app(db_path=self.db, service_token='short')

    def test_trusted_index_namespace_and_rebuild_reach_service_legacy_tasks_are_isolated(self):
        from paper_agent.services.research import ResearchService
        received = []
        def factory(options):
            received.append((options.index_namespace, options.rebuild_index))
            return ResearchService(options)
        with TestClient(self.app(service_factory=factory)) as client:
            identifiers = [str(uuid4()) for _ in range(3)]
            for identifier, extra in zip(identifiers, [
                {'index_namespace': 'java-user:7', 'rebuild_index': True}, {}, {},
            ]):
                response = self.submit(client, {**BODY, **extra}, identifier)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(self.finished(client, identifier)['status'], 'completed')
            self.assertEqual(received, [('java-user:7', True),
                ('task:'+identifiers[1], False), ('task:'+identifiers[2], False)])
            self.assertEqual(self.submit(client, {**BODY, 'index_namespace': '../victim'}).status_code, 422)

    def test_paper_title_limit_matches_java_metadata_contract(self):
        from pydantic import ValidationError
        paper_type = self.module().WorkerPaper
        paper = {'paper_id': 'boundary-paper', 'source': 'manual', 'title': 'a' * 1024,
                 'abstract': '', 'authors': [], 'page_url': 'https://example.com/paper'}
        try:
            accepted = paper_type.model_validate(paper)
        except ValidationError:
            self.fail('The worker must accept a 1024-character title allowed by Java')
        self.assertEqual(len(accepted.title), 1024)
        with self.assertRaises(ValidationError):
            paper_type.model_validate({**paper, 'title': 'a' * 1025})

    def test_saturated_queue_rejects_new_work_but_allows_replay(self):
        class Blocked:
            async def run(self, *args, **kwargs):
                await asyncio.Event().wait()
        with TestClient(self.app(service_factory=lambda options: Blocked())) as client:
            first_id = str(uuid4())
            self.assertEqual(self.submit(client, task_id=first_id).status_code, 202)
            accepted = 1
            for _ in range(30):
                response = self.submit(client)
                if response.status_code == 503:
                    break
                self.assertEqual(response.status_code, 202)
                accepted += 1
            else:
                self.fail('Queue admission must be bounded')
            self.assertLessEqual(accepted, 18)
            self.assertEqual(self.submit(client, task_id=first_id).status_code, 200)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM worker_tasks').fetchone()[0], accepted)
