from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx
from openai import AsyncOpenAI

from paper_agent.context import ContextBuilder
from paper_agent.models import ContextPacket, EvidenceChunk, Paper


TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
ANALYSIS_QUERIES = (
    "research problem motivation limitation",
    "method architecture algorithm implementation",
    "experiment dataset metric result conclusion",
)


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic local embedding for offline demos and tests."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 8:
            raise ValueError("dimensions must be at least 8")
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            index = value % self.dimensions
            sign = 1.0 if value & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OpenAICompatibleEmbedder:
    """Embedding adapter for Qwen/DashScope or another compatible endpoint."""

    def __init__(self, client: AsyncOpenAI, model: str, batch_size: int = 20) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.client = client
        self.model = model
        self.batch_size = batch_size

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = await self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            embeddings.extend(
                item.embedding
                for item in sorted(response.data, key=lambda item: item.index)
            )
        return embeddings


@dataclass
class _IndexedChunk:
    chunk: EvidenceChunk
    embedding: list[float]


class VectorIndex:
    """Small inspectable vector index suitable for a portfolio project."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._items: list[_IndexedChunk] = []

    async def add(self, chunks: list[EvidenceChunk]) -> None:
        embeddings = await self.embedder.embed([chunk.text for chunk in chunks])
        self._items.extend(
            _IndexedChunk(chunk=chunk, embedding=embedding)
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        )

    async def search(
        self, query: str, top_k: int = 8, paper_id: str | None = None
    ) -> list[EvidenceChunk]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query_vectors = await self.embedder.embed([query])
        if not query_vectors:
            return []
        query_vector = query_vectors[0]
        scored = []
        for item in self._items:
            if paper_id is not None and item.chunk.paper_id != paper_id:
                continue
            score = _cosine(query_vector, item.embedding)
            scored.append(item.chunk.model_copy(update={"score": score}))
        return sorted(scored, key=lambda item: (-item.score, item.chunk_id))[:top_k]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "chunk": item.chunk.model_dump(mode="json"),
                "embedding": item.embedding,
            }
            for item in self._items
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def load(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._items = [
            _IndexedChunk(
                chunk=EvidenceChunk.model_validate(item["chunk"]),
                embedding=item["embedding"],
            )
            for item in payload
        ]


class TextChunker:
    def __init__(self, chunk_size: int = 2400, overlap: int = 300) -> None:
        if chunk_size < 100:
            raise ValueError("chunk_size must be at least 100 characters")
        if not 0 <= overlap < chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(
        self,
        paper: Paper,
        pages: list[tuple[int | None, str]],
    ) -> list[EvidenceChunk]:
        chunks: list[EvidenceChunk] = []
        for page_number, text in pages:
            clean = " ".join(text.split())
            start = 0
            part = 0
            while start < len(clean):
                end = min(len(clean), start + self.chunk_size)
                passage = clean[start:end].strip()
                if passage:
                    page_label = page_number if page_number is not None else 0
                    chunks.append(
                        EvidenceChunk(
                            chunk_id=f"{paper.paper_id}:p{page_label}:c{part}",
                            paper_id=paper.paper_id,
                            text=passage,
                            source_url=paper.pdf_url or paper.page_url,
                            page_number=page_number,
                        )
                    )
                    part += 1
                if end == len(clean):
                    break
                start = end - self.overlap
        return chunks


class PdfLoader:
    def __init__(self, timeout_seconds: float = 30.0, max_bytes: int = 25_000_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    async def load(self, url: str) -> list[tuple[int, str]]:
        _validate_remote_url(url)
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        if len(response.content) > self.max_bytes:
            raise ValueError("PDF exceeds configured size limit")

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(response.content))
        return [
            (index, page.extract_text() or "")
            for index, page in enumerate(reader.pages, start=1)
        ]


class PaperRAG:
    """Index paper evidence, retrieve it, and build budgeted Agent context."""

    def __init__(
        self,
        embedder: Embedder,
        *,
        include_pdfs: bool = False,
        top_k_per_query: int = 4,
        context_builder: ContextBuilder | None = None,
        index_path: Path | None = None,
        pdf_loader: PdfLoader | None = None,
        chunker: TextChunker | None = None,
    ) -> None:
        self.index = VectorIndex(embedder)
        self.include_pdfs = include_pdfs
        self.top_k_per_query = top_k_per_query
        self.context_builder = context_builder or ContextBuilder()
        self.index_path = index_path
        self.pdf_loader = pdf_loader or PdfLoader()
        self.chunker = chunker or TextChunker()
        self._source_modes: dict[str, str] = {}

    async def index_papers(self, papers: list[Paper]) -> None:
        all_chunks: list[EvidenceChunk] = []
        for paper in papers:
            pages: list[tuple[int | None, str]]
            source_mode = "abstract"
            if self.include_pdfs and paper.pdf_url:
                try:
                    pages = await self.pdf_loader.load(paper.pdf_url)
                    pages = [page for page in pages if page[1].strip()]
                    if not pages:
                        raise ValueError("PDF contains no extractable text")
                    source_mode = "pdf"
                except (httpx.HTTPError, ValueError, OSError):
                    pages = [(None, paper.abstract)]
                    source_mode = "abstract_fallback"
            else:
                pages = [(None, paper.abstract)]
            self._source_modes[paper.paper_id] = source_mode
            all_chunks.extend(self.chunker.split(paper, pages))
        await self.index.add(all_chunks)
        if self.index_path is not None:
            self.index.save(self.index_path)

    async def build_analysis_context(self, paper: Paper) -> ContextPacket:
        candidates: list[EvidenceChunk] = []
        for query in ANALYSIS_QUERIES:
            candidates.extend(
                await self.index.search(
                    query,
                    top_k=self.top_k_per_query,
                    paper_id=paper.paper_id,
                )
            )
        return self.context_builder.build(" | ".join(ANALYSIS_QUERIES), candidates)

    async def retrieve(
        self, query: str, top_k: int = 5, paper_id: str | None = None
    ) -> ContextPacket:
        candidates = await self.index.search(query, top_k=top_k, paper_id=paper_id)
        return self.context_builder.build(query, candidates)

    def source_mode_for(self, paper_id: str) -> str:
        return self._source_modes.get(paper_id, "unknown")


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left)) or 1.0
    right_norm = math.sqrt(sum(value * value for value in right)) or 1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("only public HTTPS PDF URLs are allowed")
    if parsed.hostname.lower() == "localhost":
        raise ValueError("local PDF URLs are not allowed")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("private or local PDF addresses are not allowed")
