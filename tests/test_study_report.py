import asyncio
import importlib
import importlib.util
import io
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from paper_agent.core.models import Paper, EvidenceChunk
from paper_agent.services.research import ResearchOptions
from paper_agent.tools.rag import VectorIndex, HashingEmbedder


def memory_index():
    return VectorIndex(HashingEmbedder())

TOKEN = 'study-test-service-token-at-least-32-characters'
HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def paper(identifier='p1'):
    return Paper(paper_id=identifier, source='arxiv', title='Test paper '+identifier,
                 authors=['Author'], abstract='Abstract is not full text.',
                 page_url='https://arxiv.org/abs/2601.00001',
                 pdf_url='https://arxiv.org/pdf/2601.00001')


def analysis(p, evidence):
    return dict(paper_id=p.paper_id, title=p.title, overview='论文概述', background='研究背景与问题',
                methods=[dict(name='编码器', purpose='表示学习', inputs='数据', outputs='表示')],
                innovations=['联合学习'], results=['正文未提供可核实数字'],
                reflection=['建议先学习表示学习，不表示用户已完成复现。'],
                citations=[dict(chunk_id=evidence[0].chunk_id, page_number=1,
                                source_url=evidence[0].source_url)])


class FakeLoader:
    async def load(self, p):
        return [EvidenceChunk(chunk_id=p.paper_id+':p1:0', paper_id=p.paper_id,
                              text='Full paper method and experiments.', page_number=1,
                              source_url=p.pdf_url)]


class FakeTeam:
    def __init__(self):
        self.received = []

    async def analyze(self, p, evidence, learning_goal, notes, reflection):
        self.received.append((learning_goal, notes, reflection))
        return analysis(p, evidence)

    async def synthesize(self, topic, analyses, learning_goal):
        return {'synthesis': ['方法对比'], 'learning_plan': ['阅读正文并尝试复现。']}


