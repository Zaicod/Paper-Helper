import unittest
from unittest.mock import patch
import httpx
from paper_agent.tools import search


class ProviderPagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_arxiv_second_page_uses_upstream_offset_and_relevance(self):
        self.assertTrue(hasattr(search.ArxivSearchClient, 'search_page'), 'Upstream pagination is missing')
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, text='''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"><opensearch:totalResults>35</opensearch:totalResults><entry><id>https://arxiv.org/abs/2601.12345</id><title>Page two</title><summary></summary><author><name>A</name></author></entry></feed>''')
        original = httpx.AsyncClient
        with patch.object(search.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw)):
            page = await search.ArxivSearchClient().search_page('agents', 10, 2, 'relevance')
        self.assertEqual(requests[0].url.params['start'], '10')
        self.assertEqual(requests[0].url.params['sortBy'], 'relevance')
        self.assertEqual(page.total, 35)
        self.assertEqual(len(page.papers), 1)
        self.assertIsNone(page.papers[0].cited_by_count)

    async def test_openalex_citation_sort_total_and_no_abstract_preserved(self):
        self.assertTrue(hasattr(search.OpenAlexSearchClient, 'search_page'), 'Upstream pagination is missing')
        requests = []
        def respond(request):
            requests.append(request)
            number = request.url.params['page']
            return httpx.Response(200, json={'meta': {'count': 57}, 'results': [
                {'id': 'https://openalex.org/W'+number, 'display_name': 'Without abstract', 'cited_by_count': 123,
                 'authorships': [], 'primary_location': {'landing_page_url': 'https://example.org/paper'}}]})
        original = httpx.AsyncClient
        with patch.object(search.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(respond), **kw)):
            client = search.OpenAlexSearchClient()
            first = await client.search_page('agents', 10, 1, 'citations')
            second = await client.search_page('agents', 10, 2, 'citations')
        self.assertEqual(requests[1].url.params['sort'], 'cited_by_count:desc')
        self.assertNotIn('has_abstract', requests[1].url.params.get('filter', ''))
        self.assertEqual(second.total, 57)
        self.assertEqual(second.papers[0].abstract, '')
        self.assertEqual(second.papers[0].cited_by_count, 123)
        self.assertNotEqual(first.papers[0].paper_id, second.papers[0].paper_id)

    async def test_page_service_rejects_auto_later_page_and_arxiv_citations(self):
        from paper_agent.services import paper_search
        self.assertTrue(hasattr(paper_search, 'search_paper_page'), 'Paged search orchestration missing')
        for source, page, sort in [('auto', 2, 'relevance'), ('arxiv', 1, 'citations')]:
            with self.assertRaises(ValueError):
                await paper_search.search_paper_page('agents', source, 10, page, sort)
