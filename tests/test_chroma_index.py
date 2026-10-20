"""Real persistent Chroma tests; only embeddings are deterministic test fixtures."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from paper_agent.core.models import EvidenceChunk, Paper
from paper_agent.tools.chroma_index import ChromaVectorIndex


class CountingEmbedder:
    def __init__(self):
        self.documents = 0
        self.queries = 0

    async def embed(self, texts):
        self.documents += len(texts)
        return [[1.0, 0.1] if 'method' in text else [0.1, 1.0] for text in texts]

    async def embed_query(self, texts):
        self.queries += len(texts)
        return [[1.0, 0.1] for _ in texts]


def paper(identifier='p1'):
    return Paper(paper_id=identifier, source='arxiv', title='Paper ' + identifier,
                 authors=['A'], abstract='abstract', page_url='https://example.org/' + identifier,
                 pdf_url='https://example.org/' + identifier + '.pdf')


def chunks(identifier='p1', text='method evidence'):
    return [EvidenceChunk(chunk_id=identifier + ':p3:c0', paper_id=identifier,
                          text=text, source_url='https://example.org/' + identifier + '.pdf', page_number=3)]


class ChromaIndexTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.embedder = CountingEmbedder()

    async def asyncTearDown(self):
        # Chroma retains native handles for the process lifetime on Windows.
        try:
            self.directory.cleanup()
        except PermissionError:
            self.directory._finalizer.detach()

    def index(self, namespace='user:1', embedding_id='test:v1', dimensions=2):
        return ChromaVectorIndex(self.embedder, path=self.path, namespace=namespace,
                                 embedding_id=embedding_id, dimensions=dimensions)

    async def test_write_reopen_no_reembedding_and_original_citations(self):
        original = self.index()
        await original.replace_paper(paper(), chunks(), 'pdf', 'chunk:v1')
        reopened = self.index()
        self.assertEqual(await reopened.search('method'), [])
        self.assertTrue(await reopened.load_paper(paper(), 'pdf', 'chunk:v1'))
        result = await reopened.search('method')
        self.assertEqual(result[0].chunk_id, 'p1:p3:c0')
        self.assertEqual(result[0].page_number, 3)
        self.assertEqual(result[0].source_url, paper().pdf_url)
        self.assertAlmostEqual(result[0].score, 1.0, places=5)
        self.assertEqual(self.embedder.documents, 1)
        self.assertEqual(self.embedder.queries, 1)
        self.assertEqual(reopened.source_mode_for('p1'), 'pdf')

    async def test_duplicate_upsert_and_selected_paper_account_model_recipe_scope(self):
        first = self.index()
        await first.replace_paper(paper(), chunks(), 'pdf', 'v1')
        await first.replace_paper(paper(), chunks(), 'pdf', 'v1')
        await first.replace_paper(paper('p2'), chunks('p2'), 'pdf', 'v1')
        selected = self.index()
        self.assertTrue(await selected.load_paper(paper(), 'pdf', 'v1'))
        self.assertEqual([c.paper_id for c in await selected.search('method')], ['p1'])
        self.assertEqual(await selected.search('method', paper_id='p2'), [])
        self.assertFalse(await self.index('user:2').load_paper(paper(), 'pdf', 'v1'))
        self.assertFalse(await self.index(embedding_id='test:v2').load_paper(paper(), 'pdf', 'v1'))
        self.assertFalse(await self.index(dimensions=3).load_paper(paper(), 'pdf', 'v1'))
        self.assertFalse(await self.index().load_paper(paper(), 'pdf', 'v2'))
        self.assertFalse(await self.index().load_paper(paper(), 'abstract', 'v1'))
        edited = paper().model_copy(update={'title': 'Edited title'})
        self.assertFalse(await self.index().load_paper(edited, 'pdf', 'v1'))

    async def test_rebuild_preserves_old_active_revision_and_new_load_uses_latest(self):
        old = self.index()
        await old.replace_paper(paper(), chunks(text='method old body'), 'pdf', 'v1')
        new = self.index()
        await new.replace_paper(paper(), chunks(text='method new body'), 'pdf', 'v1')
        self.assertEqual((await old.search('method'))[0].text, 'method old body')
        latest = self.index()
        self.assertTrue(await latest.load_paper(paper(), 'pdf', 'v1'))
        self.assertEqual((await latest.search('method'))[0].text, 'method new body')

    async def test_failed_write_cannot_be_loaded_or_selected(self):
        index = self.index()
        await index._ensure_ready()
        collection_type = type(index._chunks)
        actual = collection_type.upsert
        def fail_chunks(collection, *args, **kwargs):
            if collection.name == index._chunks.name:
                raise RuntimeError('simulated interrupted write')
            return actual(collection, *args, **kwargs)
        with patch.object(collection_type, 'upsert', fail_chunks):
            with self.assertRaises(RuntimeError):
                await index.replace_paper(paper(), chunks(), 'pdf', 'v1')
        self.assertFalse(await self.index().load_paper(paper(), 'pdf', 'v1'))
        self.assertEqual(await index.search('method'), [])

    async def test_partial_batch_failure_never_publishes_incomplete_revision(self):
        index = self.index()
        await index._ensure_ready()
        collection_type = type(index._chunks)
        actual = collection_type.upsert
        calls = 0
        def fail_second_batch(collection, *args, **kwargs):
            nonlocal calls
            if collection.name == index._chunks.name:
                calls += 1
                if calls == 2:
                    raise RuntimeError('interrupted after first durable batch')
            return actual(collection, *args, **kwargs)
        many = [chunks()[0].model_copy(update={'chunk_id': f'p1:p{i}:c0'})
                for i in range(129)]
        with patch.object(collection_type, 'upsert', fail_second_batch):
            with self.assertRaises(RuntimeError):
                await index.replace_paper(paper(), many, 'pdf', 'v1')
        self.assertEqual(index._chunks.count(), 128)
        self.assertFalse(await self.index().load_paper(paper(), 'pdf', 'v1'))
        self.assertEqual(await index.search('method'), [])

    async def test_manifest_count_revalidated_and_active_reset(self):
        index = self.index()
        await index.replace_paper(paper(), chunks(), 'pdf', 'v1')
        index.reset_active()
        self.assertEqual(await index.search('method'), [])
        persisted = index._chunks.get(include=[])
        index._chunks.delete(ids=persisted['ids'])
        self.assertFalse(await self.index().load_paper(paper(), 'pdf', 'v1'))

    async def test_invalid_chunk_and_vector_rejected_before_publish(self):
        index = self.index()
        with self.assertRaises(ValueError):
            await index.replace_paper(paper(), chunks('other'), 'pdf', 'v1')
        for vector in ([0., 0.], [float('nan'), 1.], [1.], [float('inf'), 0.]):
            async def invalid(texts, vector=vector):
                return [vector for _ in texts]
            with patch.object(self.embedder, 'embed', invalid):
                with self.assertRaises(ValueError):
                    await index.replace_paper(paper(), chunks(), 'pdf', 'v1')
        self.assertFalse(await self.index().load_paper(paper(), 'pdf', 'v1'))

    async def test_separate_process_can_reopen_durable_index(self):
        await self.index().replace_paper(paper(), chunks(), 'pdf', 'v1')
        code = '''import asyncio, json, sys
from pathlib import Path
from paper_agent.core.models import Paper
from paper_agent.tools.chroma_index import ChromaVectorIndex
class E:
 async def embed(self, texts): return [[1.0, .1] for _ in texts]
async def main():
 i=ChromaVectorIndex(E(),path=Path(sys.argv[1]),namespace='user:1',embedding_id='test:v1',dimensions=2)
 assert await i.load_paper(Paper.model_validate_json(sys.argv[2]),'pdf','v1')
 print(json.dumps([c.chunk_id for c in await i.search('method')]))
asyncio.run(main())'''
        completed = await asyncio.to_thread(subprocess.run, [sys.executable, '-c', code,
                                            str(self.path), paper().model_dump_json()],
                                            capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout.strip().splitlines()[-1]), ['p1:p3:c0'])
