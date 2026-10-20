import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from paper_agent.core.models import Paper
from paper_agent.tools import search

TOKEN = 'keyword-test-service-token-at-least-32-characters'
HEADERS = {'Authorization': 'Bearer ' + TOKEN}
MIXED = [{'text': '  multimodal learning  ', 'match_mode': 'exact'},
         {'text': 'retrieval augmented', 'match_mode': 'fuzzy'}]
FUZZY = [{'text': 'retrieval augmented', 'match_mode': 'fuzzy'}]
FEED = '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/"><o:totalResults>0</o:totalResults></feed>'


class KeywordContractTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.core.search_query'),
                             'Structured keyword matching contract is required')
        return importlib.import_module('paper_agent.core.search_query')

    def test_normalization_limits_and_display_query(self):
        module = self.module()
        result = module.normalize_keywords(MIXED)
        self.assertEqual(result[0].text, 'multimodal learning')
        self.assertEqual(module.display_query(result), 'multimodal learning / retrieval augmented')
        for values in [[], FUZZY*11, [{'text':' ', 'match_mode':'exact'}],
                       [{'text':'x', 'match_mode':'unknown'}],
                       [{'text':'a', 'match_mode':'exact'}, {'text':' A ', 'match_mode':'fuzzy'}],
                       [{'text':'😀'*251, 'match_mode':'fuzzy'}],
                       [{'text':'a'*250, 'match_mode':'fuzzy'}, {'text':'b'*249, 'match_mode':'exact'}]]:
            with self.assertRaises(ValueError):
                module.normalize_keywords(values)

    def test_compilers_preserve_phrase_vs_separate_terms_and_escape_operators(self):
        module = self.module()
        values = module.normalize_keywords(MIXED)
        self.assertEqual(module.compile_query('arxiv', values),
                         'all:"multimodal learning" AND all:retrieval AND all:augmented')
        self.assertEqual(module.compile_query('openalex', values),
                         '"multimodal learning" AND retrieval AND augmented')
        malicious = module.normalize_keywords([{'text': 'foo" OR title:bar*', 'match_mode':'exact'},
                                                {'text':'OR (cat:cs.AI)', 'match_mode':'fuzzy'}])
        compiled = module.compile_query('arxiv', malicious)
        self.assertIn('foo\\" OR title:bar\\*', compiled)
        self.assertIn('all:"OR"', compiled)
        self.assertNotIn('all:(cat:cs.AI)', compiled)
        self.assertIn('\\(', compiled)

    def test_exact_phrases_cannot_enable_wildcards_or_proximity(self):
        module = self.module()
        value = module.compile_query('openalex', [{'text':'smart* phone? ~2', 'match_mode':'exact'}])
        self.assertIn('smart\\* phone\\? \\~2', value)


class KeywordProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_crossref_unknown_publication_date_does_not_reject_the_whole_page(self):
        from paper_agent.tools.crossref import CrossrefSearchClient
        original=httpx.AsyncClient
        def respond(request):
            return httpx.Response(200,json={'status':'ok','message':{'total-results':2,'items':[
                {'DOI':'10.1234/unknown-date','title':['Date unknown'],'issued':{'date-parts':[[None]]}},
                {'DOI':'10.1234/known-date','title':['Date known'],'published':{'date-parts':[[2026,10,19]]}},
            ]}})
        with patch.object(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw)):
            try:
                result=await CrossrefSearchClient().search_page('multimodal learning',10)
            except search.SearchError:
                self.fail('An unknown Crossref date must not discard valid papers or invalidate a page')
        self.assertEqual(result.total,2)
        self.assertEqual(len(result.papers),2)
        self.assertIsNone(result.papers[0].published)
        self.assertEqual(result.papers[1].published,'2026-10-19')

    async def test_default_auto_search_uses_available_fallback_without_relaxing_exact_terms(self):
        from paper_agent.services.paper_search import search_paper_page
        from paper_agent.tools.search_pages import ProviderPage
        calls=[]
        class Provider:
            def __init__(self, source): self.source=source
            async def search_page(self,*args,**kwargs):
                calls.append(self.source)
                if self.source=='arxiv': raise search.SearchTimeout('upstream timeout')
                if self.source=='openalex': raise search.SearchRateLimit('rate limited')
                return ProviderPage(total=1,papers=[Paper(paper_id='10.1234/fallback',source='crossref',title='Available fallback',
                    authors=[],abstract='',page_url='https://doi.org/10.1234/fallback')])
        for sort in ('relevance','latest'):
            calls.clear()
            try:
                value=await search_paper_page('display','auto',10,1,sort,Provider,keywords=FUZZY)
            except search.SearchError:
                self.fail('Default automatic search must try the available broad-search fallback')
            self.assertEqual(calls,['arxiv','openalex','crossref'])
            self.assertEqual(value['used_source'],'crossref')
            self.assertEqual([w['code'] for w in value['warnings']],['timeout','rate_limited','broad_search'])
        calls.clear()
        with self.assertRaises(search.SearchError):
            await search_paper_page('display','auto',10,1,'relevance',Provider,keywords=MIXED)
        self.assertEqual(calls,['arxiv','openalex'])

    async def test_crossref_http_rate_limit_timeout_and_invalid_body_are_typed(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.tools.crossref'))
        from paper_agent.tools.crossref import CrossrefSearchClient
        original=httpx.AsyncClient
        def limited(request):return httpx.Response(429,text='private-provider-key')
        with patch.object(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(limited),**kw)):
            with self.assertRaises(search.SearchRateLimit):
                await CrossrefSearchClient().search_page('agents',10)
        def timeout(request):raise httpx.ReadTimeout('private-provider-key',request=request)
        with patch.object(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(timeout),**kw)):
            with self.assertRaises(search.SearchTimeout):
                await CrossrefSearchClient().search_page('agents',10)
        def bad_metadata(request):return httpx.Response(200,json={'message':{'items':[], 'total-results': 'bad'}})
        with patch.object(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(bad_metadata),**kw)):
            with self.assertRaises(search.SearchError):
                await CrossrefSearchClient().search_page('agents',10)

    async def test_http_boundary_mixed_keyword_compilation(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.core.search_query'))
        received = []
        def respond(request):
            received.append(request)
            return httpx.Response(200, text=FEED) if request.url.host == 'export.arxiv.org' else httpx.Response(200, json={'meta':{'count':0}, 'results':[]})
        original = httpx.AsyncClient
        with patch.object(search.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw)):
            await search.ArxivSearchClient().search_page('display', 10, keywords=MIXED)
            await search.OpenAlexSearchClient().search_page('display', 10, keywords=MIXED)
        self.assertEqual(received[0].url.params['search_query'], 'all:"multimodal learning" AND all:retrieval AND all:augmented')
        self.assertEqual(received[1].url.params['search'], '"multimodal learning" AND retrieval AND augmented')

    async def test_crossref_citations_pagination_and_metadata_are_real_source_fields(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.tools.crossref'), 'Crossref fallback adapter required')
        from paper_agent.tools.crossref import CrossrefSearchClient
        received = []
        def respond(request):
            received.append(request)
            number = '2' if request.url.params['offset'] == '10' else '1'
            return httpx.Response(200, json={'status':'ok', 'message':{'total-results':51, 'items':[
                {'DOI':'10.1234/test'+number, 'title':['Crossref '+number],
                 'author':[{'given':'Jane', 'family':'Doe'}], 'is-referenced-by-count':120,
                 'published':{'date-parts':[[2024,2,3]]},
                 'abstract':'<jats:p>A <jats:italic>recorded</jats:italic> abstract.</jats:p>',
                 'link':[{'URL':'https://publisher.example/page', 'content-type':'text/html'}]},
                {'DOI':'10.1234/noabstract', 'title':['Missing metadata'], 'link':[
                    {'URL':'https://publisher.example/paper.pdf', 'content-type':'application/pdf'}]}]}})
        original = httpx.AsyncClient
        with patch.object(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw)):
            adapter=CrossrefSearchClient()
            first = await adapter.search_page('multimodal', 10, 1, 'citations', keywords=FUZZY)
            second = await adapter.search_page('multimodal', 10, 2, 'latest', keywords=FUZZY)
        self.assertEqual(received[0].url.params['sort'], 'is-referenced-by-count')
        self.assertEqual(received[0].url.params['order'], 'desc')
        self.assertEqual(received[1].url.params['sort'], 'published')
        self.assertEqual(received[1].url.params['offset'], '10')
        self.assertEqual(received[1].url.params['query.bibliographic'], 'retrieval augmented')
        self.assertEqual(second.total,51)
        self.assertNotEqual(first.papers[0].paper_id, second.papers[0].paper_id)
        self.assertEqual(second.papers[0].source, 'crossref')
        self.assertEqual(second.papers[0].page_url, 'https://doi.org/10.1234/test2')
        self.assertEqual(second.papers[0].cited_by_count, 120)
        self.assertEqual(second.papers[0].abstract, 'A recorded abstract.')
        self.assertIsNone(second.papers[0].pdf_url)
        self.assertEqual(second.papers[1].abstract, '')
        self.assertIsNone(second.papers[1].cited_by_count)

    async def test_citation_fallback_only_when_all_keywords_are_fuzzy(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.tools.crossref'))
        from paper_agent.services.paper_search import search_paper_page
        from paper_agent.tools.search_pages import ProviderPage
        received=[]
        class Provider:
            def __init__(self, source): self.source=source
            async def search_page(self, *args, **kwargs):
                received.append(self.source)
                if self.source=='openalex': raise search.SearchRateLimit('private-key')
                return ProviderPage(total=1, papers=[Paper(paper_id='10.1/x', source='crossref',
                    title='Fallback', authors=[], abstract='',page_url='https://doi.org/10.1/x')])
        value=await search_paper_page('display','auto',10,1,'citations',Provider,keywords=FUZZY)
        self.assertEqual(received,['openalex','crossref'])
        self.assertEqual(value['used_source'],'crossref')
        self.assertEqual([w['code'] for w in value['warnings']],['rate_limited','broad_search'])
        self.assertEqual(value['keywords'],FUZZY)
        received.clear()
        with self.assertRaises(search.SearchRateLimit):
            await search_paper_page('display','auto',10,1,'citations',Provider,keywords=MIXED)
        self.assertEqual(received,['openalex'])
        with self.assertRaises(ValueError):
            await search_paper_page('display','crossref',10,1,'relevance',Provider,keywords=MIXED)

    async def test_empty_crossref_still_exposes_broad_matching_notice(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.tools.crossref'))
        from paper_agent.services.paper_search import search_paper_page
        from paper_agent.tools.search_pages import ProviderPage
        class Empty:
            async def search_page(self,*args,**kwargs):return ProviderPage(total=0,papers=[])
        value=await search_paper_page('display','auto',10,1,'citations',lambda source:Empty(), keywords=FUZZY)
        self.assertEqual(value['used_source'],'crossref')
        self.assertIn('broad_search',[warning['code'] for warning in value['warnings']])


class KeywordWorkerTests(unittest.TestCase):
    def test_structured_keywords_do_not_require_duplicate_query_parameter(self):
        from paper_agent.interfaces.worker import create_app
        from paper_agent.tools.search_pages import ProviderPage
        class Provider:
            async def search_page(self,*args,**kwargs):
                return ProviderPage(total=0,papers=[])
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(db_path=Path(directory)/'tasks.db',service_token=TOKEN,
                                      search_factory=lambda source:Provider())) as client:
                endpoint='/internal/v1/papers/search'
                response=client.get(endpoint,params={'source':'arxiv','keywords':json.dumps(MIXED)},headers=HEADERS)
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['query'],'multimodal learning / retrieval augmented')
                missing=client.get(endpoint,params={'source':'arxiv'},headers=HEADERS)
                self.assertEqual(missing.status_code,422)

    def test_auth_validation_echo_and_legacy_calls(self):
        self.assertIsNotNone(importlib.util.find_spec('paper_agent.core.search_query'))
        from paper_agent.interfaces.worker import create_app
        from paper_agent.tools.search_pages import ProviderPage
        class Provider:
            async def search_page(self,*args,**kwargs):
                return ProviderPage(total=0,papers=[])
            async def search(self,*args): return []
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(db_path=Path(directory)/'tasks.db', service_token=TOKEN,
                                      search_factory=lambda source:Provider())) as client:
                endpoint='/internal/v1/papers/search'
                params={'query':'untrusted display', 'source':'arxiv','keywords':json.dumps(MIXED)}
                self.assertEqual(client.get(endpoint, params=params).status_code,401)
                value=client.get(endpoint,params=params,headers=HEADERS)
                self.assertEqual(value.status_code,200,value.text)
                self.assertEqual(value.json()['query'],'multimodal learning / retrieval augmented')
                self.assertEqual(value.json()['keywords'][0]['text'],'multimodal learning')
                for bad in ['not-json', '{}','[]','null',json.dumps([{'text':'secret-bad','match_mode':'evil'}])]:
                    result=client.get(endpoint,params={**params,'keywords':bad},headers=HEADERS)
                    self.assertEqual(result.status_code,422)
                    self.assertNotIn('secret-bad',result.text)
                legacy=client.get(endpoint,params={'query':'legacy','source':'arxiv'},headers=HEADERS)
                self.assertEqual(legacy.status_code,200)
                self.assertNotIn('keywords',legacy.json())
                crossref=client.get(endpoint,params={'query':'legacy','source':'crossref'},headers=HEADERS)
                self.assertEqual(crossref.status_code,200)
                self.assertEqual(crossref.json()['used_source'],'crossref')
                self.assertEqual(crossref.json()['warnings'][0]['code'],'broad_search')
