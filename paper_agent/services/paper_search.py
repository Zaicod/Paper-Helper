"""Interactive real-provider search with bounded time and storable metadata."""
from __future__ import annotations

import asyncio
import os
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from pydantic import Field, ValidationError, field_validator, model_validator

from paper_agent.core.models import Paper
from paper_agent.core.search_query import normalize_keywords, display_query
from paper_agent.tools.search import (
    ArxivSearchClient, NoPapersFound, OpenAlexSearchClient, SearchError, SearchTimeout, SearchRateLimit,
)


class SearchMetadataError(SearchError):
    """Provider metadata cannot be saved without changing scientific content."""


class SearchPaper(Paper):
    paper_id: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=1024)
    abstract: str = Field(max_length=10000)
    authors: list[Annotated[str, Field(max_length=128)]] = Field(max_length=50)
    categories: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=50)
    published: str | None = Field(default=None, max_length=64)
    page_url: str = Field(min_length=1, max_length=2048)
    pdf_url: str | None = Field(default=None, max_length=2048)

    @field_validator('paper_id', 'source', 'title')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Metadata must not be blank')
        return value

    @field_validator('page_url', 'pdf_url')
    @classmethod
    def http_links(cls, value):
        if value is not None:
            url = urlsplit(value)
            if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                    or any(character.isspace() or ord(character) < 32 for character in value)
                    or '\\' in value or not url.hostname.isascii()):
                raise ValueError('Invalid public paper URL')
        return value

    @model_validator(mode='after')
    def java_storage_constraints(self):
        # Java Bean Validation counts UTF-16 code units, while Python len counts
        # Unicode code points. Avoid returning metadata the collection rejects.
        limits = {'paper_id': 255, 'source': 64, 'title': 1024, 'abstract': 10000,
                  'published': 64, 'page_url': 2048, 'pdf_url': 2048}
        for field, maximum in limits.items():
            value = getattr(self, field)
            if value is not None and len(value.encode('utf-16-le')) // 2 > maximum:
                raise ValueError('Metadata exceeds Java storage limit')
        for values, maximum in ((self.authors, 128), (self.categories, 64)):
            if any(not value.strip() or len(value.encode('utf-16-le')) // 2 > maximum for value in values):
                raise ValueError('Invalid metadata list item')
        return self


def build_search_provider(source: str):
    if source == 'arxiv':
        return ArxivSearchClient(timeout_seconds=8.0)
    if source == 'openalex':
        return OpenAlexSearchClient(timeout_seconds=8.0, api_key=os.getenv('OPENALEX_API_KEY'))
    if source == 'crossref':
        from paper_agent.tools.crossref import CrossrefSearchClient
        return CrossrefSearchClient(timeout_seconds=8.0)
    raise ValueError('Unsupported paper provider')


async def search_paper_page(query, source, limit, page, sort, factory=None, keywords=None):
    normalized = normalize_keywords(keywords) if keywords is not None else None
    if normalized is not None:
        query = display_query(normalized)
    if not isinstance(query, str) or not query.strip() or len(query.encode('utf-16-le')) // 2 > 500:
        raise ValueError('搜索词不能为空且最多 500 字符。')
    has_exact = normalized is not None and any(k.match_mode == 'exact' for k in normalized)
    if (source not in ('auto', 'arxiv', 'openalex', 'crossref') or sort not in ('relevance', 'latest', 'citations')
            or page < 1 or not 1 <= limit <= 20 or page * limit > 10000
            or (page > 1 and source == 'auto') or (source == 'arxiv' and sort == 'citations')
            or (source == 'crossref' and has_exact)):
        raise ValueError('分页、排序或匹配方式无效；翻页请固定实际来源，Crossref 不支持精准短语。')
    factory = factory or build_search_provider
    providers = ((['openalex'] if has_exact else ['openalex', 'crossref']) if sort == 'citations'
                 else (['arxiv', 'openalex'] if has_exact else ['arxiv', 'openalex', 'crossref'])) if source == 'auto' else [source]
    warnings, errors = [], []
    empty = None
    for provider in providers:
        try:
            async with asyncio.timeout(8):
                adapter = factory(provider)
                batch = await adapter.search_page(query, limit, page, sort, **(
                    {'keywords': normalized} if normalized is not None else {}))
            bounded = [SearchPaper.model_validate(p.model_dump()) for p in batch.papers]
            if len(bounded) > limit or any(p.source != provider for p in bounded):
                raise SearchMetadataError('Invalid page identity')
            notices = []
            if provider == 'crossref':
                notices.append({'source': 'crossref', 'code': 'broad_search', 'message':
                    'Crossref 使用宽泛的书目信息检索，不保证精准短语或多个关键词同时满足；引用数仅为 Crossref 收录口径，部分论文缺少摘要和 PDF。'})
            response = {'contract_version': 1, 'query': query, 'requested_source': source, 'used_source': provider,
                        'papers': [p.model_dump(mode='json') for p in bounded], 'page': page, 'page_size': limit,
                        'total': batch.total, 'has_next': page * limit < min(batch.total, 10000),
                        'sort': sort, 'warnings': [*warnings, *notices]}
            if normalized is not None:
                response['keywords'] = [k.model_dump() for k in normalized]
            if bounded or source != 'auto':
                return response
            empty = response
        except (TimeoutError, SearchTimeout):
            errors.append('timeout')
            warnings.append({'source': provider, 'code': 'timeout', 'message': f'{provider} 响应超时，请稍后重试。'})
        except SearchRateLimit:
            errors.append('rate_limited')
            warnings.append({'source': provider, 'code': 'rate_limited', 'message': f'{provider} 请求受到限流，请稍后重试。'})
        except Exception:
            errors.append('unavailable')
            warnings.append({'source': provider, 'code': 'unavailable', 'message': f'{provider} 暂时不可用，请稍后重试。'})
    if empty is not None:
        return {**empty, 'warnings': [*warnings, *[
            item for item in empty['warnings'] if item['code'] == 'broad_search']]}
    if errors and all(e == 'rate_limited' for e in errors):
        raise SearchRateLimit('论文来源请求受到限流，请稍后重试。')
    if errors and all(e == 'timeout' for e in errors):
        raise SearchTimeout('论文来源响应超时，请稍后重试。')
    raise SearchError('论文来源暂时不可用，请更换来源或稍后重试。')


async def search_papers(query: str, source: str, limit: int, factory=None):
    factory = factory or build_search_provider
    providers = ['arxiv', 'openalex'] if source == 'auto' else [source]
    empty_source = None
    errors = []
    warnings = []
    def warning(provider, code):
        label = 'arXiv' if provider == 'arxiv' else 'OpenAlex'
        descriptions = {'timeout': '响应超时', 'rate_limited': '请求受到限流',
                        'metadata': '返回资料超出当前保存范围', 'unavailable': '暂时不可用'}
        warnings.append({'source': provider, 'code': code,
                         'message': f'{label} {descriptions[code]}，本次未完成该来源检索，请稍后重试或切换来源。'})
    try:
        # Includes rate-gate waiting and both network requests. Provider-specific
        # deadlines prevent a stalled source from exhausting the fallback budget.
        async with asyncio.timeout(22):
            for provider in providers:
                try:
                    async with asyncio.timeout(8):
                        papers = await factory(provider).search(query, limit)
                    if not papers:
                        raise NoPapersFound('No matching papers')
                    try:
                        bounded = [SearchPaper.model_validate(paper.model_dump()) for paper in papers[:limit]]
                        if any(paper.source != provider for paper in bounded):
                            raise ValueError('Unexpected provider identity')
                    except (ValidationError, ValueError, AttributeError, TypeError) as exc:
                        raise SearchMetadataError('论文来源返回的资料超出可保存范围，请更换来源或查询词。') from exc
                    return {'contract_version': 1, 'query': query, 'requested_source': source,
                            'used_source': provider, 'papers': [paper.model_dump(mode='json') for paper in bounded],
                            'warnings': warnings}
                except NoPapersFound:
                    empty_source = provider
                except (TimeoutError, httpx.TimeoutException, SearchTimeout):
                    errors.append('timeout')
                    warning(provider, 'timeout')
                except SearchRateLimit:
                    errors.append('rate_limited')
                    warning(provider, 'rate_limited')
                except SearchMetadataError:
                    errors.append('metadata')
                    warning(provider, 'metadata')
                except Exception:
                    # No external exception text, URL, credential or traceback is
                    # part of the public contract, even for unexpected adapters.
                    errors.append('failed')
                    warning(provider, 'unavailable')
    except TimeoutError:
        errors.append('timeout')
    if empty_source is not None:
        return {'contract_version': 1, 'query': query, 'requested_source': source,
                'used_source': empty_source, 'papers': [], 'warnings': warnings}
    if errors and all(error == 'rate_limited' for error in errors):
        raise SearchRateLimit('论文来源请求受到限流，请稍后重试。')
    if errors and all(error == 'timeout' for error in errors):
        raise SearchTimeout('论文来源响应超时，请稍后重试或更换来源。')
    if 'metadata' in errors:
        raise SearchMetadataError('论文来源返回的资料超出可保存范围，请更换来源或查询词。')
    raise SearchError('论文来源暂时不可用，请稍后重试或更换来源。')
