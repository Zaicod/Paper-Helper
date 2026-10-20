"""tools search implementation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
import asyncio
import time
import weakref

import httpx

from paper_agent.core.models import Paper


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
OPENALEX_ENDPOINT = "https://api.openalex.org/works"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"


class SearchError(RuntimeError):
    """Raised when a paper provider cannot return trustworthy results."""


class NoPapersFound(SearchError):
    """The provider returned a valid response containing no matching papers."""


class SearchTimeout(SearchError):
    """The real provider did not respond within the configured deadline."""


class SearchRateLimit(SearchError):
    """The provider rejected the request because its quota or rate was exceeded."""


class ArxivRequestGate:
    """Keep one arXiv request active and at least three seconds between starts."""

    def __init__(self, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.lock = asyncio.Lock()
        self.clock = clock
        self.sleep = sleep
        self.next_start = 0.0

    async def __aenter__(self):
        await self.lock.acquire()
        try:
            delay = self.next_start - self.clock()
            if delay > 0:
                await self.sleep(delay)
            self.next_start = self.clock() + 3.0
        except BaseException:
            self.lock.release()
            raise

    async def __aexit__(self, *args):
        self.lock.release()


_ARXIV_GATES = weakref.WeakKeyDictionary()


def _arxiv_gate():
    # All instances in this process/event loop share a connection and rate gate,
    # including research workflows and the interactive paper-search endpoint.
    loop = asyncio.get_running_loop()
    if loop not in _ARXIV_GATES:
        _ARXIV_GATES[loop] = ArxivRequestGate()
    return _ARXIV_GATES[loop]


class ArxivSearchClient:
    """Deterministic arXiv adapter; it performs I/O but no LLM reasoning."""

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def search_page(self, topic: str, limit: int, page: int = 1, sort: str = 'relevance', keywords=None):
        from paper_agent.tools.search_pages import fetch_page
        return await fetch_page(self, 'arxiv', topic, limit, page, sort, keywords=keywords)

    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]:
        if not topic.strip():
            raise ValueError("topic cannot be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        search_query = f'all:"{topic.strip()}"'
        if category:
            search_query += f" AND cat:{category}"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": limit,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        headers = {
            "User-Agent": "paper-research-agent/0.1 (educational project)"
        }

        try:
            async with _arxiv_gate():
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds, headers=headers
                ) as client:
                    response = await client.get(ARXIV_ENDPOINT, params=params)
                    response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SearchTimeout('arXiv request timed out') from exc
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                raise SearchRateLimit('arXiv rate limit exceeded') from exc
            raise SearchError('arXiv request failed') from exc

        try:
            papers = self._parse_feed(response.text)
        except ET.ParseError as exc:
            raise SearchError("arXiv returned invalid Atom XML") from exc

        if not papers:
            raise NoPapersFound('No matching arXiv papers')
        return papers

    @staticmethod
    def _parse_feed(xml_text: str) -> list[Paper]:
        root = ET.fromstring(xml_text)
        if root.tag != f'{ATOM}feed':
            raise SearchError('arXiv returned an invalid feed')
        papers: list[Paper] = []

        for entry in root.findall(f"{ATOM}entry"):
            page_url = _text(entry, f"{ATOM}id")
            if '/api/errors' in page_url:
                raise SearchError('arXiv rejected the query')
            paper_id = page_url.rstrip("/").split("/")[-1]
            pdf_url = None
            for link in entry.findall(f"{ATOM}link"):
                if link.attrib.get("title") == "pdf":
                    pdf_url = link.attrib.get("href")
                    break

            papers.append(
                Paper(
                    paper_id=paper_id,
                    source="arxiv",
                    title=_clean(_text(entry, f"{ATOM}title")),
                    authors=[
                        _text(author, f"{ATOM}name")
                        for author in entry.findall(f"{ATOM}author")
                    ],
                    abstract=_clean(_text(entry, f"{ATOM}summary")),
                    published=_text(entry, f"{ATOM}published") or None,
                    categories=[
                        node.attrib["term"]
                        for node in entry.findall(f"{ATOM}category")
                        if "term" in node.attrib
                    ],
                    page_url=page_url,
                    pdf_url=pdf_url,
                )
            )

        return papers


class FixtureSearchClient:
    """Offline search provider for learning the workflow without network access."""

    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]:
        examples = [
            Paper(
                paper_id="demo-001",
                source="demo",
                title="Retrieval-Augmented Generation for Knowledge-Intensive Tasks",
                authors=["Demo Author A", "Demo Author B"],
                abstract=(
                    "This demonstration record studies combining parametric language "
                    "models with retrieved passages for knowledge-intensive tasks. "
                    "The abstract reports improved factual performance over a "
                    "parametric-only baseline."
                ),
                published="2020-01-01",
                categories=["cs.CL", "cs.AI"],
                page_url="https://example.com/demo-001",
            ),
            Paper(
                paper_id="demo-002",
                source="demo",
                title="Adaptive Retrieval for Efficient Question Answering",
                authors=["Demo Author C"],
                abstract=(
                    "This demonstration record proposes deciding when retrieval is "
                    "needed instead of retrieving for every query. It reports lower "
                    "retrieval cost while preserving answer quality on a benchmark."
                ),
                published="2022-01-01",
                categories=["cs.CL"],
                page_url="https://example.com/demo-002",
            ),
            Paper(
                paper_id="demo-003",
                source="demo",
                title="Evidence-Aware Generation with Citation Checking",
                authors=["Demo Author D", "Demo Author E"],
                abstract=(
                    "This demonstration record adds evidence attribution and a "
                    "citation consistency checker to a retrieval-generation pipeline. "
                    "The abstract claims fewer unsupported answers in evaluation."
                ),
                published="2024-01-01",
                categories=["cs.CL", "cs.IR"],
                page_url="https://example.com/demo-003",
            ),
        ]

        if category is not None:
            examples = [paper for paper in examples if category in paper.categories]
        return examples[:limit]


class OpenAlexSearchClient:
    """OpenAlex search adapter used as an arXiv-independent fallback."""

    CATEGORY_TERMS = {
        "cs.CL": "computational linguistics",
        "cs.AI": "artificial intelligence",
    }

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        api_key: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    async def search_page(self, topic: str, limit: int, page: int = 1, sort: str = 'relevance', keywords=None):
        from paper_agent.tools.search_pages import fetch_page
        return await fetch_page(self, 'openalex', topic, limit, page, sort, keywords=keywords)

    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]:
        if not topic.strip():
            raise ValueError("topic cannot be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        search_text = topic.strip()
        if category in self.CATEGORY_TERMS:
            search_text += " " + self.CATEGORY_TERMS[category]

        params = {
            "search": search_text,
            "filter": "has_abstract:true",
            "per_page": limit,
            "select": (
                "id,ids,doi,display_name,authorships,abstract_inverted_index,"
                "publication_date,primary_location,best_oa_location,open_access,topics"
            ),
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                headers={"User-Agent": "paper-research-agent/0.1"},
            ) as client:
                response = await client.get(OPENALEX_ENDPOINT, params=params)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise SearchTimeout('OpenAlex request timed out') from exc
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                raise SearchRateLimit('OpenAlex rate limit exceeded') from exc
            raise SearchError('OpenAlex request failed') from exc

        try:
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get('results'), list):
                raise ValueError('Invalid result list')
            papers = [self._to_paper(item) for item in body['results']]
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise SearchError('OpenAlex returned invalid paper metadata') from exc
        papers = [paper for paper in papers if paper.abstract]
        if not papers:
            raise NoPapersFound('No matching OpenAlex papers')
        return papers

    @staticmethod
    def _to_paper(item: dict) -> Paper:
        primary = item.get("primary_location") or {}
        best_oa = item.get("best_oa_location") or {}
        open_access = item.get("open_access") or {}
        openalex_url = item.get("id") or ""
        doi_url = item.get("doi") or ""

        paper_id = openalex_url.rstrip("/").split("/")[-1]
        doi_lower = doi_url.lower()
        arxiv_marker = "10.48550/arxiv."
        if arxiv_marker in doi_lower:
            paper_id = doi_lower.split(arxiv_marker, 1)[1]

        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in item.get("authorships", [])
        ]
        authors = [author for author in authors if author]

        topics = [
            topic.get("display_name", "") for topic in item.get("topics", [])
        ]
        topics = [topic for topic in topics if topic][:8]

        page_url = (
            primary.get("landing_page_url")
            or doi_url
            or openalex_url
        )
        pdf_url = (
            best_oa.get("pdf_url")
            or primary.get("pdf_url")
            or open_access.get("oa_url")
        )

        return Paper(
            paper_id=paper_id,
            source="openalex",
            title=item.get("display_name") or "Untitled",
            authors=authors,
            abstract=_restore_openalex_abstract(
                item.get("abstract_inverted_index")
            ),
            published=item.get("publication_date"),
            categories=topics,
            page_url=page_url,
            pdf_url=pdf_url,
        )


class FallbackSearchClient:
    """Try independent providers in order and return the first successful result."""

    def __init__(self, providers: list[object]) -> None:
        if not providers:
            raise ValueError("at least one search provider is required")
        self.providers = providers

    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return await provider.search(topic, limit, category)
            except SearchError as exc:
                errors.append(f"{type(provider).__name__}: {exc}")
        raise SearchError("all paper sources failed; " + " | ".join(errors))


def _text(node: ET.Element, path: str) -> str:
    child = node.find(path)
    return child.text.strip() if child is not None and child.text else ""


def _clean(value: str) -> str:
    return " ".join(value.split())


def _restore_openalex_abstract(
    inverted_index: dict[str, list[int]] | None,
) -> str:
    if not inverted_index:
        return ""
    positioned_words = [
        (position, word)
        for word, positions in inverted_index.items()
        for position in positions
    ]
    positioned_words.sort(key=lambda pair: pair[0])
    return " ".join(word for _, word in positioned_words)
