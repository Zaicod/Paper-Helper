import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4
from contextlib import closing
from fastapi.testclient import TestClient
from paper_agent.interfaces.worker import create_app
from paper_agent.services.citation_tracking import CitationTrackingService
from test_citation_tracking import Agent, Graph, seed

TOKEN='citation-test-service-token-at-least-32-characters'
HEADERS={'Authorization':'Bearer '+TOKEN}
BODY={'contract_version':1,'topic':'SEED-IV emotion recognition','limit':10,'task_type':'citation_trace',
    'citation_direction':'both','papers':[seed(1).model_dump()], 'index_namespace':'java-user:1',
    'options':{'mode':'live','rag':'none','provider':'qwen','credential_source':'personal'},
    'runtime_credentials':{'provider':'qwen','api_key':'controlled-placeholder-not-real'}}


class CitationWorkerTests(unittest.TestCase):
    def finished(self, client, tid):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=client.get('/internal/v1/tasks/'+tid,headers=HEADERS).json()
            if result['status'] not in ('queued','running'): return result
            time.sleep(.01)
        self.fail('Task did not complete')

    def test_authenticated_task_runs_and_persists_safe_snapshot_with_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'tasks.sqlite3'
            with TestClient(create_app(db,service_token=TOKEN,citation_factory=lambda options:
                    CitationTrackingService(options,agent=Agent(),graph=Graph()))) as client:
                tid=str(uuid4()); url='/internal/v1/tasks/'+tid
                self.assertEqual(client.post(url,json=BODY).status_code,401)
                self.assertEqual(client.post(url,json=BODY,headers=HEADERS).status_code,202)
                value=self.finished(client,tid)
                self.assertEqual(value['status'],'completed')
                self.assertEqual(value['report']['report_type'],'citation_report')
                self.assertEqual(value['report']['seeds'],BODY['papers'])
                self.assertEqual(len(value['report']['results']),2)
                self.assertEqual(client.post(url,json=BODY,headers=HEADERS).status_code,200)
                with closing(sqlite3.connect(db)) as conn:
                    payload=conn.execute('select payload from worker_tasks').fetchone()[0]
                    self.assertNotIn('runtime_credentials',payload)
                    self.assertNotIn('controlled-placeholder',payload)

    def test_invalid_seed_count_mode_direction_namespace_and_old_task_direction(self):
        with tempfile.TemporaryDirectory() as temp:
            with TestClient(create_app(Path(temp)/'tasks.sqlite3',service_token=TOKEN)) as client:
                invalid=[{**BODY,'papers':[]},{**BODY,'papers':[seed(n).model_dump() for n in range(1,7)]},
                    {**BODY,'citation_direction':'bad'},{**BODY,'index_namespace':None},
                    {**BODY,'options':{**BODY['options'],'mode':'demo'}},
                    {**BODY,'options':{**BODY['options'],'credential_source':'server'}},
                    {**BODY,'options':{**BODY['options'],'rag':'abstract'}},
                    {**BODY,'task_type':'research'}]
                for body in invalid:
                    with self.subTest(body=body):
                        self.assertEqual(client.post('/internal/v1/tasks/'+str(uuid4()),json=body,headers=HEADERS).status_code,422)

    def test_report_seed_snapshot_mismatch_is_rejected_and_internal_error_is_safe(self):
        class Wrong:
            async def run(self,*args,**kwargs):
                return await CitationTrackingService(agent=Agent(),graph=Graph()).run('changed topic',papers=[seed(2)])
        with tempfile.TemporaryDirectory() as temp:
            with TestClient(create_app(Path(temp)/'tasks.sqlite3',service_token=TOKEN,citation_factory=lambda options:Wrong())) as client:
                tid=str(uuid4()); client.post('/internal/v1/tasks/'+tid,json=BODY,headers=HEADERS)
                value=self.finished(client,tid)
                self.assertEqual(value['status'],'failed')
                self.assertEqual(value['error_code'],'citation_trace_failed')
                self.assertNotIn('ValueError',json.dumps(value))
