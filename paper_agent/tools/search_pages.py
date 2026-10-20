"""Provider-native search pages; the research search protocol remains unchanged."""
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
import httpx
from paper_agent.core.models import Paper
from paper_agent.core.search_query import compile_query
from paper_agent.tools import search


class ProviderPage(BaseModel):
    papers: list[Paper]
    total: int = Field(ge=0)


@asynccontextmanager
async def request_gate(provider):
    if provider == 'arxiv':
        async with search._arxiv_gate():
            yield
    else:
        yield


async def fetch_page(adapter, provider, topic, limit, page, sort, keywords=None):
    if not topic.strip() or not 1 <= limit <= 20 or page < 1 or page * limit > 10000:
        raise ValueError('Invalid search page')
    if sort not in ('relevance', 'latest', 'citations') or (provider == 'arxiv' and sort == 'citations'):
        raise ValueError('Unsupported provider sort')
    if provider == 'arxiv':
        text = compile_query(provider, keywords) if keywords is not None else f'all:"{topic.strip()}"'
        params = {'search_query': text, 'start': (page - 1) * limit,
                  'max_results': limit, 'sortBy': 'relevance' if sort == 'relevance' else 'submittedDate',
                  'sortOrder': 'descending'}
        endpoint = search.ARXIV_ENDPOINT
    else:
        text = compile_query(provider, keywords) if keywords is not None else topic.strip()
        params = {'search': text, 'page': page, 'per_page': limit,
                  'sort': {'relevance': 'relevance_score:desc', 'latest': 'publication_date:desc',
                           'citations': 'cited_by_count:desc'}[sort]}
        if adapter.api_key:
            params['api_key'] = adapter.api_key
        endpoint = search.OPENALEX_ENDPOINT
    try:
        async with request_gate(provider):
            async with httpx.AsyncClient(timeout=adapter.timeout_seconds,
                                         headers={'User-Agent': 'paper-research-agent/0.3 (educational project)'}) as client:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise search.SearchTimeout('Paper source timed out') from exc
    except httpx.HTTPError as exc:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            raise search.SearchRateLimit('Paper source rate limited') from exc
        raise search.SearchError('Paper source unavailable') from exc
    try:
        if provider == 'arxiv':
            root = ET.fromstring(response.text)
            total = int(root.findtext('{http://a9.com/-/spec/opensearch/1.1/}totalResults'))
            papers = adapter._parse_feed(response.text)
        else:
            body = response.json()
            total = body['meta']['count']
            if type(total) is not int or not isinstance(body['results'], list):
                raise ValueError('Invalid page count')
            papers = [adapter._to_paper(item).model_copy(update={'cited_by_count': item.get('cited_by_count')})
                      for item in body['results']]
        return ProviderPage(papers=papers, total=total)
    except (ET.ParseError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise search.SearchError('Paper source returned invalid page metadata') from exc
