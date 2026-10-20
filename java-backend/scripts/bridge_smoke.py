"""Run real Java -> Python demo research, with temporary persistent databases.

Only Python's standard library is used by this harness. Both application
processes use the actual packaged implementation, not mocked HTTP handlers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from smoke import BACKEND, ROOT, Client, project_java


def free_port() -> int:
    with socket.socket() as handle:
        handle.bind(('127.0.0.1', 0))
        return handle.getsockname()[1]


class WorkerClient:
    def __init__(self, base: str, token: str):
        self.base, self.token, self.checks = base, token, 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, task_id, payload=None, expected=200, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + self.token
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(self.base + '/internal/v1/tasks/' + task_id,
                                         data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as response:
            status, raw = response.code, response.read()
        if status != expected:
            raise AssertionError(f'Worker {method}: expected HTTP {expected}, got {status}')
        self.checks += 1
        return json.loads(raw) if raw else None


def completed(client, path: str, timeout: int = 90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.request('GET', path)
        if snapshot['status'] == 'completed':
            report = snapshot['report']
            assert report and report['papers'] and report['analyses'], 'Missing actual analysis report'
            assert report['synthesis'] and report['idea_portfolio']['ideas'], 'Missing final synthesis/ideas'
            assert report['context_audits'], 'Abstract RAG must produce context audits'
            assert all(audit['selected_chunk_ids'] for audit in report['context_audits']), 'Missing evidence selection'
            stages = {event['stage'] for event in snapshot['events'] if event['status'] == 'completed'}
            assert stages == {'search', 'index', 'analyze', 'synthesize', 'ideate'}, 'Missing workflow progress events'
            return snapshot
        if snapshot['status'] in ('failed', 'interrupted'):
            raise AssertionError('Demo task did not complete: ' + str(snapshot.get('error_code')))
        time.sleep(0.3)
    raise AssertionError('Research task did not complete within the allotted time')


def main():
    java = project_java()
    jar = BACKEND / 'target' / 'paperflow-business-0.1.0.jar'
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not jar.is_file() or not python.is_file():
        raise RuntimeError('Install the Python environment and package the Java service first.')
    tool_root = ROOT / '.tools'
    tool_root.mkdir(exist_ok=True)
    summary_path = tool_root / 'java-phase3-bridge-smoke.json'
    # A failed new run must not leave a stale success result.
    summary_path.unlink(missing_ok=True)
    processes = []
    clients = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with tempfile.TemporaryDirectory(prefix='bridge_smoke_', dir=tool_root) as temporary:
        work = Path(temporary)
        worker_port, java_port = free_port(), free_port()
        while java_port == worker_port:
            java_port = free_port()
        worker_base, java_base = f'http://127.0.0.1:{worker_port}', f'http://127.0.0.1:{java_port}'
        token = uuid.uuid4().hex + uuid.uuid4().hex
        env = os.environ.copy()
        env.update(PAPERFLOW_SERVICE_TOKEN=token, PAPERFLOW_WORKER_URL=worker_base,
                   PAPERFLOW_WORKER_DB=str(work / 'worker.sqlite3'), PYTHONPATH=str(ROOT))
        database = work / 'business'
        jdbc = f'jdbc:h2:file:{database.as_posix()};MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_ON_EXIT=FALSE;WRITE_DELAY=0'

        def stop():
            # Stop Java first, so no synchronizer can dispatch during worker shutdown.
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            processes.clear()

        def launch(command, log):
            process = subprocess.Popen(command, cwd=work, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, creationflags=flags)
            processes.append(process)
            return process

        def wait_ready(process, base, path, expected):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 75
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Application exited before readiness; inspect .tools bridge logs.')
                try:
                    with opener.open(base + path, timeout=1) as response:
                        if response.status == expected:
                            return
                except urllib.error.HTTPError as response:
                    if response.code == expected:
                        return
                except (urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.3)
            raise RuntimeError('Application did not become ready within 75 seconds.')

        def start(worker_log, java_log):
            worker = launch([str(python), '-B', '-m', 'paper_agent.interfaces.worker',
                             '--host', '127.0.0.1', '--port', str(worker_port)], worker_log)
            wait_ready(worker, worker_base, '/internal/v1/tasks/' + str(uuid.uuid4()), 401)
            business = launch([str(java), '-jar', str(jar), '--spring.profiles.active=local',
                               '--server.address=127.0.0.1', f'--server.port={java_port}',
                               f'--spring.datasource.url={jdbc}'], java_log)
            wait_ready(business, java_base, '/api/auth/csrf', 200)

        suffix = uuid.uuid4().hex[:10]
        credentials_a = {'username': 'bridge_a_' + suffix, 'email': f'bridge_a_{suffix}@example.test',
                         'password': 'bridge-study-password-123'}
        credentials_b = {'username': 'bridge_b_' + suffix, 'email': f'bridge_b_{suffix}@example.test',
                         'password': 'bridge-study-password-456'}
        with (tool_root / 'java-phase3-worker-smoke.log').open('w', encoding='utf-8') as worker_log, \
                (tool_root / 'java-phase3-business-smoke.log').open('w', encoding='utf-8') as java_log:
            try:
                start(worker_log, java_log)
                a, b = Client(java_base), Client(java_base)
                worker = WorkerClient(worker_base, token)
                clients.extend((a, b, worker))
                unknown = str(uuid.uuid4())
                worker.request('GET', unknown, expected=401, authenticated=False)
                worker.request('GET', unknown, expected=404)
                a.request('GET', '/api/research/tasks', expected=401)
                for client, credentials in ((a, credentials_a), (b, credentials_b)):
                    client.refresh_csrf()
                    client.request('POST', '/api/auth/register', credentials, expected=201)
                    client.refresh_csrf()
                collection = a.request('POST', '/api/library/collections', {'name': 'Agent bridge evidence'}, expected=201)
                collection_path = f"/api/library/collections/{collection['id']}"
                paper = {'source': 'manual', 'paper_id': 'bridge-evidence-' + suffix,
                         'title': 'Retrieval augmented research with auditable evidence',
                         'abstract': 'We study retrieval augmented agents. Evidence chunks support paper analysis, '
                                     'cross-paper synthesis and research ideas. Local hashing provides offline retrieval.',
                         'authors': ['Bridge Researcher'], 'categories': ['cs.AI'],
                         'page_url': 'https://example.test/bridge-paper'}
                attached = a.request('POST', collection_path + '/papers', paper, expected=201)
                payload = {'idempotency_key': str(uuid.uuid4()), 'topic': 'Auditable retrieval agents',
                           'mode': 'demo', 'rag': 'abstract', 'limit': 1,
                           'collection_id': collection['id'], 'paper_ids': [attached['id']]}
                a.request('POST', '/api/research/tasks', payload, expected=403, csrf=False)
                first = a.request('POST', '/api/research/tasks', payload, expected=202)
                task_id = first['task_id']
                task_path = '/api/research/tasks/' + task_id
                result = completed(a, task_path)
                assert result['report']['papers'][0]['paper_id'] == paper['paper_id'], 'Worker did not use trusted collection snapshot'
                assert result['report']['papers'][0]['title'] == paper['title'], 'Paper metadata changed during dispatch'
                replay = a.request('POST', '/api/research/tasks', payload, expected=202)
                assert replay['task_id'] == task_id, 'Same key must retain task identity'
                a.request('POST', '/api/research/tasks', {**payload, 'topic': 'Changed topic'}, expected=409)
                b.request('GET', task_path, expected=404)
                b.request('POST', '/api/research/tasks', {**payload, 'idempotency_key': str(uuid.uuid4())}, expected=404)
                assert b.request('GET', '/api/research/tasks')['total'] == 0, 'Task history leaked to another user'
                assert a.request('GET', '/api/research/tasks')['total'] == 1
                # Deleting the collection must not delete its immutable task snapshot/history.
                a.request('DELETE', collection_path, expected=204)
                assert a.request('POST', '/api/research/tasks', payload, expected=202)['task_id'] == task_id
                assert a.request('GET', task_path)['report'] == result['report']
                search_payload = {'idempotency_key': str(uuid.uuid4()), 'topic': 'retrieval augmented generation',
                                  'mode': 'demo', 'rag': 'abstract', 'limit': 2}
                search_task = a.request('POST', '/api/research/tasks', search_payload, expected=202)
                search_result = completed(a, '/api/research/tasks/' + search_task['task_id'])
                assert all(p['paper_id'] != paper['paper_id'] for p in search_result['report']['papers'])
                # Direct internal replay exercises worker idempotency independently of Java.
                direct_id = str(uuid.uuid4())
                direct_payload = {'contract_version': 1, 'topic': 'offline internal contract', 'limit': 1,
                                  'options': {'mode': 'demo', 'rag': 'abstract', 'provider': 'qwen'}, 'papers': [paper]}
                worker.request('POST', direct_id, direct_payload, expected=202)
                worker.request('POST', direct_id, direct_payload, expected=200)
                worker.request('POST', direct_id, {**direct_payload, 'topic': 'conflict'}, expected=409)
                direct_result = completed(worker, direct_id)
                stop()
                start(worker_log, java_log)
                restarted = Client(java_base)
                clients.append(restarted)
                restarted.refresh_csrf()
                restarted.request('POST', '/api/auth/login', {'identifier': credentials_a['email'], 'password': credentials_a['password']})
                restarted.refresh_csrf()
                assert restarted.request('GET', task_path)['report'] == result['report'], 'Java report did not survive restart'
                history = restarted.request('GET', '/api/research/tasks')
                assert history['total'] == 2 and len(history['tasks']) == 2, 'Persisted task history changed'
                assert worker.request('GET', direct_id)['report'] == direct_result['report'], 'Worker ledger did not survive restart'
                worker.request('POST', direct_id, direct_payload, expected=200)
            finally:
                stop()
    summary = {'status': 'passed', 'http_checks': sum(client.checks for client in clients),
               'application_restarts': {'java': 1, 'python': 1}, 'completed_demo_tasks': 3,
               'databases': ['temporary H2 file', 'temporary SQLite file'],
               'live_models_tested': False, 'external_services_required': False}
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
