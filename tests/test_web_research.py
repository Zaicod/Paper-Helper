import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from paper_agent.agents.demo import DemoResearchTeam
from paper_agent.interfaces.web import ResearchRequest, ResearchTaskManager, create_app
from pydantic import ValidationError


class WebResearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='paper_web_test_')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    async def test_request_defaults_to_live_and_abstract_rag(self):
        request = ResearchRequest(topic='RAG')
        self.assertEqual(getattr(request, 'mode', None), 'live')
        self.assertEqual(getattr(request, 'rag', None), 'abstract')

    async def test_direct_manager_ignores_requested_namespace_and_isolates_tasks(self):
        manager = ResearchTaskManager(self.root)
        request = ResearchRequest(topic='RAG', mode='demo', index_namespace='java-user:123')
        with patch.object(manager, '_run', new_callable=AsyncMock):
            first = await manager.start(request)
            second = await manager.start(request)
            await asyncio.gather(*manager._background_tasks)
        self.assertEqual(first.request.index_namespace, f'web-task:{first.task_id}')
        self.assertEqual(second.request.index_namespace, f'web-task:{second.task_id}')
        self.assertNotEqual(first.request.index_namespace, second.request.index_namespace)
        self.assertEqual(request.index_namespace, 'java-user:123')

    async def test_legacy_manager_does_not_retain_browser_runtime_secrets(self):
        manager = ResearchTaskManager(self.root)
        request = ResearchRequest(topic='RAG', mode='demo', credential_source='personal',
            runtime_credentials={'provider': 'qwen', 'api_key': 'fake-browser-runtime-secret'})
        with patch.object(manager, '_run', new_callable=AsyncMock):
            first = await manager.start(request)
            await asyncio.gather(*manager._background_tasks)
        self.assertIsNone(first.request.runtime_credentials)
        self.assertEqual(first.request.credential_source, 'server')
        self.assertIsNone(manager._records[first.task_id].view.request.runtime_credentials)

    async def test_request_rejects_whitespace_topic_and_unscoped_selection(self):
        for payload in [
            {'topic': '   '},
            {'topic': 'RAG', 'selected_papers': [{'source': 'demo', 'paper_id': 'demo-001'}]},
        ]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ResearchRequest(**payload)

    async def test_web_task_runs_rag_and_preserves_six_stage_progress(self):
        manager = ResearchTaskManager(self.root)
        started = await manager.start(ResearchRequest(topic='RAG: baseline/ablation', mode='demo'))
        finished = await manager.wait(started.task_id)
        self.assertEqual(finished.status, 'completed', finished.error)
        report = json.loads((self.root / started.task_id / next(
            name for name in finished.files if name.endswith('.json')
        )).read_text(encoding='utf-8'))
        self.assertEqual(len(report['context_audits']), 3)
        subscription = await manager.subscribe(started.task_id)
        history, queue, terminal = subscription
        await manager.unsubscribe(started.task_id, queue)
        self.assertTrue(terminal)
        counted = [event.node for event in history if event.type == 'node']
        self.assertEqual(counted, ['search', 'analyze', 'synthesize', 'ideate', 'render', 'persist'])
        self.assertTrue(any(getattr(e, 'stage', None) == 'index' for e in history))

    async def test_partial_failure_still_produces_report(self):
        class FailingTeam(DemoResearchTeam):
            async def analyze_paper(self, paper, context=None):
                if paper.paper_id == 'demo-002':
                    raise RuntimeError('temporary offline failure')
                return await super().analyze_paper(paper, context)

        manager = ResearchTaskManager(self.root, team=FailingTeam())
        with patch('paper_agent.workflows.research.asyncio.sleep', new_callable=AsyncMock):
            task = await manager.start(ResearchRequest(topic='RAG', mode='demo'))
            finished = await manager.wait(task.task_id)
        self.assertEqual(finished.status, 'completed', finished.error)
        path = next((self.root / task.task_id).glob('*.json'))
        report = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(len(report['analyses']), 2)
        self.assertEqual(len(report['analysis_failures']), 1)

    async def test_live_without_credentials_fails_instead_of_running_demo(self):
        with patch.dict(os.environ, {}, clear=True):
            manager = ResearchTaskManager(self.root)
            task = await manager.start(ResearchRequest(topic='RAG'))
            result = await manager.wait(task.task_id)
        self.assertEqual(result.status, 'failed')
        self.assertIn('DASHSCOPE_API_KEY', result.error)
        self.assertEqual(result.files, [])

    async def test_report_write_failure_never_publishes_completed(self):
        manager = ResearchTaskManager(self.root)
        with patch('paper_agent.interfaces.web.save_report', side_effect=OSError('disk full')):
            task = await manager.start(ResearchRequest(topic='RAG', mode='demo'))
            result = await manager.wait(task.task_id)
        self.assertEqual(result.status, 'failed')
        history, queue, _ = await manager.subscribe(task.task_id)
        await manager.unsubscribe(task.task_id, queue)
        self.assertNotIn('completed', [event.type for event in history])

    async def test_oversized_collection_is_rejected_before_analysis(self):
        from paper_agent.tools.search import FixtureSearchClient
        paper = (await FixtureSearchClient().search('RAG', 1))[0]

        class OversizedLibrary:
            def get_collection_papers(self, *args):
                return [paper.model_copy(update={'paper_id': str(i)}) for i in range(21)]

        manager = ResearchTaskManager(self.root, library=OversizedLibrary())
        task = await manager.start(ResearchRequest(topic='RAG', mode='demo', collection_id=1))
        result = await manager.wait(task.task_id)
        self.assertEqual(result.status, 'failed')
        self.assertIn('20', result.error)

    async def test_private_storage_exception_is_not_exposed_in_task_status(self):
        class BrokenLibrary:
            def get_collection_papers(self, *args):
                raise OSError('connection failed: api_key=FAKE_SECRET_VALUE')

        manager = ResearchTaskManager(self.root, library=BrokenLibrary())
        task = await manager.start(ResearchRequest(topic='RAG', mode='demo', collection_id=1))
        result = await manager.wait(task.task_id)
        self.assertEqual(result.status, 'failed')
        self.assertNotIn('FAKE_SECRET_VALUE', result.error)

    async def test_collection_selection_is_analyzed_and_persisted(self):
        from paper_agent.services.research import ResearchOptions, ResearchService
        from paper_agent.storage.library import PaperLibrary
        library = PaperLibrary.sqlite(self.root / 'library.db')
        self.addCleanup(library.close)
        seed = await ResearchService(ResearchOptions(mode='demo')).run('RAG')
        library.save_report(seed, 'seed')
        collection = library.create_collection('offline collection')
        for paper in seed.papers:
            library.add_to_collection(collection.id, paper.source, paper.paper_id)
        selected = seed.papers[1]
        manager = ResearchTaskManager(self.root / 'reports', library=library)
        task = await manager.start(ResearchRequest(
            topic='selected study', mode='demo', collection_id=collection.id,
            selected_papers=[{'source': selected.source, 'paper_id': selected.paper_id}],
        ))
        result = await manager.wait(task.task_id)
        self.assertEqual(result.status, 'completed', result.error)
        self.assertEqual(result.library_run_id, task.task_id)
        path = next((self.root / 'reports' / task.task_id).glob('*.json'))
        report = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual([p['paper_id'] for p in report['papers']], [selected.paper_id])
        self.assertEqual(len(report['context_audits']), 1)

    async def test_http_routes_run_through_shared_service(self):
        import httpx
        from paper_agent.agents.mindmap import FixtureMindMapAgent
        manager = ResearchTaskManager(self.root)
        app = create_app(manager=manager, mind_map_agent=FixtureMindMapAgent(), require_auth=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            invalid = await client.post('/api/research', json={'topic': '  ', 'mode': 'demo'})
            self.assertEqual(invalid.status_code, 422)
            response = await client.post('/api/research', json={
                'topic': 'RAG', 'mode': 'demo', 'index_namespace': 'java-user:123',
            })
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()['request']['index_namespace'],
                             'web-task:' + response.json()['task_id'])
            task = await manager.wait(response.json()['task_id'])
            response = await client.get('/api/tasks/' + task.task_id)
            self.assertEqual(response.json()['status'], 'completed')
            self.assertEqual(len(response.json()['artifacts']), 3)
            artifact = await client.get(response.json()['artifacts'][1])
            self.assertEqual(artifact.status_code, 200)


