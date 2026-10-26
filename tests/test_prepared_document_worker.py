"""Authenticated binary preparation routes, with actual text PDF and no external calls."""
import tempfile
from pathlib import Path
import unittest
import time
from uuid import uuid4
from fastapi.testclient import TestClient
from paper_agent.interfaces.worker import create_app
from paper_agent.tools.prepared_documents import PreparedDocumentStore
from test_prepared_documents import paper,pdf_bytes,TEXT

TOKEN='prepared-document-controlled-token-at-least32chars'
HEADERS={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/pdf'}

class PreparedDocumentWorkerTest(unittest.TestCase):
    def test_private_upload_prepare_and_download(self):
        async def no_locations(p):return []
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(Path(tmp)/'tasks.sqlite3',service_token=TOKEN,
                document_store_factory=lambda root:PreparedDocumentStore(root,resolver=no_locations))
            with TestClient(app) as client:
                path='/internal/v1/documents/upload?namespace=java-user:7&filename=paper.pdf'
                self.assertEqual(client.post(path,content=pdf_bytes(TEXT)).status_code,401)
                upload=client.post(path,headers=HEADERS,content=pdf_bytes(TEXT))
                self.assertEqual(upload.status_code,200)
                body={'namespace':'java-user:7','paper':paper().model_dump(mode='json'),'upload_id':upload.json()['upload_id']}
                result=client.post('/internal/v1/documents/prepare',headers={'Authorization':'Bearer '+TOKEN},json=body)
                self.assertEqual(result.status_code,200)
                self.assertEqual(result.json()['status'],'ready')
                did=result.json()['document_id']
                self.assertEqual(client.get('/internal/v1/documents/'+did+'/file?namespace=java-user:7',headers=HEADERS).status_code,200)
                self.assertEqual(client.get('/internal/v1/documents/'+did+'/file?namespace=java-user:8',headers=HEADERS).status_code,404)
                self.assertEqual(client.post('/internal/v1/documents/prepare',headers={'Authorization':'Bearer '+TOKEN},json={**body,'namespace':'java-user:8'}).status_code,404)
                self.assertEqual(client.post(path,headers=HEADERS,content=b'bad').status_code,422)

    def test_upload_route_accepts_more_than_json_limit_while_other_routes_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TestClient(create_app(Path(tmp)/'tasks.sqlite3',service_token=TOKEN)) as client:
                content=pdf_bytes(TEXT)+b' '*(2*1024*1024)
                r=client.post('/internal/v1/documents/upload?namespace=java-user:7&filename=large.pdf',headers=HEADERS,content=content)
                self.assertEqual(r.status_code,200)
                self.assertEqual(client.post('/internal/v1/models/test',headers=HEADERS,content=content).status_code,413)

    def test_prepared_study_uses_uploaded_page_evidence_and_preserves_task_snapshot(self):
        from paper_agent.services.study import StudyService
        from test_study_report import FakeTeam,memory_index
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(Path(tmp)/'tasks.sqlite3',service_token=TOKEN,
                study_factory=lambda options:StudyService(options,team=FakeTeam(),index=memory_index()))
            with TestClient(app) as client:
                upload=client.post('/internal/v1/documents/upload?namespace=java-user:7&filename=paper.pdf',headers=HEADERS,content=pdf_bytes(TEXT)).json()
                status=client.post('/internal/v1/documents/prepare',headers={'Authorization':'Bearer '+TOKEN},json={
                    'namespace':'java-user:7','paper':paper().model_dump(mode='json'),'upload_id':upload['upload_id']}).json()
                task={'contract_version':1,'task_type':'study_report','topic':'分析创新与架构','limit':1,
                    'index_namespace':'java-user:7','prepared_documents':{paper().paper_id:status['document_id']},
                    'papers':[paper().model_dump(mode='json')],
                    'options':{'mode':'live','rag':'abstract','provider':'qwen','credential_source':'personal'},
                    'runtime_credentials':{'provider':'qwen','api_key':'controlled-placeholder-key'}}
                tid=str(uuid4());path='/internal/v1/tasks/'+tid
                self.assertEqual(client.post(path,headers={'Authorization':'Bearer '+TOKEN},json=task).status_code,202)
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    result=client.get(path,headers=HEADERS).json()
                    if result['status'] not in ('running','queued'):break
                    time.sleep(.01)
                self.assertEqual(result['status'],'completed',result.get('error_message'))
                report=result['report']
                self.assertEqual(report['papers'][0]['pdf_url'],None)
                self.assertIn('/api/library/documents/',report['analyses'][0]['citations'][0]['source_url'])
                self.assertNotIn('controlled-placeholder',str(report))

if __name__=='__main__':unittest.main()
