"""Persistent, explicitly scoped paper evidence index backed by local Chroma."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path
import threading
from typing import Any

from paper_agent.core.models import EvidenceChunk, Paper


_LOCK = threading.RLock()
_BATCH_SIZE = 128


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


class ChromaVectorIndex:
    """Only complete revisions explicitly loaded by this instance are searchable.

    A manifest is the atomic publication pointer. Immutable chunk revisions are
    retained so existing tasks keep their original evidence during a rebuild.
    Chroma performs durable upserts before that pointer is published.
    """

    def __init__(self, embedder, *, path: Path, namespace: str,
                 embedding_id: str, dimensions: int) -> None:
        if not namespace.strip() or not embedding_id.strip() or dimensions < 1:
            raise ValueError('index namespace, embedding identity and dimensions are required')
        self.embedder = embedder
        self.path = Path(path).resolve()
        self.namespace = namespace
        self.embedding_id = embedding_id
        self.dimensions = dimensions
        self._collection_key = _digest([embedding_id, dimensions])[:32]
        self._client = None
        self._chunks = None
        self._manifests = None
        self._active: dict[str, tuple[str, str]] = {}

    async def _ensure_ready(self) -> None:
        if self._client is None:
            await asyncio.to_thread(self._open)

    def _open(self) -> None:
        with _LOCK:
            if self._client is not None:
                return
            import chromadb
            from chromadb.config import Settings
            client = chromadb.PersistentClient(
                path=str(self.path), settings=Settings(anonymized_telemetry=False))
            chunks = client.get_or_create_collection(
                name='paper-chunks-' + self._collection_key,
                embedding_function=None, metadata={'hnsw:space': 'cosine'})
            manifests = client.get_or_create_collection(
                name='paper-manifests-' + self._collection_key, embedding_function=None)
            self._chunks, self._manifests, self._client = chunks, manifests, client

    def _identity(self, paper: Paper, source_mode: str, recipe: str) -> str:
        if not source_mode.strip() or not recipe.strip():
            raise ValueError('source mode and chunk recipe are required')
        return _digest([self.namespace, paper.model_dump(mode='json'),
                        self.embedding_id, self.dimensions, recipe, source_mode])

    async def load_paper(self, paper: Paper, source_mode: str, recipe: str) -> bool:
        identity = self._identity(paper, source_mode, recipe)
        await self._ensure_ready()
        revision = await asyncio.to_thread(self._load_revision, identity)
        if revision is None:
            self._active.pop(paper.paper_id, None)
            return False
        self._active[paper.paper_id] = (revision, source_mode)
        return True

    def _load_revision(self, identity: str) -> str | None:
        with _LOCK:
            found = self._manifests.get(ids=[identity], include=['metadatas'])
            if not found['ids']:
                return None
            metadata = found['metadatas'][0]
            if metadata.get('namespace') != self.namespace:
                return None
            revision = metadata['revision']
            count = metadata['chunk_count']
            records = self._chunks.get(where=self._where([revision]), include=[])
            if count < 1 or len(records['ids']) != count:
                return None
            return revision

    def reset_active(self) -> None:
        self._active.clear()

    def source_mode_for(self, paper_id: str) -> str:
        selected = self._active.get(paper_id)
        return selected[1] if selected else 'unknown'

    async def replace_paper(self, paper: Paper, chunks: list[EvidenceChunk],
                            source_mode: str, recipe: str) -> None:
        identity = self._identity(paper, source_mode, recipe)
        if not chunks or any(c.paper_id != paper.paper_id or not c.text.strip() or
                             not c.chunk_id.strip() for c in chunks):
            raise ValueError('paper requires nonempty matching evidence chunks')
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError('duplicate evidence chunk identities')
        bodies = [{k: v for k, v in c.model_dump(mode='json').items() if k != 'score'}
                  for c in chunks]
        body_hash = _digest(bodies)
        revision = _digest([identity, body_hash])
        vectors: list[list[float]] = []
        # Bounded batches also bound local embedding peak memory.
        for start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[start:start + _BATCH_SIZE]
            generated = await self.embedder.embed([c.text for c in batch])
            self._validate_vectors(generated, len(batch))
            vectors.extend(generated)
        await self._ensure_ready()
        await asyncio.to_thread(self._publish, paper, chunks, vectors, identity,
                                revision, body_hash, source_mode, recipe)
        self._active[paper.paper_id] = (revision, source_mode)

    def _validate_vectors(self, vectors, count: int) -> None:
        if len(vectors) != count:
            raise ValueError('embedding count does not match evidence')
        for vector in vectors:
            if (len(vector) != self.dimensions or
                    any(not math.isfinite(float(value)) for value in vector) or
                    not any(float(value) != 0 for value in vector)):
                raise ValueError('embedding must have finite, nonzero configured dimensions')

    def _publish(self, paper, chunks, vectors, identity, revision, body_hash,
                 source_mode, recipe) -> None:
        with _LOCK:
            for start in range(0, len(chunks), _BATCH_SIZE):
                batch = chunks[start:start + _BATCH_SIZE]
                self._chunks.upsert(
                    ids=[_digest([revision, c.chunk_id]) for c in batch],
                    documents=[c.text for c in batch],
                    embeddings=vectors[start:start + _BATCH_SIZE],
                    metadatas=[{
                        'namespace': self.namespace, 'paper_id': paper.paper_id,
                        'source': paper.source, 'revision': revision,
                        'body_hash': body_hash, 'identity': identity,
                        'chunk_id': c.chunk_id, 'source_url': c.source_url,
                        'page_number': c.page_number if c.page_number is not None else 0,
                        'source_mode': source_mode, 'recipe': recipe,
                        'embedding_id': self.embedding_id,
                    } for c in batch])
            persisted = self._chunks.get(where=self._where([revision]), include=[])
            if len(persisted['ids']) != len(chunks):
                raise RuntimeError('incomplete evidence index; revision not published')
            self._manifests.upsert(ids=[identity], embeddings=[[1.0]],
                                   metadatas=[{'namespace': self.namespace,
                                               'revision': revision,
                                               'chunk_count': len(chunks),
                                               'body_hash': body_hash}])

    def _where(self, revisions: list[str]) -> dict:
        return {'$and': [{'namespace': {'$eq': self.namespace}},
                         {'revision': {'$in': revisions}}]}

    async def search(self, query: str, top_k: int = 8,
                     paper_id: str | None = None) -> list[EvidenceChunk]:
        if top_k < 1:
            raise ValueError('top_k must be positive')
        bindings = ([self._active[paper_id]] if paper_id in self._active else []) \
            if paper_id is not None else list(self._active.values())
        if not bindings:
            return []
        query_embed = getattr(self.embedder, 'embed_query', self.embedder.embed)
        vectors = await query_embed([query])
        self._validate_vectors(vectors, 1)
        await self._ensure_ready()
        result = await asyncio.to_thread(
            self._chunks.query, query_embeddings=vectors, n_results=top_k,
            where=self._where([binding[0] for binding in bindings]),
            include=['documents', 'metadatas', 'distances'])
        found = []
        for text, metadata, distance in zip(result['documents'][0], result['metadatas'][0],
                                             result['distances'][0], strict=True):
            found.append(EvidenceChunk(chunk_id=metadata['chunk_id'],
                                       paper_id=metadata['paper_id'], text=text,
                                       source_url=metadata['source_url'],
                                       page_number=metadata['page_number'] or None,
                                       score=1.0 - float(distance)))
        return sorted(found, key=lambda c: (-c.score, c.chunk_id))
