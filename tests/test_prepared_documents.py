"""Private PDF preparation with controlled network and actual PDF extraction."""
import asyncio
from contextlib import closing
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from paper_agent.core.models import Paper
from paper_agent.tools.prepared_documents import PreparedDocumentStore, PreparedPDFLoader


def paper(**update):
    return Paper(paper_id='W7131315593',source='openalex',title='MMSTG-Net controlled test',authors=['Author'],
        abstract='Controlled metadata',page_url='https://doi.org/10.1109/JBHI.2026.3667946',**update)


def pdf_bytes(text=None):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
    writer=PdfWriter();page=writer.add_blank_page(width=600,height=800)
    if text is not None:
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        content=DecodedStreamObject();content.set_data(('BT /F1 12 Tf 30 750 Td ('+text+') Tj ET').encode('ascii'))
        page[NameObject('/Contents')]=writer._add_object(content)
    output=BytesIO();writer.write(output);return output.getvalue()


TEXT='This paper studies the model architecture, innovation, experimental results and limitations. '*8


class PreparedDocumentsTest(unittest.IsolatedAsyncioTestCase):
    async def test_uploaded_pdf_is_private_immutable_and_fingerprint_bound(self):
        async def no_network(p): self.fail('upload must not resolve remote metadata')
        with tempfile.TemporaryDirectory() as temp:
            store=PreparedDocumentStore(Path(temp),resolver=no_network)
            upload=await store.upload('java-user:7','paper.pdf',pdf_bytes(TEXT))
            prepared=await store.prepare('java-user:7',paper(),upload_id=upload)
            self.assertEqual(prepared['status'],'ready')
            self.assertEqual(prepared['source_kind'],'uploaded')
            loader=PreparedPDFLoader(store,'java-user:7',{'W7131315593':prepared['document_id']})
            chunks=await loader.load(paper())
            self.assertTrue(chunks and chunks[0].page_number==1)
            self.assertEqual(chunks[0].source_url,'/api/library/documents/'+prepared['document_id']+'/file')
            with self.assertRaises(ValueError):await PreparedPDFLoader(store,'java-user:8',{'W7131315593':prepared['document_id']}).load(paper())
            with self.assertRaises(ValueError):await loader.load(paper().model_copy(update={'title':'Changed paper'}))
            second=await store.upload('java-user:7','new.pdf',pdf_bytes('Revised evidence. '*40))
            newer=await store.prepare('java-user:7',paper(),upload_id=second)
            self.assertNotEqual(newer['document_id'],prepared['document_id'])
            self.assertIn('architecture',(await loader.load(paper()))[0].text)

    async def test_missing_pdf_is_diagnosed_before_any_model_or_file_fetch(self):
        async def empty(p):return []
        def fetch(url):self.fail('no candidate URL means no download')
        with tempfile.TemporaryDirectory() as temp:
            status=await PreparedDocumentStore(Path(temp),resolver=empty,fetcher=fetch).prepare('java-user:7',paper())
            self.assertEqual(status['status'],'missing')
            self.assertIsNone(status['document_id'])

    async def test_verified_oa_location_can_supply_missing_pdf(self):
        async def resolve(p):return ['https://example.org/open.pdf']
        def fetch(url):return pdf_bytes(TEXT),url
        with tempfile.TemporaryDirectory() as temp:
            store=PreparedDocumentStore(Path(temp),resolver=resolve,fetcher=fetch)
            status=await store.prepare('java-user:7',paper())
            self.assertEqual(status['status'],'ready')
            chunks=await PreparedPDFLoader(store,'java-user:7',{'W7131315593':status['document_id']}).load(paper())
            self.assertEqual(chunks[0].source_url,'https://example.org/open.pdf')

    async def test_invalid_and_scanned_pdf_have_distinct_safe_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            store=PreparedDocumentStore(Path(temp))
            with self.assertRaises(ValueError):await store.upload('java-user:7','bad.pdf',b'not a pdf')
            upload=await store.upload('java-user:7','scan.pdf',pdf_bytes())
            result=await store.prepare('java-user:7',paper(),upload_id=upload)
            self.assertEqual(result['status'],'unreadable')
            self.assertIn('文本',result['message'])
            with self.assertRaises(ValueError):await store.upload('../private','test.pdf',pdf_bytes(TEXT))
            with self.assertRaises(ValueError):await store.read_pdf('java-user:7','../../outside')

    async def test_foreign_upload_and_tampered_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store=PreparedDocumentStore(Path(temp))
            upload=await store.upload('java-user:7','paper.pdf',pdf_bytes(TEXT))
            with self.assertRaises(ValueError):await store.prepare('java-user:8',paper(),upload_id=upload)
            status=await store.prepare('java-user:7',paper(),upload_id=upload)
            file=Path(temp)/(status['document_id']+'.pdf');file.write_bytes(b'%PDF-tampered')
            with self.assertRaises(ValueError):await store.read_pdf('java-user:7',status['document_id'])

    async def test_resolver_requires_matching_identity_and_explicit_oa_pdf(self):
        from paper_agent.tools.prepared_documents import resolve_open_pdf_candidates
        import httpx
        seen=[]
        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(200,json={'id':'https://openalex.org/W7131315593','doi':'https://doi.org/10.1109/JBHI.2026.3667946',
                'best_oa_location':{'pdf_url':'https://example.org/right.pdf','is_oa':True},
                'locations':[{'is_oa':True,'landing_page_url':'https://example.org/html'},
                             {'is_oa':False,'pdf_url':'https://example.org/closed.pdf'}]})
        result=await resolve_open_pdf_candidates(paper(),transport=httpx.MockTransport(handler))
        self.assertEqual(result,['https://example.org/right.pdf'])
        def foreign(request):return httpx.Response(200,json={'id':'https://openalex.org/W123','doi':'https://doi.org/10.1000/other','best_oa_location':{'pdf_url':'https://example.org/wrong.pdf','is_oa':True}})
        self.assertEqual(await resolve_open_pdf_candidates(paper(),transport=httpx.MockTransport(foreign)),[])

    async def test_repeated_upload_and_preparation_reuse_same_immutable_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=PreparedDocumentStore(Path(tmp))
            content=pdf_bytes(TEXT)
            first=await store.upload('java-user:7','paper.pdf',content)
            again=await store.upload('java-user:7','paper.pdf',content)
            self.assertEqual(first,again)
            one=await store.prepare('java-user:7',paper(),upload_id=first)
            two=await store.prepare('java-user:7',paper(),upload_id=again)
            self.assertEqual(one['document_id'],two['document_id'])

    async def test_prepared_versions_use_separate_vector_cache_recipes(self):
        from paper_agent.services.study import StudyService
        from test_study_report import FakeTeam
        class Index:
            def __init__(self):
                from paper_agent.tools.rag import HashingEmbedder
                self.embedder=HashingEmbedder();self.recipes=[];self.chunks=[]
            def reset_active(self):pass
            async def load_paper(self,p,mode,recipe):self.recipes.append(recipe);return False
            async def replace_paper(self,p,chunks,*args):self.chunks=chunks
            async def search(self,*args,**kwargs):return self.chunks
        with tempfile.TemporaryDirectory() as tmp:
            store=PreparedDocumentStore(Path(tmp));index=Index()
            for text in [TEXT,'Revised full paper evidence. '*30]:
                uploaded=await store.upload('java-user:7','paper.pdf',pdf_bytes(text))
                status=await store.prepare('java-user:7',paper(),upload_id=uploaded)
                loader=PreparedPDFLoader(store,'java-user:7',{paper().paper_id:status['document_id']})
                await StudyService(loader=loader,team=FakeTeam(),index=index).run('topic',papers=[paper()])
            self.assertNotEqual(index.recipes[0],index.recipes[1])

    async def test_restricted_http_source_is_blocked_rather_than_scanned_pdf(self):
        from paper_agent.tools.study_pdf import _fetch_public_pdf
        class Response:
            status=403
            def getheader(self,name):return None
        class Connection:
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return Response()
            def close(self):pass
        async def empty(p):return []
        with tempfile.TemporaryDirectory() as tmp:
            store=PreparedDocumentStore(Path(tmp),resolver=empty)
            with patch('paper_agent.tools.study_pdf._public_target',return_value=('example.org','1.1.1.1','/file.pdf')),patch('paper_agent.tools.study_pdf._PinnedHTTPSConnection',Connection):
                status=await store.prepare('java-user:7',paper(pdf_url='https://example.org/file.pdf'))
            self.assertEqual(status['status'],'blocked')


if __name__=='__main__':unittest.main()
