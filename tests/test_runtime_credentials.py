"""Per-task credentials must never become persisted task inputs or global state."""
import asyncio
import importlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from contextlib import closing

from fastapi.testclient import TestClient

TOKEN = 'model-settings-test-service-token-at-least-32-characters'
HEADERS = {'Authorization': 'Bearer '+TOKEN}
BODY = {'contract_version': 1, 'topic': 'RAG', 'limit': 1,
        'options': {'mode': 'live', 'rag': 'none', 'provider': 'qwen', 'credential_source': 'personal'}}


class RuntimeCredentialsTests(unittest.TestCase):
    def finish(self, client, task):
        for _ in range(300):
            result = client.get('/internal/v1/tasks/'+task, headers=HEADERS).json()
            if result['status'] not in ('queued', 'running'):
                return result
            time.sleep(.01)
        self.fail('Task did not finish')

    def test_credentials_are_secret_and_excluded_from_task_serialization(self):
        from paper_agent.interfaces.worker import TaskInput
        value = TaskInput.model_validate({**BODY, 'runtime_credentials': {'provider': 'qwen', 'api_key': 'fake-private-key'}})
        self.assertNotIn('fake-private-key', repr(value))
        self.assertNotIn('runtime_credentials', value.model_dump())
        self.assertNotIn('fake-private-key', value.model_dump_json())

    def test_concurrent_keys_are_local_and_duplicate_cannot_replace_admitted_key(self):
        from paper_agent.interfaces.worker import create_app
        from paper_agent.services.research import ResearchOptions, ResearchService
        seen, references = [], []
        class ControlledService:
            def __init__(self, options):
                self.options = options
            async def run(self, topic, limit, **kwargs):
                seen.append((topic, self.options.runtime_credentials.api_key.get_secret_value()))
                references.append(self.options)
                await asyncio.sleep(.06)
                return await ResearchService(ResearchOptions(mode='demo', rag='none')).run(topic, limit, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory)/'tasks.db', service_token=TOKEN,
                             service_factory=ControlledService)
            with TestClient(app) as client:
                ids = [str(uuid4()), str(uuid4())]
                for task, topic, key in zip(ids, ['first', 'second'], ['fake-private-one', 'fake-private-two']):
                    body = {**BODY, 'topic': topic, 'runtime_credentials': {'provider': 'qwen', 'api_key': key}}
                    self.assertEqual(client.post('/internal/v1/tasks/'+task, headers=HEADERS, json=body).status_code, 202)
                retry = {**BODY, 'topic': 'first', 'runtime_credentials': {'provider': 'qwen', 'api_key': 'fake-replacement'}}
                self.assertEqual(client.post('/internal/v1/tasks/'+ids[0], headers=HEADERS, json=retry).status_code, 200)
                for task in ids:
                    self.assertEqual(self.finish(client, task)['status'], 'completed')
                self.assertCountEqual(seen, [('first', 'fake-private-one'), ('second', 'fake-private-two')])
                with closing(sqlite3.connect(Path(directory)/'tasks.db')) as connection:
                    persisted = ' '.join(row[0] for row in connection.execute('SELECT payload FROM worker_tasks'))
                self.assertNotIn('fake-private', persisted)
                self.assertNotIn('runtime_credentials', persisted)
                self.assertEqual(app.state.runtime_credentials, {})
                self.assertTrue(all(value.runtime_credentials is None for value in references))

    def test_personal_missing_or_wrong_provider_never_uses_environment(self):
        from paper_agent.interfaces.worker import create_app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'DASHSCOPE_API_KEY': 'fake-server-key'}):
            app = create_app(db_path=Path(directory)/'tasks.db', service_token=TOKEN)
            with TestClient(app) as client:
                for credentials in [None, {'provider': 'openai', 'api_key': 'fake-wrong-key'}]:
                    task = str(uuid4())
                    body = {**BODY, **({'runtime_credentials': credentials} if credentials else {})}
                    response = client.post('/internal/v1/tasks/'+task, headers=HEADERS, json=body)
                    self.assertEqual(response.status_code, 202)
                    result = self.finish(client, task)
                    self.assertEqual(result['status'], 'failed')
                    self.assertIn('模型设置', result['error_message'])
                    self.assertNotIn('fake-', str(result))
                self.assertEqual(app.state.runtime_credentials, {})

    def test_saved_model_probe_authenticates_and_redacts_remote_errors(self):
        from paper_agent.interfaces.worker import create_app
        received = []
        async def tester(credentials, model):
            received.append((credentials.provider, model, credentials.api_key.get_secret_value()))
            if model == 'broken-model':
                raise RuntimeError('fake-private-key traceback sensitive remote body')
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory)/'tasks.db', service_token=TOKEN, model_tester=tester)
            with TestClient(app) as client:
                body = {'provider': 'qwen', 'model': 'my-model', 'api_key': 'fake-private-key'}
                route = '/internal/v1/models/test'
                self.assertEqual(client.post(route, json=body).status_code, 401)
                value = client.post(route, headers=HEADERS, json=body)
                self.assertEqual(value.status_code, 200)
                self.assertTrue(value.json()['success'])
                body['model'] = 'broken-model'
                failure = client.post(route, headers=HEADERS, json=body)
                self.assertFalse(failure.json()['success'])
                self.assertNotIn('fake-private-key', failure.text)
                self.assertNotIn('traceback', failure.text)
                self.assertEqual(received[0], ('qwen', 'my-model', 'fake-private-key'))
                with closing(sqlite3.connect(Path(directory)/'tasks.db')) as connection:
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM worker_tasks').fetchone()[0], 0)

    def test_shutdown_clears_running_and_queued_credentials_without_resuming_them(self):
        from paper_agent.interfaces.worker import create_app
        references = []
        class Blocked:
            def __init__(self, options):
                references.append(options)
            async def run(self, *args, **kwargs):
                await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'tasks.db'
            app = create_app(db_path=path, service_token=TOKEN, service_factory=Blocked)
            identifiers = [str(uuid4()) for _ in range(3)]
            with TestClient(app) as client:
                for task in identifiers:
                    body = {**BODY, 'runtime_credentials': {'provider': 'qwen', 'api_key': 'fake-shutdown-key'}}
                    self.assertEqual(client.post('/internal/v1/tasks/'+task, headers=HEADERS, json=body).status_code, 202)
            self.assertEqual(app.state.runtime_credentials, {})
            self.assertTrue(all(options.runtime_credentials is None for options in references))
            resumed = create_app(db_path=path, service_token=TOKEN)
            with TestClient(resumed) as client:
                for task in identifiers:
                    self.assertEqual(self.finish(client, task)['status'], 'interrupted')


class ProbeHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_uses_fixed_origins_and_bounded_output_without_following_redirect(self):
        import httpx
        from openai import AsyncOpenAI, APIStatusError
        from paper_agent.services.model_runtime import RuntimeCredentials, probe_model
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.host == 'api.openai.com':
                return httpx.Response(302, headers={'Location': 'https://other.example/leak'})
            return httpx.Response(200, json={'id':'probe', 'object':'chat.completion', 'created':0,
                'model':'my-model', 'choices':[{'index':0, 'finish_reason':'stop', 'message':{'role':'assistant', 'content':'OK'}}]})
        clients, replaced_clients = [], []
        def build(**kwargs):
            replaced_clients.append(kwargs['http_client'])
            kwargs['http_client'] = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
            client = AsyncOpenAI(**kwargs)
            clients.append(client)
            return client
        with patch('paper_agent.services.model_runtime.AsyncOpenAI', side_effect=build):
            await probe_model(RuntimeCredentials(provider='qwen', api_key='fake-probe-key'), 'my-model')
            with self.assertRaises(APIStatusError):
                await probe_model(RuntimeCredentials(provider='openai', api_key='fake-other-key'), 'my-model')
        for client in replaced_clients:
            await client.aclose()
        self.assertEqual([request.url.host for request in calls], ['dashscope.aliyuncs.com', 'api.openai.com'])
        self.assertEqual(json.loads(calls[0].content)['max_tokens'], 16)
        self.assertEqual(json.loads(calls[1].content)['max_completion_tokens'], 16)
        self.assertTrue(all(client.is_closed() for client in clients))


class RuntimeClientTests(unittest.TestCase):
    def test_personal_clients_use_distinct_keys_without_modifying_environment(self):
        runtime = importlib.import_module('paper_agent.services.model_runtime')
        from paper_agent.services.research import ResearchOptions, ResearchService
        from paper_agent.services.study import StudyService
        before = dict(os.environ)
        with patch('paper_agent.services.model_runtime.AsyncOpenAI', wraps=runtime.AsyncOpenAI) as clients:
            for key, provider, service in [('fake-account-one', 'qwen', ResearchService), ('fake-account-two', 'openai', StudyService)]:
                options = ResearchOptions(credential_source='personal', provider=provider, model='configured-model',
                    runtime_credentials=runtime.RuntimeCredentials(provider=provider, api_key=key))
                team = service(options)._build_team()
                self.assertEqual(team.analyst.model.model, 'configured-model')
                self.assertNotIn(key, options.model_dump_json())
            self.assertEqual([call.kwargs['api_key'] for call in clients.call_args_list], ['fake-account-one', 'fake-account-two'])
        self.assertEqual(before, dict(os.environ))