class StudyReportTests(unittest.IsolatedAsyncioTestCase):
    def modules(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.services.study'),
                             'Dedicated evidence-grounded study report service is required')
        return importlib.import_module('paper_agent.services.study')

    async def test_selected_papers_notes_and_goal_survive_structured_analysis(self):
        module = self.modules()
        team = FakeTeam()
        events = []
        async def emit(event):
            events.append(event)
        report = await module.StudyService(ResearchOptions(mode='live'), loader=FakeLoader(), team=team, index=memory_index()).run(
            '学习多模态', papers=[paper(), paper('p2')], notes={'p1': '我的笔记'},
            learning_goal='理解模块', reflection='我的疑问', on_event=emit)
        self.assertEqual([a.paper_id for a in report.analyses], ['p1', 'p2'])
        self.assertEqual(report.report_type, 'study_report')
        self.assertEqual(report.evidence_mode, 'pdf')
        self.assertEqual(team.received[0], ('理解模块', '我的笔记', '我的疑问'))
        self.assertTrue(report.synthesis)
        self.assertTrue(any(e.stage == 'index' for e in events))

    async def test_topic_reaches_analyst_when_learning_goal_is_blank(self):
        module = self.modules()
        topic = 'Analyze architecture, innovations, results and limitations.'
        for blank_goal in ('', '   '):
            with self.subTest(learning_goal=blank_goal):
                team = FakeTeam()
                await module.StudyService(loader=FakeLoader(), team=team, index=memory_index()).run(
                    topic, papers=[paper()], learning_goal=blank_goal)
                self.assertEqual(team.received[0][0], topic)

    async def test_pdf_failure_never_falls_back_to_abstract(self):
        module = self.modules()
        class BrokenLoader:
            async def load(self, p):
                raise RuntimeError('secret-private-url')
        with self.assertRaisesRegex(module.StudyEvidenceError, 'Test paper p1.*PDF') as raised:
            await module.StudyService(loader=BrokenLoader(), team=FakeTeam(), index=memory_index()).run('topic', papers=[paper()])
        self.assertNotIn('secret', str(raised.exception))

    async def test_partial_failure_does_not_omit_second_selected_paper(self):
        module = self.modules()
        class PartialLoader(FakeLoader):
            async def load(self, p):
                if p.paper_id == 'p2':
                    raise RuntimeError('upstream-secret')
                return await super().load(p)
        with self.assertRaisesRegex(module.StudyEvidenceError, 'Test paper p2'):
            await module.StudyService(loader=PartialLoader(), team=FakeTeam(), index=memory_index()).run(
                'topic', papers=[paper(), paper('p2')])

    async def test_missing_live_model_key_is_explicit_and_never_uses_demo(self):
        module = self.modules()
        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': ''}):
            with self.assertRaisesRegex(ValueError, '个人设置.*DASHSCOPE_API_KEY'):
                await module.StudyService(loader=FakeLoader()).run('topic', papers=[paper()])

    async def test_foreign_paper_identity_and_fabricated_evidence_fail(self):
        module = self.modules()
        class BadTeam(FakeTeam):
            async def analyze(self, p, evidence, *args):
                value = analysis(p, evidence)
                value['citations'][0]['chunk_id'] = 'other-paper'
                return value
        with self.assertRaisesRegex(module.StudyEvidenceError, '证据'):
            await module.StudyService(loader=FakeLoader(), team=BadTeam(), index=memory_index()).run('topic', papers=[paper()])
        class WrongPaper(FakeTeam):
            async def analyze(self, p, evidence, *args):
                value = analysis(p, evidence)
                value['paper_id'] = 'another-paper'
                return value
        with self.assertRaises(module.StudyEvidenceError):
            await module.StudyService(loader=FakeLoader(), team=WrongPaper(), index=memory_index()).run('topic', papers=[paper()])

    async def test_document_export_contains_requested_sections_and_chinese_style(self):
        module = self.modules()
        report = await module.StudyService(loader=FakeLoader(), team=FakeTeam(), index=memory_index()).run('学习报告', papers=[paper()])
        from paper_agent.interfaces.study_document import render_study_document
        content = render_study_document(report)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read('word/document.xml').decode()
            styles = archive.read('word/styles.xml').decode()
        for expected in ['论文概述', '研究背景与问题', '模型方法', '创新点', '学习体会', '编码器', 'https://arxiv.org/pdf/2601.00001']:
            self.assertIn(expected, xml)
        self.assertIn('宋体', styles)

    async def test_pdf_loader_rejects_non_https_private_dns_and_unsafe_redirects(self):
        self.modules()
        from paper_agent.tools.study_pdf import StudyPDFLoader
        for url in ['http://arxiv.org/paper.pdf', 'https://127.0.0.1/x.pdf',
                    'https://[::1]/x.pdf', 'https://user:password@arxiv.org/x.pdf']:
            p = paper().model_copy(update={'pdf_url': url})
            with self.assertRaises(ValueError):
                await StudyPDFLoader().load(p)
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.0.0.4', 443))]):
            with self.assertRaises(ValueError):
                await StudyPDFLoader().load(paper())

    async def test_canonical_arxiv_http_pdf_is_upgraded_to_https_before_fetch(self):
        self.modules()
        from paper_agent.tools.study_pdf import StudyPDFLoader
        p = paper().model_copy(update={'pdf_url': 'http://arxiv.org/pdf/2601.00001v1'})
        expected = 'https://arxiv.org/pdf/2601.00001v1'
        def fetch(url):
            self.assertEqual(url, expected)
            return b'%PDF-fixture', expected
        with patch('paper_agent.tools.study_pdf._fetch_public_pdf', side_effect=fetch), \
                patch('paper_agent.tools.study_pdf._extract_pdf', return_value=[]):
            await StudyPDFLoader().load(p)

    async def test_pdf_http_redirect_and_declared_stream_size_are_bounded(self):
        self.modules()
        from paper_agent.tools.study_pdf import _fetch_public_pdf, MAX_PDF_BYTES
        class Response:
            status = 302
            def getheader(self, name):
                return 'https://127.0.0.1/private.pdf' if name == 'Location' else None
        class Connection:
            def __init__(self, *args):
                pass
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return Response()
            def close(self):
                pass
        def resolve(host, *args, **kwargs):
            return [(2, 1, 6, '', ('127.0.0.1' if host == '127.0.0.1' else '1.1.1.1', 443))]
        with patch('socket.getaddrinfo', side_effect=resolve), \
                patch('paper_agent.tools.study_pdf._PinnedHTTPSConnection', Connection):
            with self.assertRaisesRegex(ValueError, 'public'):
                _fetch_public_pdf('https://papers.example/test.pdf')
            Response.status = 200
            Response.getheader = lambda self, name: str(MAX_PDF_BYTES+1) if name == 'Content-Length' else None
            with self.assertRaisesRegex(ValueError, 'limit'):
                _fetch_public_pdf('https://papers.example/test.pdf')

    async def test_pdf_parser_rejects_unreadable_and_excessive_page_documents(self):
        self.modules()
        from pypdf import PdfWriter
        from paper_agent.tools.study_pdf import _extract_pdf, MAX_PAGES
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        target = io.BytesIO()
        writer.write(target)
        with self.assertRaisesRegex(ValueError, 'readable'):
            _extract_pdf(target.getvalue(), paper(), paper().pdf_url)
        for _ in range(MAX_PAGES):
            writer.add_blank_page(width=200, height=200)
        target = io.BytesIO()
        writer.write(target)
        with self.assertRaisesRegex(ValueError, 'page count'):
            _extract_pdf(target.getvalue(), paper(), paper().pdf_url)


