import asyncio
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from paper_agent.tools.local_embeddings import LocalMultilingualEmbedder, LocalEmbeddingError, prepare_model
from paper_agent.core.models import EvidenceChunk


class FakeTokenizer:
    def __init__(self):
        self.texts = []

    def encode_batch(self, texts):
        self.texts.extend(texts)
        return [SimpleNamespace(ids=[1, 2, 0], attention_mask=[1, 1, 0], type_ids=[0, 0, 0]) for _ in texts]


class FakeSession:
    def get_inputs(self):
        return [SimpleNamespace(name='input_ids'), SimpleNamespace(name='attention_mask')]

    def run(self, _, inputs):
        batch = len(inputs['input_ids'])
        hidden = np.zeros((batch, 3, 384), dtype=np.float32)
        hidden[:, 0, 0] = 2
        hidden[:, 1, 1] = 2
        hidden[:, 2, 2] = 1000  # Padding must contribute nothing.
        return [hidden]


class LocalEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepared_default_cache_does_not_need_network(self):
        def cached_file(**kwargs):
            self.assertTrue(kwargs.get('local_files_only'))
            return str(Path('cached') / kwargs['filename'])
        with patch('huggingface_hub.hf_hub_download', side_effect=cached_file) as download:
            self.assertEqual(prepare_model(), Path('cached'))
            self.assertEqual(download.call_count, 2)

    async def test_prefixes_masked_mean_normalization_and_batches(self):
        embedder = LocalMultilingualEmbedder(batch_size=2)
        tokenizer = FakeTokenizer()
        runtime = SimpleNamespace(tokenizer=tokenizer, session=FakeSession(), lock=threading.Lock())
        with patch.object(embedder, '_runtime', return_value=runtime):
            vectors = await embedder.embed(['one', 'two', 'three'])
            queries = await embedder.embed_query(['question'])
        self.assertEqual(tokenizer.texts, ['passage: one', 'passage: two', 'passage: three', 'query: question'])
        self.assertEqual(len(vectors), 3)
        self.assertEqual(len(queries[0]), 384)
        self.assertAlmostEqual(vectors[0][0], 2 ** -0.5, places=6)
        self.assertEqual(vectors[0][2], 0)
        self.assertAlmostEqual(sum(x*x for x in vectors[0]), 1, places=6)

    async def test_empty_does_not_load_or_download_model(self):
        embedder = LocalMultilingualEmbedder()
        with patch.object(embedder, '_runtime', side_effect=AssertionError('loaded')):
            self.assertEqual(await embedder.embed([]), [])
        self.assertEqual(embedder.dimensions, 384)
        self.assertIn('761b726dd34fb83930e26aab4e9ac3899aa1fa78', embedder.embedding_id)

    async def test_runtime_failure_is_safe_and_not_replaced_with_hash_vectors(self):
        embedder = LocalMultilingualEmbedder()
        with patch.object(embedder, '_runtime', side_effect=RuntimeError('private filesystem path')):
            with self.assertRaises(LocalEmbeddingError) as error:
                await embedder.embed(['text'])
        self.assertNotIn('private', str(error.exception))

    async def test_local_identity_changes_with_file_content(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'onnx').mkdir()
            (path / 'onnx/model_quantized.onnx').write_bytes(b'model-one')
            (path / 'tokenizer.json').write_bytes(b'tokenizer-one')
            first = LocalMultilingualEmbedder(model_dir=path).embedding_id
            (path / 'onnx/model_quantized.onnx').write_bytes(b'model-two')
            second = LocalMultilingualEmbedder(model_dir=path).embedding_id
            self.assertNotEqual(first, second)

    async def test_unchanged_model_hash_is_shared_across_instances(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'onnx').mkdir()
            (path / 'onnx/model_quantized.onnx').write_bytes(b'shared-model')
            (path / 'tokenizer.json').write_bytes(b'shared-tokenizer')
            with patch('paper_agent.tools.local_embeddings.hashlib.sha256', wraps=hashlib.sha256) as digest:
                first = LocalMultilingualEmbedder(model_dir=path).embedding_id
                second = LocalMultilingualEmbedder(model_dir=path).embedding_id
                self.assertEqual(first, second)
                self.assertEqual(digest.call_count, 1)

    async def test_invalid_text_and_batch_size_are_rejected(self):
        with self.assertRaises(ValueError):
            LocalMultilingualEmbedder(batch_size=0)
        with self.assertRaises(ValueError):
            await LocalMultilingualEmbedder().embed([''])

    async def test_split_chunks_preserves_tail_and_page_without_truncation(self):
        class CharacterTokenizer:
            def no_truncation(self): pass
            def enable_truncation(self, **kwargs): pass
            def encode(self, text):
                return SimpleNamespace(ids=list(range(len(text))))
        model = LocalMultilingualEmbedder()
        runtime = SimpleNamespace(tokenizer=CharacterTokenizer(), lock=threading.Lock())
        chunk = EvidenceChunk(chunk_id='paper:p7:c0', paper_id='paper', text='a'*1000+'TAIL', source_url='https://example.org/paper.pdf', page_number=7)
        with patch.object(model, '_runtime', return_value=runtime):
            parts = await model.split_chunks([chunk])
        self.assertGreater(len(parts), 1)
        self.assertEqual(''.join(p.text for p in parts), chunk.text)
        self.assertTrue(all(len('passage: '+p.text) <= 500 for p in parts))
        self.assertTrue(all(p.page_number == 7 and p.source_url == chunk.source_url for p in parts))
        self.assertEqual(len({p.chunk_id for p in parts}), len(parts))


if __name__ == '__main__':
    unittest.main()
