"""Exercise the packaged Java service over real HTTP without external services."""

from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def project_java() -> Path:
    candidates = [os.environ.get('PAPERFLOW_JAVA_HOME'), os.environ.get('JAVA_HOME')]
    jdk_root = Path.home() / '.jdks'
    if jdk_root.is_dir():
        candidates.extend(str(p) for p in sorted(jdk_root.iterdir(), reverse=True) if p.is_dir())
    for candidate in candidates:
        if not candidate:
            continue
        executable = Path(candidate) / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        if not executable.is_file():
            continue
        result = subprocess.run([str(executable), '-version'], capture_output=True, text=True, timeout=10)
        version = re.search(r'version "(\d+)', result.stderr + result.stdout)
        if version and 21 <= int(version.group(1)) <= 25:
            return executable
    raise RuntimeError('Set PAPERFLOW_JAVA_HOME to a JDK from 21 through 25.')


class Client:
    def __init__(self, base: str):
        self.base = base
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.headers: dict[str, str] = {}
        self.checks = 0

    def request(self, method, path, payload=None, expected=200, csrf=True):
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        if csrf:
            headers.update(self.headers)
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as response:
            status, raw = response.code, response.read()
        if status != expected:
            raise AssertionError(f'{method} {path}: expected HTTP {expected}, got {status}')
        self.checks += 1
        if not raw:
            return None
        result = json.loads(raw)
        if isinstance(result, dict) and 'code' in result:
            if status < 400:
                assert result['code'] == 1, 'Expected successful Result wrapper'
                return result['data']
            assert result['code'] == 0, 'Expected safe Result error wrapper'
        return result

    def refresh_csrf(self):
        token = self.request('GET', '/api/auth/csrf')
        self.headers = {token['header_name']: token['token']}

    def session_id(self):
        return next((c.value for c in self.cookies if c.name == 'paperflow_java_session'), None)