class StudyWorkerTests(unittest.TestCase):
    def test_saved_fifty_thousand_character_notes_match_existing_library_limits(self):
        from paper_agent.interfaces.worker import TaskInput
        body = dict(contract_version=1, task_type='study_report', topic='学习报告',
            options=dict(mode='live', provider='qwen'), papers=[paper().model_dump()],
            notes={'p1': 'n' * 50000}, collection_note='c' * 50000, reflection='r' * 50000)
        try:
            value = TaskInput.model_validate(body)
        except ValueError:
            self.fail('Existing library notes up to 50000 characters must remain valid study snapshots')
        self.assertEqual(len(value.notes['p1']), 50000)

    def test_pdf_failure_exposes_safe_paper_specific_hint(self):
        from paper_agent.interfaces.worker import create_app
        from paper_agent.services.study import StudyService
        class BrokenLoader:
            async def load(self, p):
                raise RuntimeError('sk-network-secret private-path')
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory)/'worker.db', service_token=TOKEN,
                study_factory=lambda options: StudyService(options, loader=BrokenLoader(), team=FakeTeam(), index=memory_index()))
            with TestClient(app) as client:
                body = dict(contract_version=1, task_type='study_report', topic='学习报告',
                    options=dict(mode='live', provider='qwen'), papers=[paper().model_dump()])
                identifier = str(uuid4())
                client.post('/internal/v1/tasks/'+identifier, json=body, headers=HEADERS)
                for _ in range(100):
                    value = client.get('/internal/v1/tasks/'+identifier, headers=HEADERS).json()
                    if value['status'] not in ['queued', 'running']:
                        break
                    time.sleep(.01)
                self.assertEqual(value['status'], 'failed')
                self.assertEqual(value['error_code'], 'study_report_failed')
                self.assertIn('Test paper p1', value['error_message'])
                self.assertIn('PDF', value['error_message'])
                self.assertNotIn('secret', value['error_message'])

    def test_study_worker_dispatch_and_authenticated_snapshot_document(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.services.study'))
        from paper_agent.interfaces.worker import create_app
        from paper_agent.services.study import StudyService
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory)/'worker.db', service_token=TOKEN,
                study_factory=lambda options: StudyService(options, loader=FakeLoader(), team=FakeTeam(), index=memory_index()))
            with TestClient(app) as client:
                body = dict(contract_version=1, task_type='study_report', topic='学习报告',
                            options=dict(mode='live', rag='abstract', provider='qwen'),
                            papers=[paper().model_dump()], learning_goal='模块', reflection='', notes={'p1':'笔记'})
                identifier = str(uuid4())
                self.assertEqual(client.post('/internal/v1/tasks/'+identifier, json=body, headers=HEADERS).status_code, 202)
                for _ in range(100):
                    result = client.get('/internal/v1/tasks/'+identifier, headers=HEADERS).json()
                    if result['status'] not in ['queued', 'running']:
                        break
                    time.sleep(.01)
                self.assertEqual(result['status'], 'completed', result)
                endpoint = '/internal/v1/study-reports/document'
                self.assertEqual(client.post(endpoint, json=result['report']).status_code, 401)
                document = client.post(endpoint, json=result['report'], headers=HEADERS)
                self.assertEqual(document.status_code, 200, document.text[:100] if document.status_code != 200 else '')
                self.assertTrue(document.content.startswith(b'PK'))
                body['papers'] = None
                self.assertEqual(client.post('/internal/v1/tasks/'+str(uuid4()), json=body, headers=HEADERS).status_code, 422)

    def test_injected_foreign_report_is_not_persisted_as_completed(self):
        from paper_agent.interfaces.worker import create_app
        from paper_agent.services.study import StudyService
        class ForeignService:
            async def run(self, topic, **kwargs):
                return await StudyService(loader=FakeLoader(), team=FakeTeam(), index=memory_index()).run(topic, papers=[paper('foreign')])
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(db_path=Path(directory)/'worker.db', service_token=TOKEN,
                study_factory=lambda options: ForeignService())
            with TestClient(app) as client:
                body = dict(contract_version=1, task_type='study_report', topic='学习报告',
                    options=dict(mode='live', provider='qwen'), papers=[paper().model_dump()])
                identifier = str(uuid4())
                client.post('/internal/v1/tasks/'+identifier, json=body, headers=HEADERS)
                for _ in range(100):
                    result = client.get('/internal/v1/tasks/'+identifier, headers=HEADERS).json()
                    if result['status'] not in ['queued', 'running']:
                        break
                    time.sleep(.01)
                self.assertEqual(result['status'], 'failed', 'Worker must validate selected paper identities even for injected services')
                self.assertIsNone(result['report'])
