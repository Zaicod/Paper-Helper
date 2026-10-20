"""Exercise Vue, the packaged Java backend and the real Python Agent worker.

Requires the project's Python environment, packaged Java service, installed
frontend dependencies and Playwright Chromium. No live model credentials are
used. Only processes started by this script are stopped.
"""
from __future__ import annotations

from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'frontend-vue'
sys.path.insert(0, str(ROOT / 'java-backend' / 'scripts'))
from smoke import project_java  # noqa: E402


def free_port(used: set[int]) -> int:
    while True:
        with socket.socket() as handle:
            handle.bind(('127.0.0.1', 0))
            port = handle.getsockname()[1]
        if port not in used:
            used.add(port)
            return port


def main(search_test=False, model_settings_test=False):
    tools = ROOT / '.tools'
    tools.mkdir(exist_ok=True)
    prefix = 'model-settings-e2e' if model_settings_test else 'paper-search-e2e' if search_test else 'vue-e2e'
    output = tools / prefix if search_test or model_settings_test else tools
    output.mkdir(exist_ok=True)
    summary_path = tools / (prefix + '-smoke.json')
    summary_path.unlink(missing_ok=True)
    node = shutil.which('node')
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    jar = ROOT / 'java-backend' / 'target' / 'paperflow-business-0.1.0.jar'
    vite = FRONTEND / 'node_modules' / 'vite' / 'bin' / 'vite.js'
    playwright = FRONTEND / 'node_modules' / '@playwright' / 'test' / 'cli.js'
    if not node or not all(path.is_file() for path in (python, jar, vite, playwright)):
        raise RuntimeError('Prepare Python, package Java, install frontend dependencies and Playwright Chromium first.')
    java = project_java()
    used: set[int] = set()
    worker_port, java_port, vite_port = (free_port(used) for _ in range(3))
    worker_url, java_url, vite_url = (f'http://127.0.0.1:{port}' for port in (worker_port, java_port, vite_port))
    processes: list[subprocess.Popen] = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def stop():
        for process in reversed(processes):
            if process.poll() is not None:
                continue
            if os.name == 'nt':
                # Numeric IDs come directly from our own Popen objects. /T also
                # closes browser child processes if a test timed out.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=flags, timeout=20, check=False)
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        processes.clear()

    def wait_ready(process, url, expected=200):
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'A service exited before readiness; inspect .tools/{prefix}-*.log.')
            try:
                with opener.open(url, timeout=1) as response:
                    if response.status == expected:
                        return
            except urllib.error.HTTPError as response:
                if response.code == expected:
                    return
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.3)
        raise RuntimeError('A service did not become ready within 75 seconds.')

    try:
        with tempfile.TemporaryDirectory(prefix='vue_e2e_', dir=tools) as temporary, ExitStack() as stack:
            work = Path(temporary)
            # Keep packaging available while this owned service is running (Windows
            # locks an executing JAR). The temporary copy is removed with this run.
            run_jar = Path(shutil.copy2(jar, work / jar.name))
            environment = os.environ.copy()
            environment.update(PYTHONPATH=str(ROOT), PAPERFLOW_SERVICE_TOKEN=uuid.uuid4().hex + uuid.uuid4().hex,
                               PAPERFLOW_WORKER_DB=str(work / 'worker.sqlite3'), PAPERFLOW_WORKER_URL=worker_url,
                               PAPERFLOW_JAVA_URL=java_url, PAPERFLOW_E2E_BASE_URL=vite_url,
                               PAPERFLOW_E2E_OUTPUT_DIR=str(output))
            if model_settings_test:
                # Avoid reading any user's live model credentials in this run.
                for name in ('OPENAI_API_KEY', 'DASHSCOPE_API_KEY', 'OPENALEX_API_KEY'):
                    environment.pop(name, None)
            if search_test:
                environment.pop('OPENALEX_API_KEY', None)
            if 'PAPERFLOW_BROWSER_CHANNEL' not in environment:
                installed_chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
                if os.name == 'nt' and installed_chrome.is_file():
                    environment['PAPERFLOW_BROWSER_CHANNEL'] = 'chrome'
            database = work / 'business'
            jdbc = f'jdbc:h2:file:{database.as_posix()};MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_ON_EXIT=FALSE;WRITE_DELAY=0'

            def launch(name, command, cwd):
                log = stack.enter_context((tools / f'{prefix}-{name}.log').open('w', encoding='utf-8'))
                process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=log,
                                           stderr=subprocess.STDOUT, creationflags=flags)
                processes.append(process)
                return process

            try:
                worker_command = ([str(python), '-B', '-c', 'from scripts.paper_search_fixture import serve; serve()', '--port', str(worker_port)]
                                  if search_test or model_settings_test else [str(python), '-B', '-m', 'paper_agent.interfaces.worker', '--host', '127.0.0.1', '--port', str(worker_port)])
                worker = launch('worker', worker_command, work)
                wait_ready(worker, worker_url + '/internal/v1/tasks/' + str(uuid.uuid4()), 401)
                business = launch('java', [str(java), '-jar', str(run_jar), '--spring.profiles.active=local',
                                          '--server.address=127.0.0.1', f'--server.port={java_port}',
                                          f'--spring.datasource.url={jdbc}',
                                          f'--paperflow.model-settings.key-file={work / "master.key"}'], work)
                wait_ready(business, java_url + '/api/auth/csrf')
                frontend = launch('vite', [node, str(vite), '--host', '127.0.0.1', '--port', str(vite_port)], FRONTEND)
                wait_ready(frontend, vite_url + '/login')
                spec = 'model-settings.spec.ts' if model_settings_test else 'paper-search.spec.ts' if search_test else 'workspace.spec.ts'
                tests = launch('playwright', [node, str(playwright), 'test', spec], FRONTEND)
                try:
                    code = tests.wait(timeout=240)
                except subprocess.TimeoutExpired as cause:
                    raise RuntimeError(f'Browser validation timed out; inspect .tools/{prefix}-playwright.log.') from cause
                if code != 0:
                    raise RuntimeError(f'Browser validation failed; inspect .tools/{prefix}-playwright.log and {output / "vue-playwright-results.json"}.')
                if model_settings_test:
                    fake_keys = ('fixture-personal-qwen-1234', 'fixture-personal-openai-5678',
                                 'fixture-personal-qwen-other-9999')
                    with closing(sqlite3.connect(work / 'worker.sqlite3')) as ledger:
                        durable_rows = ledger.execute('SELECT payload,events,report,error_message FROM worker_tasks').fetchall()
                    if any(key in json.dumps(durable_rows) for key in fake_keys):
                        raise RuntimeError('Model credentials appeared in the durable worker ledger.')
                    for name in ('worker', 'java', 'vite'):
                        logged = (tools / f'{prefix}-{name}.log').read_text(encoding='utf-8', errors='replace')
                        if any(key in logged for key in fake_keys):
                            raise RuntimeError('Model credentials appeared in a service log.')
            finally:
                # Close databases before TemporaryDirectory removes their files.
                stop()
        summary = {'status': 'passed', 'services': ['Vue/Vite', 'Java/Spring Boot/MyBatis', 'Python/FastAPI Agent'],
                   'browser': 'Playwright Chromium', 'viewports': ['1440x1080', '390x844'],
                   'database': ['temporary H2 file', 'temporary SQLite file'], 'mocked_responses': False,
                   'live_models_tested': False, 'external_services_required': False,
                   'screenshots': ['.tools/vue-desktop.png', '.tools/vue-mobile.png']}
        if search_test:
            summary.update(upstream_source='TEST ONLY controlled arXiv/OpenAlex/Crossref HTTP fixtures', external_sources_verified=False,
                           study_generation='TEST ONLY controlled PDF evidence and Agent model boundaries; actual StudyService workflow and DOCX serializer',
                           screenshots=['.tools/paper-search-e2e/paper-search-desktop.png', '.tools/paper-search-e2e/paper-search-mobile.png'])
        if model_settings_test:
            summary.update(model_boundary='TEST ONLY saved fake-key assertion; no live model API contacted',
                           retry_checks=['failed task retries using current personal model', 'new execution preserves original failed record and selected papers'],
                           study_generation='Actual Java dispatch, Python StudyService, controlled PDF/team and real DOCX serializer',
                           credential_checks=['worker SQLite and service logs contain no fake keys', 'saved key crosses controlled model boundary', 'two-account distinct keys'],
                           screenshots=['.tools/model-settings-e2e/model-settings-desktop.png', '.tools/model-settings-e2e/model-settings-mobile.png'])
        summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary))
    except Exception as cause:
        stop()
        summary_path.write_text(json.dumps({'status': 'failed', 'error': str(cause)}, indent=2), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
