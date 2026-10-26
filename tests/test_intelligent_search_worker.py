"""Real worker HTTP/ledger with explicitly controlled planner and source boundaries."""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from contextlib import closing
from uuid import uuid4
from fastapi.testclient import TestClient
from paper_agent.interfaces.worker import create_app
from paper_agent.services.intelligent_search import IntelligentSearchService
from test_intelligent_search import FakeAgent, paper

TOKEN='search-agent-test-service-token-at-least-32-characters'
HEADERS={'Authorization':'Bearer '+TOKEN}
BODY={'contract_version':1,'topic':'多模态情绪识别 seediv seedvii','limit':10,'task_type':'search',
      'options':{'mode':'live','rag':'none','provider':'qwen','credential_source':'personal'},
      'runtime_credentials':{'provider':'qwen','api_key':'controlled-placeholder-not-a-real-key'}}


class IntelligentSearchWorkerTest(unittest.TestCase):
    def finished(self,client,tid):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            value=client.get('/internal/v1/tasks/'+tid,headers=HEADERS).json()
            if value['status'] not in ('queued','running'): return value
            time.sleep(.01)
        self.fail('controlled search did not finish')

    def test_completed_report_persists_without_runtime_secret_and_replays(self):
        async def retrieve(q,source,*args,**kwargs):
            return {'papers':[paper(source,'SEED-IV Fusion','EEG and eye movement on SEED-IV',source)]}
        def factory(options):
            return IntelligentSearchService(options,agent=FakeAgent(),search_page=retrieve)
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'tasks.sqlite3'; tid=str(uuid4())
            with TestClient(create_app(db,service_token=TOKEN,intelligent_search_factory=factory)) as client:
                url='/internal/v1/tasks/'+tid
                self.assertEqual(client.post(url,headers=HEADERS,json=BODY).status_code,202)
                report=self.finished(client,tid)
                self.assertEqual(report['status'],'completed')
                self.assertEqual(report['report']['report_type'],'search_report')
                self.assertEqual(len(report['report']['results']),2)
                self.assertTrue(report['events'])
                self.assertEqual(client.post(url,headers=HEADERS,json=BODY).status_code,200)
                self.assertNotIn('controlled-placeholder',json.dumps(report))
            with closing(sqlite3.connect(db)) as conn:
                payload=conn.execute('select payload from worker_tasks').fetchone()[0]
                self.assertNotIn('runtime_credentials',payload)
                self.assertNotIn('controlled-placeholder',payload)
            with TestClient(create_app(db,service_token=TOKEN,intelligent_search_factory=factory)) as client:
                self.assertEqual(self.finished(client,tid),report)

    def test_invalid_mode_and_selected_papers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with TestClient(create_app(Path(temp)/'tasks.sqlite3',service_token=TOKEN)) as client:
                url='/internal/v1/tasks/'+str(uuid4())
                invalid={**BODY,'options':{**BODY['options'],'mode':'demo'}}
                self.assertEqual(client.post(url,headers=HEADERS,json=invalid).status_code,422)
                invalid={**BODY,'papers':[paper('one','Title')]}
                self.assertEqual(client.post(url,headers=HEADERS,json=invalid).status_code,422)

    def test_model_failure_has_search_error_code_and_safe_message(self):
        class Broken:
            async def run(self,*args,**kwargs): raise RuntimeError('private-key-or-upstream-body')
        with tempfile.TemporaryDirectory() as temp:
            with TestClient(create_app(Path(temp)/'tasks.sqlite3',service_token=TOKEN,
                    intelligent_search_factory=lambda options:Broken())) as client:
                tid=str(uuid4())
                self.assertEqual(client.post('/internal/v1/tasks/'+tid,headers=HEADERS,json=BODY).status_code,202)
                result=self.finished(client,tid)
                self.assertEqual(result['error_code'],'search_failed')
                self.assertNotIn('private-key',json.dumps(result))


if __name__=='__main__': unittest.main()
