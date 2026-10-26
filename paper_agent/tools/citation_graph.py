"""Bounded one-hop OpenAlex graph reads. Never fetch provider-supplied URLs."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import os
import re
from urllib.parse import unquote, urlsplit
import httpx

ENDPOINT = 'https://api.openalex.org/works'
MAX_RESPONSE = 4 * 1024 * 1024


class GraphError(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


@dataclass
class GraphBatch:
    works: list[dict]
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)


def work_id(value):
    if not isinstance(value, str): return None
    if re.fullmatch(r'W[1-9]\d*', value): return value
    match = re.fullmatch(r'https://openalex\.org/(?:works/)?(W[1-9]\d*)', value)
    return match.group(1) if match else None


def doi(value):
    if not isinstance(value, str): return None
    value = unquote(value).strip()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value, flags=re.I)
    return value.casefold() if re.fullmatch(r'10\.\d{4,9}/[^\s?#\\]+', value, re.I) else None


def seed_identity(paper):
    if paper.source == 'openalex' and work_id(paper.paper_id):
        return ('work', work_id(paper.paper_id))
    page = urlsplit(paper.page_url)
    if page.scheme == 'https' and page.hostname == 'openalex.org' and not page.query and not page.fragment:
        identifier = work_id(paper.page_url)
        if identifier: return ('work', identifier)
    identifier = doi(paper.paper_id) if paper.source == 'crossref' else None
    if page.hostname in ('doi.org', 'dx.doi.org') and not page.username and not page.password and not page.query and not page.fragment:
        identifier = doi(page.path.lstrip('/')) or identifier
    if identifier: return ('doi', identifier)
    if paper.source == 'arxiv' and re.fullmatch(r'(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?',paper.paper_id,re.I):
        return ('doi', '10.48550/arxiv.' + re.sub(r'v\d+$','',paper.paper_id).casefold())
    raise GraphError('unmapped')


class OpenAlexGraphClient:
    def __init__(self, *, transport=None, max_requests=20):
        self.transport = transport
        self.requests = 0
        self.max_requests = min(20, max(0, max_requests))

    async def _get(self, suffix='', params=None):
        if self.requests >= self.max_requests: raise GraphError('budget')
        self.requests += 1
        params = dict(params or {})
        if os.getenv('OPENALEX_API_KEY'): params['api_key'] = os.environ['OPENALEX_API_KEY']
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, transport=self.transport,
                    headers={'User-Agent':'PaperFlow/0.3 citation-tracking'}) as client:
                async with client.stream('GET', ENDPOINT+suffix, params=params) as response:
                    if response.status_code == 429: raise GraphError('rate_limited')
                    if response.status_code != 200: raise GraphError('unavailable')
                    content = bytearray()
                    async for block in response.aiter_bytes():
                        if len(content)+len(block) > MAX_RESPONSE: raise GraphError('oversized')
                        content.extend(block)
            value = json.loads(content)
            if not isinstance(value, dict): raise GraphError('invalid_metadata')
            return value
        except httpx.TimeoutException:
            raise GraphError('timeout') from None
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, GraphError): raise
            raise GraphError('invalid_metadata') from None

    async def resolve(self, paper):
        kind, identifier = seed_identity(paper)
        if kind == 'work':
            item = await self._get('/'+identifier)
            if work_id(item.get('id')) != identifier: raise GraphError('identity_mismatch')
        else:
            body = await self._get(params={'filter':'doi:https://doi.org/'+identifier,'per_page':2})
            items = body.get('results')
            if not isinstance(items, list) or len(items) != 1: raise GraphError('unmapped')
            item = items[0]
            if not isinstance(item, dict) or doi(item.get('doi')) != identifier:
                raise GraphError('identity_mismatch')
        if not work_id(item.get('id')): raise GraphError('invalid_metadata')
        return item

    async def neighbors(self, item, direction):
        identifier = work_id(item.get('id'))
        if not identifier or direction not in ('references','citations'): raise GraphError('invalid_metadata')
        warnings = []
        expected = []
        if direction == 'references':
            refs = item.get('referenced_works')
            if not isinstance(refs, list): raise GraphError('missing_relations')
            for ref in refs[:100]:
                value = work_id(ref)
                if value and value not in expected: expected.append(value)
                elif not value: warnings.append('来源含无效引用编号，已忽略。')
            truncated = len(expected) > 20 or len(refs)>100
            expected = expected[:20]
            if not expected: return GraphBatch([], warnings=warnings)
            params = {'filter':'openalex_id:'+'|'.join(expected),'per_page':20}
        else:
            truncated = False
            params = {'filter':'cites:'+identifier,'per_page':20,'sort':'publication_date:desc'}
        body = await self._get(params=params)
        rows = body.get('results')
        if not isinstance(rows,list) or len(rows)>20: raise GraphError('invalid_metadata')
        meta = body.get('meta') or {}
        count = meta.get('count') if isinstance(meta,dict) else None
        truncated = truncated or isinstance(count,int) and count>20
        valid = []
        for row in rows:
            wid = work_id(row.get('id')) if isinstance(row,dict) else None
            refs = row.get('referenced_works') if isinstance(row,dict) else None
            linked = wid in expected if direction=='references' else isinstance(refs,list) and identifier in {work_id(r) for r in refs}
            if not wid or not linked:
                warnings.append('来源返回的候选缺少可核对的引用关系，已忽略。')
                continue
            valid.append(row)
        return GraphBatch(valid, truncated, list(dict.fromkeys(warnings)))
