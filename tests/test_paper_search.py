import asyncio
import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from paper_agent.core.models import Paper
from paper_agent.tools import search

TOKEN = 'paper-search-test-service-token-over-32-characters'
HEADERS = {'Authorization': f'Bearer {TOKEN}'}
PAPER = Paper(paper_id='W123', source='openalex', title='Recorded research', authors=['A Researcher'],
              abstract='A real metadata shape.', categories=['Machine learning'],
              published='2024-01-01', page_url='https://openalex.org/W123')
ATOM = '''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<id>http://arxiv.org/abs/2401.12345v1</id><title> Recorded\n arXiv result </title>
<summary>A recorded abstract.</summary><published>2024-01-02T00:00:00Z</published>
<author><name>A Author</name></author><category term="cs.AI"/>
<link title="pdf" href="https://arxiv.org/pdf/2401.12345v1"/></entry></feed>'''


class SearchRouteTests(unittest.TestCase):
    def test_empty_primary_result_keeps_fallback_failure_visible(self):
        class Empty:
            async def search(self, *args): raise search.NoPapersFound('no records')
        class Fails:
            async def search(self, *args): raise search.SearchError('sk-secret provider failed')
        with self.client(lambda source: Empty() if source == 'arxiv' else Fails()) as client:
            response = client.get('/internal/v1/papers/search', params={'query': 'multimodal'}, headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body['papers'], [])
            self.assertEqual(len(body.get('warnings', [])), 1)
            self.assertEqual(body['warnings'][0]['source'], 'openalex')
            self.assertEqual(body['warnings'][0]['code'], 'unavailable')
            self.assertNotIn('sk-secret', response.text)

    def test_provider_rate_limit_has_distinct_status_and_partial_warning(self):
        client_type = httpx.AsyncClient
        def rate_limited(request): return httpx.Response(429, text='secret-provider-details')
        with patch.object(search.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(rate_limited), **kwargs)):
            with self.client(lambda source: search.OpenAlexSearchClient()) as client:
                response = client.get('/internal/v1/papers/search', params={'query': 'multimodal', 'source': 'openalex'}, headers=HEADERS)
                self.assertEqual(response.status_code, 429)
                self.assertNotIn('secret-provider', response.text)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def client(self, factory):
        from paper_agent.interfaces.worker import create_app
        self.assertIn('search_factory', __import__('inspect').signature(create_app).parameters,
                      'Worker must expose the real paper-search boundary with injectable providers')
        return TestClient(create_app(db_path=Path(self.temp.name)/'tasks.sqlite3', service_token=TOKEN,
                                     search_factory=factory))

    def test_authenticated_search_and_parameters(self):
        calls = []
        class Provider:
            async def search(self, topic, limit, category=None):
                calls.append((topic, limit))
                return [PAPER]
        with self.client(lambda source: Provider()) as client:
            url = '/internal/v1/papers/search'
            self.assertEqual(client.get(url, params={'query': 'RAG'}).status_code, 401)
            response = client.get(url, params={'query': '  RAG  ', 'source': 'openalex', 'limit': 2}, headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body['contract_version'], 1)
            self.assertEqual(body['query'], 'RAG')
            self.assertEqual(body['requested_source'], 'openalex')
            self.assertEqual(body['used_source'], 'openalex')
            self.assertEqual(body['papers'][0]['paper_id'], 'W123')
            self.assertEqual(calls, [('RAG', 2)])
            for params in [{'query': ' '}, {'query': 'a'*501}, {'query': 'RAG', 'source': 'fixture'},
                           {'query': 'RAG', 'limit': 0}, {'query': 'RAG', 'limit': 21}]:
                self.assertEqual(client.get(url, params=params, headers=HEADERS).status_code, 422)

    def test_auto_fallback_preserves_real_provider_and_empty_results(self):
        class Fails:
            async def search(self, *args):
                raise search.SearchError('sk-secret in https://provider?api_key=secret')
        class Good:
            async def search(self, *args): return [PAPER]
        with self.client(lambda source: Fails() if source == 'arxiv' else Good()) as client:
            body = client.get('/internal/v1/papers/search', params={'query': 'RAG'}, headers=HEADERS).json()
            self.assertEqual(body['used_source'], 'openalex')
            self.assertEqual(body['papers'][0]['source'], 'openalex')
        self.assertTrue(hasattr(search, 'NoPapersFound'), 'Legitimate empty results need a distinct signal')
        class Empty:
            async def search(self, *args): raise search.NoPapersFound('no records')
        with self.client(lambda source: Fails() if source == 'arxiv' else Empty()) as client:
            response = client.get('/internal/v1/papers/search', params={'query': 'none'}, headers=HEADERS)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['papers'], [])
            self.assertEqual(response.json()['used_source'], 'openalex')

    def test_failures_and_timeouts_do_not_echo_provider_secrets(self):
        class Fails:
            async def search(self, *args): raise RuntimeError('sk-private-key /private/path')
        with self.client(lambda source: Fails()) as client:
            response = client.get('/internal/v1/papers/search', params={'query': 'RAG'}, headers=HEADERS)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('private', response.text)
        class TimesOut:
            async def search(self, *args): raise httpx.ReadTimeout('sk-private-key')
        with self.client(lambda source: TimesOut()) as client:
            response = client.get('/internal/v1/papers/search', params={'query': 'RAG', 'source': 'arxiv'}, headers=HEADERS)
            self.assertEqual(response.status_code, 504)
            self.assertNotIn('private', response.text)

    def test_unrepresentable_metadata_is_rejected_without_truncating(self):
        class Oversized:
            async def search(self, *args): return [PAPER.model_copy(update={'abstract': 'x'*10001})]
        with self.client(lambda source: Oversized()) as client:
            response = client.get('/internal/v1/papers/search', params={'query': 'RAG', 'source': 'openalex'}, headers=HEADERS)
            self.assertEqual(response.status_code, 502)
            self.assertIn('保存', response.json()['detail'])

    def test_metadata_matches_java_utf16_and_nonblank_constraints(self):
        records = [PAPER.model_copy(update={'title': '😀' * 513}),
                   PAPER.model_copy(update={'authors': [' ']}),
                   PAPER.model_copy(update={'categories': ['a' * 65]}),
                   PAPER.model_copy(update={'page_url': 'https://example.com/not a uri'})]
        for paper in records:
            class Provider:
                async def search(self, *args): return [paper]
            with self.client(lambda source: Provider()) as client:
                response = client.get('/internal/v1/papers/search', params={'query': 'RAG', 'source': 'openalex'}, headers=HEADERS)
                self.assertEqual(response.status_code, 502, f'Invalid metadata was accepted: {paper.paper_id}')

    def test_default_worker_uses_real_openalex_adapter_without_fixture_substitution(self):
        from paper_agent.interfaces.worker import create_app
        client_type = httpx.AsyncClient
        requests = []
        def response(request):
            requests.append(request)
            return httpx.Response(200, json={'results': []})
        with patch.object(search.httpx, 'AsyncClient', lambda **kwargs: client_type(transport=httpx.MockTransport(response), **kwargs)):
            with TestClient(create_app(db_path=Path(self.temp.name)/'default.sqlite3', service_token=TOKEN)) as client:
                result = client.get('/internal/v1/papers/search', params={'query': 'nothing', 'source': 'openalex'}, headers=HEADERS)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()['papers'], [])
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.host, 'api.openalex.org')