def main():
    java = project_java()
    jar = BACKEND / 'target' / 'paperflow-business-0.1.0.jar'
    if not jar.is_file():
        raise RuntimeError('Build the service with scripts/dev.ps1 -Action Package first.')
    tool_root = ROOT / '.tools'
    tool_root.mkdir(exist_ok=True)
    process = None
    total_checks = 0
    with tempfile.TemporaryDirectory(prefix='java_smoke_', dir=tool_root) as temporary:
        work = Path(temporary)
        database = work / 'business'
        jdbc = f'jdbc:h2:file:{database.as_posix()};MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_ON_EXIT=FALSE;WRITE_DELAY=0'
        suffix = uuid.uuid4().hex[:10]
        credentials_a = {'username': f'learner_a_{suffix}', 'email': f'a_{suffix}@example.test', 'password': 'local-study-pass-123'}
        credentials_b = {'username': f'learner_b_{suffix}', 'email': f'b_{suffix}@example.test', 'password': 'local-study-pass-456'}

        def stop():
            nonlocal process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            process = None

        def start(log):
            nonlocal process
            with socket.socket() as port_socket:
                port_socket.bind(('127.0.0.1', 0))
                port = port_socket.getsockname()[1]
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen([
                str(java), '-jar', str(jar), '--spring.profiles.active=local',
                '--server.address=127.0.0.1', f'--server.port={port}',
                f'--spring.datasource.url={jdbc}',
            ], cwd=BACKEND, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            base = f'http://127.0.0.1:{port}'
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError('Java service exited before readiness. Check the smoke log.')
                try:
                    with urllib.request.urlopen(base + '/api/auth/csrf', timeout=1) as response:
                        if response.status == 200:
                            return base
                except (urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.3)
            raise RuntimeError('Java service did not become ready within 60 seconds.')

        log_path = tool_root / 'java-phase2-smoke.log'
        try:
            with log_path.open('w', encoding='utf-8') as log:
                base = start(log)
                a, b = Client(base), Client(base)
                a.request('GET', '/api/auth/me', expected=401)
                a.request('POST', '/api/auth/register', credentials_a, expected=403, csrf=False)
                a.refresh_csrf()
                old_session = a.session_id()
                a.request('POST', '/api/auth/register', credentials_a, expected=201)
                if not a.session_id() or a.session_id() == old_session:
                    raise AssertionError('Authentication must rotate the session identifier')
                a.request('POST', '/api/library/collections', {'name': 'same name'}, expected=403)
                a.refresh_csrf()
                collection_a = a.request('POST', '/api/library/collections', {'name': 'same name', 'description': 'A private notes'}, expected=201)
                b.refresh_csrf()
                b.request('POST', '/api/auth/register', credentials_b, expected=201)
                b.refresh_csrf()
                collection_b = b.request('POST', '/api/library/collections', {'name': 'same name'}, expected=201)
                if collection_a['id'] == collection_b['id']:
                    raise AssertionError('Same collection names must remain separate across users')
                path_a = f"/api/library/collections/{collection_a['id']}"
                path_b = f"/api/library/collections/{collection_b['id']}"
                listed_a = a.request('GET', '/api/library/collections')
                listed_b = b.request('GET', '/api/library/collections')
                if [c['id'] for c in listed_a['collections']] != [collection_a['id']]:
                    raise AssertionError('User A list must contain only A resources')
                if [c['id'] for c in listed_b['collections']] != [collection_b['id']]:
                    raise AssertionError('User B list must contain only B resources')
                paper = {'source': 'manual', 'paper_id': f'study-{suffix}', 'title': 'Agent evidence study',
                         'abstract': 'Manual metadata for integration verification.', 'authors': ['Researcher'],
                         'categories': ['cs.AI'], 'page_url': 'https://example.test/paper'}
                attached = a.request('POST', path_a + '/papers', paper, expected=201)
                a.request('PUT', path_a + '/note', {'content': '收藏夹笔记：保留证据与研究问题。'})
                a.request('PUT', path_a + '/paper-note', {'source': paper['source'], 'paper_id': paper['paper_id'], 'content': 'A private paper note'})
                b.request('GET', path_a, expected=404)
                b.request('PUT', path_a + '/note', {'content': 'forbidden'}, expected=404)
                b.request('POST', path_a + '/papers', paper, expected=404)
                b.request('DELETE', path_a, expected=404)
                b.request('POST', path_b + '/papers', paper, expected=201)
                if b.request('GET', path_b)['papers'][0]['note']:
                    raise AssertionError('Paper notes must not be shared across owners')
                a.request('POST', path_a + '/papers', paper, expected=201)
                if a.request('GET', path_a)['papers'][0]['note'] != 'A private paper note':
                    raise AssertionError('Repeated paper attachment must preserve notes')
                b.request('DELETE', path_b + f"/papers/{attached['id']}", expected=204)
                if len(a.request('GET', path_a)['papers']) != 1:
                    raise AssertionError('Removing another membership must preserve A paper')
                total_checks += a.checks + b.checks
                stop()
                base = start(log)
                restarted = Client(base)
                restarted.refresh_csrf()
                restarted.request('POST', '/api/auth/login', {'identifier': credentials_a['email'].upper(), 'password': credentials_a['password']})
                restarted.refresh_csrf()
                detail = restarted.request('GET', path_a)
                if detail['overall_note'] != '收藏夹笔记：保留证据与研究问题。' or detail['papers'][0]['note'] != 'A private paper note':
                    raise AssertionError('Committed notes must survive application restart')
                restarted.request('POST', '/api/auth/logout', expected=204)
                restarted.request('GET', '/api/auth/me', expected=401)
                total_checks += restarted.checks
        finally:
            stop()
    summary = {'status': 'passed', 'http_checks': total_checks, 'server_restarts': 1,
               'database': 'temporary H2 file', 'external_services_required': False}
    (tool_root / 'java-phase2-smoke.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
