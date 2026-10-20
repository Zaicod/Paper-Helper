"""Crossref's broad bibliographic search and Crossref-only citation counts."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

from paper_agent.core.models import Paper
from paper_agent.core.search_query import compile_query
from paper_agent.tools.search import NoPapersFound, SearchError, SearchRateLimit, SearchTimeout
from paper_agent.tools.search_pages import ProviderPage

CROSSREF_ENDPOINT = 'https://api.crossref.org/works'


class _AbstractText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _abstract_text(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('Invalid Crossref abstract')
    parser = _AbstractText()
    parser.feed(value)
    parser.close()
    return ' '.join(' '.join(parser.parts).split())


def _publication_date(item):
    for field in ('published', 'published-online', 'published-print', 'issued'):
        value = item.get(field)
        if not value:
            continue
        parts = value.get('date-parts', [[]])[0]
        if not parts or parts == [None]:
            continue
        if (len(parts) > 3 or any(type(part) is not int for part in parts)
                or not 1 <= parts[0] <= 9999
                or (len(parts) > 1 and not 1 <= parts[1] <= 12)
                or (len(parts) > 2 and not 1 <= parts[2] <= 31)):
            raise ValueError('Invalid Crossref publication date')
        return '-'.join(str(part).zfill(4 if index == 0 else 2) for index, part in enumerate(parts))
    return None


def _paper(item):
    doi = item['DOI']
    if not isinstance(doi, str) or not re.fullmatch(r'10\.\d{4,9}/\S+', doi):
        raise ValueError('Invalid Crossref DOI')
    title = item['title'][0]
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Invalid Crossref title')
    authors = []
    for author in item.get('author', []):
        name = author.get('name') or ' '.join(part for part in (author.get('given'), author.get('family')) if part)
        if name:
            authors.append(name)
    pdf = None
    for link in item.get('link', []):
        if link.get('content-type', '').lower().split(';', 1)[0].strip() == 'application/pdf':
            pdf = link.get('URL')
            if pdf:
                break
    citations = item.get('is-referenced-by-count')
    if citations is not None and (type(citations) is not int or citations < 0):
        raise ValueError('Invalid Crossref citation count')
    return Paper(paper_id=doi, source='crossref', title=' '.join(title.split()), authors=authors,
        abstract=_abstract_text(item.get('abstract')), published=_publication_date(item),
        categories=item.get('subject') or [], page_url='https://doi.org/' + quote(doi, safe='/'),
        pdf_url=pdf, cited_by_count=citations)


class CrossrefSearchClient:
    def __init__(self, timeout_seconds: float = 8.0):
        self.timeout_seconds = timeout_seconds

    async def search_page(self, topic: str, limit: int, page: int = 1, sort: str = 'relevance', keywords=None):
        if (not isinstance(topic, str) or not topic.strip() or not 1 <= limit <= 20
                or page < 1 or page * limit > 10000 or sort not in ('relevance', 'latest', 'citations')):
            raise ValueError('Invalid Crossref search page')
        text = compile_query('crossref', keywords) if keywords is not None else topic.strip()
        params = {'query.bibliographic': text, 'rows': limit, 'offset': (page - 1) * limit,
                  'sort': {'relevance': 'score', 'latest': 'published', 'citations': 'is-referenced-by-count'}[sort],
                  'order': 'desc'}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds,
                    headers={'User-Agent': 'PaperFlow/0.3 (educational paper research project)'}) as client:
                response = await client.get(CROSSREF_ENDPOINT, params=params)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SearchTimeout('Crossref request timed out') from exc
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                raise SearchRateLimit('Crossref rate limited') from exc
            raise SearchError('Crossref request failed') from exc
        try:
            body = response.json()
            message = body['message']
            if (body.get('status') != 'ok' or type(message.get('total-results')) is not int
                    or not isinstance(message.get('items'), list)):
                raise ValueError('Invalid Crossref response')
            return ProviderPage(total=message['total-results'], papers=[_paper(item) for item in message['items']])
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
            raise SearchError('Crossref returned invalid metadata') from exc

    async def search(self, topic: str, limit: int, category=None):
        page = await self.search_page(topic, limit)
        if not page.papers:
            raise NoPapersFound('No matching Crossref papers')
        return page.papers
