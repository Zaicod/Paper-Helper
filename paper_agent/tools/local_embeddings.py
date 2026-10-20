"""Pinned multilingual E5 embeddings with a local ONNX CPU runtime.

The model is loaded lazily. No remote Python code, hosted inference, or API key
is used. Documents use E5's ``passage:`` prefix and queries use ``query:``.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paper_agent.core.models import EvidenceChunk
from paper_agent.core.errors import PublicResearchError

MODEL_REPOSITORY = 'Xenova/multilingual-e5-small'
MODEL_REVISION = '761b726dd34fb83930e26aab4e9ac3899aa1fa78'
MODEL_FILENAME = 'onnx/model_quantized.onnx'
MODEL_FILES = ('tokenizer.json', MODEL_FILENAME)
_RECIPE = 'e5-query-passage-masked-mean-l2-max512-v1'


class LocalEmbeddingError(PublicResearchError):
    """Safe actionable error; callers must not silently use another embedder."""


def prepare_model(output_dir: Path | None = None) -> Path:
    """Download only the pinned tokenizer and quantized ONNX weights."""
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    locations = []
    for filename in MODEL_FILES:
        options = dict(repo_id=MODEL_REPOSITORY, filename=filename,
                       revision=MODEL_REVISION, token=False, local_dir=output_dir)
        try:
            location = hf_hub_download(**options, local_files_only=True)
        except LocalEntryNotFoundError:
            location = hf_hub_download(**options)
        locations.append(Path(location))
    return locations[0].parent


@dataclass
class _Runtime:
    tokenizer: Any
    session: Any
    lock: threading.Lock


_RUNTIMES: dict[str, _Runtime] = {}
_LOAD_LOCK = threading.Lock()
_FILE_DIGESTS: dict[tuple, str] = {}
_DIGEST_LOCK = threading.Lock()


def _local_digest(folder: Path) -> str:
    # Reuse the 118MB weight hash across task-specific embedder instances.
    # File replacement or modification invalidates this per-process cache.
    files = [folder / filename for filename in MODEL_FILES]
    fingerprint = tuple((str(path), s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                        for path in files for s in [path.stat()])
    with _DIGEST_LOCK:
        if fingerprint not in _FILE_DIGESTS:
            digest = hashlib.sha256()
            for filename, path in zip(MODEL_FILES, files):
                digest.update(filename.encode())
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
            _FILE_DIGESTS[fingerprint] = digest.hexdigest()
        return _FILE_DIGESTS[fingerprint]


class LocalMultilingualEmbedder:
    dimensions = 384

    def __init__(self, model_dir: str | Path | None = None, batch_size: int = 8):
        if not 1 <= batch_size <= 64:
            raise ValueError('batch_size must be between 1 and 64')
        configured = model_dir or os.getenv('PAPERFLOW_EMBEDDING_MODEL_DIR')
        self.model_dir = Path(configured).expanduser().resolve() if configured else None
        self.batch_size = batch_size
        self._identity: str | None = None

    @property
    def embedding_id(self) -> str:
        if self._identity is None:
            identity = f'{MODEL_REPOSITORY}@{MODEL_REVISION}:{MODEL_FILENAME}:{_RECIPE}'
            if self.model_dir:
                try:
                    digest = _local_digest(self.model_dir)
                except OSError as error:
                    raise LocalEmbeddingError('本地向量模型文件不完整，请运行 scripts/prepare_embeddings.py 或检查 PAPERFLOW_EMBEDDING_MODEL_DIR。') from error
                identity += f':sha256-{digest}'
            self._identity = identity
        return self._identity

    def _runtime(self) -> _Runtime:
        identity = self.embedding_id
        with _LOAD_LOCK:
            if identity not in _RUNTIMES:
                from tokenizers import Tokenizer
                import onnxruntime as ort

                folder = self.model_dir or prepare_model()
                tokenizer = Tokenizer.from_file(str(folder / 'tokenizer.json'))
                tokenizer.enable_truncation(max_length=512)
                tokenizer.enable_padding(pad_id=1, pad_token='<pad>')
                options = ort.SessionOptions()
                options.intra_op_num_threads = min(4, os.cpu_count() or 1)
                options.inter_op_num_threads = 1
                session = ort.InferenceSession(
                    str(folder / MODEL_FILENAME), sess_options=options,
                    providers=['CPUExecutionProvider'],
                )
                _RUNTIMES[identity] = _Runtime(tokenizer, session, threading.Lock())
            return _RUNTIMES[identity]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, 'passage: ')

    async def embed_query(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, 'query: ')

    async def split_chunks(self, chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
        """Keep every character while bounding passages to 500 model tokens.

        This runs before indexing so retrieval citations point at the actual
        encoded passage, rather than a longer chunk with a silently lost tail.
        """
        if not chunks:
            return []
        try:
            return await asyncio.to_thread(self._split_chunks, chunks)
        except LocalEmbeddingError:
            raise
        except Exception as error:
            raise LocalEmbeddingError('论文语义分块失败，请检查本地向量模型。') from error

    def _split_chunks(self, chunks: list[EvidenceChunk]) -> list[EvidenceChunk]:
        runtime = self._runtime()
        result = []
        with runtime.lock:
            runtime.tokenizer.no_truncation()
            try:
                for chunk in chunks:
                    text = chunk.text
                    pieces = []
                    while text:
                        if len(runtime.tokenizer.encode('passage: ' + text).ids) <= 500:
                            pieces.append(text)
                            break
                        low, high, best = 1, len(text), 0
                        while low <= high:
                            midpoint = (low + high) // 2
                            if len(runtime.tokenizer.encode('passage: ' + text[:midpoint]).ids) <= 500:
                                best, low = midpoint, midpoint + 1
                            else:
                                high = midpoint - 1
                        if not best:
                            raise LocalEmbeddingError('论文片段无法在模型词数限制内编码。')
                        pieces.append(text[:best])
                        text = text[best:]
                    for number, piece in enumerate(pieces):
                        result.append(chunk.model_copy(update={
                            'text': piece,
                            'chunk_id': chunk.chunk_id if len(pieces) == 1 else f'{chunk.chunk_id}:t{number}',
                        }))
            finally:
                runtime.tokenizer.enable_truncation(max_length=512)
        return result

    async def _embed(self, texts: list[str], prefix: str) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError('Embedding input must contain non-empty text')
        try:
            return await asyncio.to_thread(self._encode, texts, prefix)
        except LocalEmbeddingError:
            raise
        except Exception as error:
            raise LocalEmbeddingError('本地论文向量模型加载或推理失败，请安装 RAG 依赖并运行 scripts/prepare_embeddings.py 检查模型。') from error

    def _encode(self, texts: list[str], prefix: str) -> list[list[float]]:
        import numpy as np

        runtime = self._runtime()
        results: list[list[float]] = []
        # Tokenizer settings and inference are shared; serialize their use while
        # keeping CPU work off the asyncio event loop.
        with runtime.lock:
            for start in range(0, len(texts), self.batch_size):
                encoded = runtime.tokenizer.encode_batch([prefix + t for t in texts[start:start + self.batch_size]])
                inputs = {
                    'input_ids': np.asarray([e.ids for e in encoded], dtype=np.int64),
                    'attention_mask': np.asarray([e.attention_mask for e in encoded], dtype=np.int64),
                    'token_type_ids': np.asarray([e.type_ids for e in encoded], dtype=np.int64),
                }
                feeds = {item.name: inputs[item.name] for item in runtime.session.get_inputs()}
                hidden = runtime.session.run(None, feeds)[0]
                mask = inputs['attention_mask'][..., None]
                pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
                norms = np.linalg.norm(pooled, axis=1, keepdims=True)
                if pooled.shape != (len(encoded), self.dimensions) or not np.isfinite(pooled).all() or (norms <= 0).any():
                    raise LocalEmbeddingError('本地向量模型输出无效，请重新准备模型文件。')
                results.extend((pooled / norms).tolist())
        return results