class RecordedAdapterTests(unittest.IsolatedAsyncioTestCase):
    def transport_factory(self, handler):
        client_type = httpx.AsyncClient
        return lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs)

    async def test_recorded_arxiv_and_openalex_http_parsing(self):
        def arxiv_response(request):
            self.assertEqual(request.url.host, 'export.arxiv.org')
            self.assertEqual(request.url.params['max_results'], '2')
            return httpx.Response(200, text=ATOM)
        with patch.object(search.httpx, 'AsyncClient', self.transport_factory(arxiv_response)):
            papers = await search.ArxivSearchClient().search('RAG', 2)
        self.assertEqual(papers[0].title, 'Recorded arXiv result')
        self.assertEqual(papers[0].paper_id, '2401.12345v1')
        self.assertEqual(papers[0].categories, ['cs.AI'])
        def openalex_response(request):
            self.assertEqual(request.url.params['api_key'], 'optional-secret')
            return httpx.Response(200, json={'results': [{'id': 'https://openalex.org/W123',
                'display_name': 'Recorded OpenAlex result', 'abstract_inverted_index': {'Second': [1], 'First': [0]},
                'authorships': [{'author': {'display_name': 'An Author'}}],
                'primary_location': {'landing_page_url': 'https://doi.org/10.1/test'},
                'topics': [{'display_name': 'Artificial intelligence'}], 'publication_date': '2024-01-01'}]})
        with patch.object(search.httpx, 'AsyncClient', self.transport_factory(openalex_response)):
            papers = await search.OpenAlexSearchClient(api_key='optional-secret').search('RAG', 2)
        self.assertEqual(papers[0].abstract, 'First Second')
        self.assertEqual(papers[0].source, 'openalex')

    async def test_empty_adapters_have_distinct_signal_and_malformed_data_is_failure(self):
        self.assertTrue(hasattr(search, 'NoPapersFound'))
        with patch.object(search.httpx, 'AsyncClient', self.transport_factory(lambda request: httpx.Response(200, json={'results': []}))):
            with self.assertRaises(search.NoPapersFound): await search.OpenAlexSearchClient().search('none', 1)
        with patch.object(search.httpx, 'AsyncClient', self.transport_factory(lambda request: httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"/>'))):
            with self.assertRaises(search.NoPapersFound): await search.ArxivSearchClient().search('none', 1)
        with patch.object(search.httpx, 'AsyncClient', self.transport_factory(lambda request: httpx.Response(200, text='not json'))):
            with self.assertRaises(search.SearchError): await search.OpenAlexSearchClient().search('broken', 1)

    async def test_arxiv_global_gate_serializes_requests_and_spaces_starts(self):
        self.assertTrue(hasattr(search, 'ArxivRequestGate'), 'arXiv requests need a shared rate gate')
        self.assertIs(search._arxiv_gate(), search._arxiv_gate())
        now = [0.0]
        starts = []
        active = [0]
        async def sleep(seconds): now[0] += seconds
        gate = search.ArxivRequestGate(clock=lambda: now[0], sleep=sleep)
        async def response(request):
            active[0] += 1
            self.assertEqual(active[0], 1)
            starts.append(now[0])
            await asyncio.sleep(0)
            active[0] -= 1
            return httpx.Response(200, text=ATOM)
        with patch.object(search.httpx, 'AsyncClient', self.transport_factory(response)), patch.object(search, '_arxiv_gate', return_value=gate):
            await asyncio.gather(search.ArxivSearchClient().search('a', 1), search.ArxivSearchClient().search('b', 1))
        self.assertEqual(starts, [0.0, 3.0])

    async def test_http_adapter_errors_and_timeout_are_typed_and_redacted(self):
        for adapter in [search.ArxivSearchClient, search.OpenAlexSearchClient]:
            with self.subTest(provider=adapter.__name__):
                with patch.object(search.httpx, 'AsyncClient', self.transport_factory(lambda request: httpx.Response(429))):
                    with self.assertRaises(search.SearchError) as failure:
                        await adapter().search('topic', 1)
                self.assertNotIn('https:', str(failure.exception))
                async def timeout(request): raise httpx.ReadTimeout('sk-secret-in-url?api_key=private')
                # arXiv's gate is still enforced; use a fresh fake-clock gate to keep this offline test immediate.
                now = [0.0]
                async def advance(seconds): now[0] += seconds
                gate = search.ArxivRequestGate(clock=lambda: now[0], sleep=advance)
                with patch.object(search, '_arxiv_gate', return_value=gate), patch.object(search.httpx, 'AsyncClient', self.transport_factory(timeout)):
                    with self.assertRaises(search.SearchTimeout) as failure:
                        await adapter().search('topic', 1)
                self.assertNotIn('private', str(failure.exception))