class AuthenticatedWebsocketTests(unittest.TestCase):
    def test_demo_websocket_and_explicit_model_override(self):
        from fastapi.testclient import TestClient
        from paper_agent.agents.mindmap import FixtureMindMapAgent
        from paper_agent.interfaces.web import TaskView
        from paper_agent.services.auth import AuthenticationService, InMemorySessionStore
        from paper_agent.services.catalog import PaperCatalog
        from paper_agent.storage.library import PaperLibrary

        class PersonalSettings:
            def __init__(self):
                self.calls = []

            def build_research_team(self, user_id, **kwargs):
                self.calls.append((user_id, kwargs))
                return DemoResearchTeam()

        with tempfile.TemporaryDirectory(prefix='paper_ws_test_') as tmp:
            root = Path(tmp)
            library = PaperLibrary.sqlite(root / 'library.db')
            try:
                personal = PersonalSettings()
                manager = ResearchTaskManager(root / 'reports', library=library)
                app = create_app(
                    manager=manager,
                    catalog=PaperCatalog(library, root / 'pdfs'),
                    auth_service=AuthenticationService(library, InMemorySessionStore()),
                    mind_map_agent=FixtureMindMapAgent(), model_settings_service=personal,
                    require_auth=True,
                )
                with TestClient(app) as client:
                    self.assertEqual(client.get('/api/library/collections').status_code, 401)
                    registered = client.post('/api/auth/register', json={
                        'username': 'offline_user', 'email': 'offline@example.test',
                        'password': 'offline-test-password',
                    })
                    self.assertEqual(registered.status_code, 201)
                    response = client.post('/api/research', json={
                        'topic': 'RAG', 'mode': 'demo', 'index_namespace': 'java-user:123',
                    })
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(response.json()['request']['index_namespace'],
                                     f"web-user:{registered.json()['id']}")
                    task_id = response.json()['task_id']
                    events = []
                    with client.websocket_connect('/ws/' + task_id) as websocket:
                        for _ in range(30):
                            event = websocket.receive_json()
                            events.append(event)
                            if event['type'] in {'completed', 'error'}:
                                break
                    self.assertEqual(events[-1]['type'], 'completed')
                    self.assertEqual(len([e for e in events if e['type'] == 'node']), 6)
                    self.assertEqual(personal.calls, [], 'Demo must not resolve personal live models')
                    payload = {'topic': 'RAG', 'provider': 'openai', 'model': 'test-model'}
                    with patch.object(manager, 'start', new_callable=AsyncMock) as start:
                        start.return_value = TaskView(
                            task_id='override-test', status='queued', request=ResearchRequest(**payload),
                        )
                        response = client.post('/api/research', json=payload)
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(personal.calls[-1][1], {
                        'provider': 'openai', 'model_name': 'test-model',
                    })
            finally:
                library.close()


if __name__ == '__main__':
    unittest.main()
