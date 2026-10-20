"""TEST ONLY: real HTTP provider fixtures for browser integration.

Normal worker startup never imports this module. This bootstrap changes only
this process's provider endpoints, while keeping the actual adapters and parser.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from urllib.parse import parse_qs, urlsplit

ARXIV_ENTRY = '''<entry>
  <id>https://arxiv.org/abs/2601.00001</id>
  <title>Controlled arXiv evidence paper</title>
  <summary>Controlled HTTP integration evidence for retrieval augmented agents. Abstract passages support auditable research synthesis.</summary>
  <published>2026-01-01T00:00:00Z</published>
  <author><name>Smith, John</name></author><author><name>陈研究员</name></author>
  <category term="cs.AI"/><link title="pdf" href="https://arxiv.org/pdf/2601.00001"/>
</entry>'''


class ProviderFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        request = urlsplit(self.path)
        query = parse_qs(request.query)
        keyword = ' '.join(query.get('search_query', query.get('search', query.get('query.bibliographic', [])))).lower().replace('\\', '')
        if 'citationfallback' in keyword and request.path == '/openalex':
            self.send_response(429); self.end_headers(); return
        if 'source-error' in keyword or ('fallback' in keyword and request.path == '/arxiv'):
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'Controlled upstream unavailable')
            return
        empty = 'no-result' in keyword
        paged = 'paged-study' in keyword or 'keywordpages' in keyword
        page_number = int(query.get('page', ['1'])[0]) if request.path == '/openalex' else int(query.get('start', ['0'])[0]) // int(query.get('max_results', ['10'])[0]) + 1
        if request.path == '/arxiv':
            entry = ARXIV_ENTRY.replace('2601.00001', f'2602.{page_number:05d}').replace('Controlled arXiv evidence paper', f'Controlled page {page_number} paper') if paged else ARXIV_ENTRY
            body = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
                    + f'<opensearch:totalResults>{0 if empty else 25 if paged else 1}</opensearch:totalResults>'
                    + ('' if empty else entry) + '</feed>').encode('utf-8')
            kind = 'application/atom+xml; charset=utf-8'
        elif request.path == '/openalex':
            records = [] if empty else [{
                'id': 'https://openalex.org/W123456789',
                'display_name': 'Controlled OpenAlex evidence paper',
                'authorships': [{'author': {'display_name': 'OpenAlex Researcher'}}],
                'abstract_inverted_index': {'Controlled': [0], 'OpenAlex': [1], 'evidence': [2], 'supports': [3], 'research.': [4]},
                'publication_date': '2026-01-02',
                'primary_location': {'landing_page_url': 'https://example.test/openalex/W123456789'},
                'topics': [{'display_name': 'Artificial intelligence'}],
                'cited_by_count': 432,
            }]
            body = json.dumps({'meta': {'count': 0 if empty else 1}, 'results': records}).encode('utf-8')
            kind = 'application/json'
        elif request.path == '/crossref':
            body = json.dumps({'status': 'ok', 'message': {'total-results': 1, 'items': [{
                'DOI': '10.1234/controlled-study', 'title': ['Controlled Crossref citation paper'],
                'author': [{'given': 'Crossref', 'family': 'Researcher'}], 'is-referenced-by-count': 987,
                'published': {'date-parts': [[2026, 1, 3]]},
            }]}}).encode('utf-8')
            kind = 'application/json'
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Never log provider query strings (they can contain credentials).
        pass


def serve():
    import uvicorn
    import paper_agent.tools.search as adapters
    import paper_agent.tools.crossref as crossref
    from paper_agent.interfaces.worker import create_app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, type=int)
    options = parser.parse_args()
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), ProviderFixture)
    upstream.daemon_threads = True
    base = f'http://127.0.0.1:{upstream.server_address[1]}'
    adapters.ARXIV_ENDPOINT = base + '/arxiv'
    adapters.OPENALEX_ENDPOINT = base + '/openalex'
    crossref.CROSSREF_ENDPOINT = base + '/crossref'
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    print('TEST ONLY: controlled arXiv/OpenAlex/Crossref HTTP fixtures; external websites are not being validated.', flush=True)
    try:
        uvicorn.run(create_app(study_factory=controlled_study_factory, model_tester=controlled_model_test), host='127.0.0.1', port=options.port)
    finally:
        upstream.shutdown()
        upstream.server_close()


def _check_credentials(credentials, model):
    expected = {'qwen': 'fixture-personal-qwen-1234', 'openai': 'fixture-personal-openai-5678'}
    if model == 'fixture-qwen-other':
        expected['qwen'] = 'fixture-personal-qwen-other-9999'
    provider = getattr(credentials, 'provider', None)
    secret = getattr(credentials, 'api_key', None)
    if (provider not in expected or secret is None or secret.get_secret_value() != expected[provider]
            or not isinstance(model, str) or not model.startswith(f'fixture-{provider}-')):
        raise ValueError('Controlled model credentials mismatch')


async def controlled_model_test(credentials, model):
    """TEST ONLY: verify secrets cross HTTP without contacting a paid model."""
    _check_credentials(credentials, model)


def controlled_study_factory(options):
    """Keep the real workflow, checking task-local credentials at its boundary."""
    from paper_agent.services.study import StudyService
    from paper_agent.tools.rag import HashingEmbedder, VectorIndex
    if getattr(options, 'credential_source', 'server') == 'personal':
        credentials = getattr(options, 'runtime_credentials', None)
        _check_credentials(credentials, options.model)
        if credentials.provider != options.provider:
            raise ValueError('Controlled model credentials mismatch')
    return StudyService(options, loader=ControlledStudyPDF(), team=ControlledStudyTeam(),
                        index=VectorIndex(HashingEmbedder()))


class ControlledStudyPDF:
    """TEST ONLY evidence boundary; no real PDF claim or model credential is used."""
    async def load(self, paper):
        from paper_agent.core.models import EvidenceChunk
        if 'missing-pdf' in paper.title:
            raise ValueError('Controlled PDF unavailable')
        return [EvidenceChunk(chunk_id=paper.paper_id+':p1:c0', paper_id=paper.paper_id, page_number=1,
                              source_url=paper.pdf_url or paper.page_url,
                              text='TEST ONLY controlled methodology and experiment text for browser integration.')]


class ControlledStudyTeam:
    """TEST ONLY deterministic model boundary, injected exclusively by this script."""
    async def analyze(self, paper, evidence, goal, notes, reflection):
        return {'paper_id': paper.paper_id, 'title': paper.title, 'overview': '受控测试论文概述',
                'background': '受控测试研究问题，验证任务与导出链路。',
                'methods': [{'name': '证据编码模块', 'purpose': '受控测试模块解释', 'inputs': '正文证据', 'outputs': '结构化学习内容'}],
                'innovations': ['受控测试创新点'], 'results': ['受控测试不提供真实实验数字。'],
                'reflection': ['Agent 测试建议：结合正文核对理解。'],
                'citations': [{'chunk_id': evidence[0].chunk_id, 'page_number': 1, 'source_url': evidence[0].source_url}]}

    async def synthesize(self, topic, analyses, goal):
        return {'synthesis': [f'受控测试已分析 {len(analyses)} 篇论文。'], 'learning_plan': ['阅读正文，解释模块，再检查实验。']}


if __name__ == '__main__':
    serve()
