from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from paper_agent.models import Paper
from paper_agent.search import (
    ArxivSearchClient,
    FallbackSearchClient,
    OpenAlexSearchClient,
    SearchError,
)
from paper_agent.storage import PaperLibrary, PaperLibraryItem


class PaperSearchClient(Protocol):
    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]: ...


@dataclass(frozen=True)
class DownloadedPdf:
    path: Path
    source_url: str
    size_bytes: int


class PdfDownloadError(RuntimeError):
    """Raised when a remote resource cannot be stored as a trustworthy PDF."""


class PdfDownloader:
    def __init__(
        self,
        root: Path,
        *,
        timeout_seconds: float = 45.0,
        max_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    async def download(self, paper: Paper) -> DownloadedPdf:
        if not paper.pdf_url:
            raise PdfDownloadError("该论文没有可用的开放 PDF 链接")
        parsed = urlparse(paper.pdf_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise PdfDownloadError("PDF 链接不是有效的 HTTP(S) 地址")

        source_dir = self.root / _safe_component(paper.source)
        source_dir.mkdir(parents=True, exist_ok=True)
        destination = source_dir / f"{_safe_component(paper.paper_id)}.pdf"
        temporary = destination.with_suffix(".pdf.part")
        size = 0
        prefix = b""

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "paper-research-agent/0.2"},
            ) as client:
                async with client.stream("GET", paper.pdf_url) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as stream:
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            if not prefix:
                                prefix = chunk[:5]
                            size += len(chunk)
                            if size > self.max_bytes:
                                raise PdfDownloadError(
                                    f"PDF 超过 {self.max_bytes // (1024 * 1024)} MB 限制"
                                )
                            stream.write(chunk)
            if prefix != b"%PDF-":
                raise PdfDownloadError("下载内容不是有效的 PDF 文件")
            temporary.replace(destination)
        except PdfDownloadError:
            temporary.unlink(missing_ok=True)
            raise
        except (httpx.HTTPError, OSError) as exc:
            temporary.unlink(missing_ok=True)
            detail = str(exc) or type(exc).__name__
            raise PdfDownloadError(f"PDF 下载失败：{detail}") from exc

        return DownloadedPdf(
            path=destination,
            source_url=paper.pdf_url,
            size_bytes=size,
        )


class PaperCatalog:
    """Search trusted providers, download PDFs and persist them into collections."""

    def __init__(
        self,
        library: PaperLibrary,
        download_root: Path,
        *,
        arxiv: PaperSearchClient | None = None,
        openalex: PaperSearchClient | None = None,
        downloader: PdfDownloader | None = None,
    ) -> None:
        self.library = library
        self.download_root = download_root.resolve()
        self.arxiv = arxiv or ArxivSearchClient()
        self.openalex = openalex or OpenAlexSearchClient()
        self.downloader = downloader or PdfDownloader(self.download_root)
        self._results: dict[tuple[str, str], Paper] = {}

    async def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
        source: str = "auto",
    ) -> list[Paper]:
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("query cannot be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        clients: dict[str, PaperSearchClient] = {
            "arxiv": self.arxiv,
            "openalex": self.openalex,
        }
        if source == "auto":
            client: PaperSearchClient = FallbackSearchClient(
                [self.arxiv, self.openalex]
            )
        elif source in clients:
            client = clients[source]
        else:
            raise ValueError("source must be auto, arxiv or openalex")

        papers = await client.search(clean_query, limit, category)
        for paper in papers:
            self._results[(paper.source, paper.paper_id)] = paper.model_copy(deep=True)
        return papers

    async def download_to_collection(
        self,
        source: str,
        paper_id: str,
        *,
        collection_id: int | None = None,
        collection_name: str | None = None,
    ) -> PaperLibraryItem:
        paper = self._results.get((source, paper_id))
        if paper is None:
            raise KeyError("请先搜索该论文，再执行下载")
        if collection_id is None and not (collection_name or "").strip():
            raise ValueError("请选择已有分类或输入新分类名称")
        if collection_id is not None and not self.library.collection_exists(
            collection_id
        ):
            raise KeyError("collection not found")

        downloaded = await self.downloader.download(paper)
        return await asyncio.to_thread(
            self.library.import_downloaded_paper,
            paper,
            local_path=downloaded.path,
            source_url=downloaded.source_url,
            size_bytes=downloaded.size_bytes,
            collection_id=collection_id,
            collection_name=collection_name,
        )

    def resolve_download(self, download_id: int) -> tuple[Path, str] | None:
        record = self.library.get_download(download_id)
        if record is None:
            return None
        path = Path(record.local_path).resolve()
        try:
            path.relative_to(self.download_root)
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path, record.filename


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:180] or "paper"
