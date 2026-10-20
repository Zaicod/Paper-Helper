"""Real storage with explicitly controlled embeddings/PDF/Agent boundaries."""
import asyncio
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from paper_agent.services.research import ResearchOptions, ResearchService
from paper_agent.tools.chroma_index import ChromaVectorIndex
from paper_agent.tools.rag import HashingEmbedder, PaperRAG
from tests.test_study_report import FakeLoader, FakeTeam, paper


def index(path, namespace='account-a'):
    return ChromaVectorIndex(HashingEmbedder(), path=path, namespace=namespace,
                             embedding_id='test-only-hash', dimensions=256)


@contextmanager
def storage_directory():
    with tempfile.TemporaryDirectory() as directory:
        try:
            yield directory
        finally:
            # Stop test-owned native handles before Windows removes this directory.
            from chromadb.api.client import SharedSystemClient
            for system in list(SharedSystemClient._identifier_to_system.values()):
                system.stop()
            SharedSystemClient.clear_system_cache()


class ChromaWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_cache_reopens_without_pdf_or_document_embeddings(self):
        with storage_directory() as directory:
            class Loader:
                calls = 0
                async def load(self, url):
                    self.calls += 1
                    return [(1, 'method architecture and experiment results')]
            loader = Loader()
            first = PaperRAG(HashingEmbedder(), index=index(Path(directory)),
                             include_pdfs=True, pdf_loader=loader)
            await first.index_papers([paper(), paper('p2')])
            second = PaperRAG(HashingEmbedder(), index=index(Path(directory)),
                              include_pdfs=True, pdf_loader=loader)
            await second.index_papers([paper()])
            self.assertEqual(loader.calls, 2)
            self.assertEqual(second.source_mode_for('p1'), 'pdf')
            self.assertTrue((await second.build_analysis_context(paper())).chunks)
            self.assertEqual((await second.retrieve('method', paper_id='p2')).chunks, [])
            changed = paper().model_copy(update={'pdf_url': 'https://arxiv.org/pdf/2601.99999'})
            await second.index_papers([changed])
            self.assertEqual(loader.calls, 3)

    async def test_study_uses_persistent_semantic_queries_and_explicit_rebuild(self):
        from paper_agent.services.study import StudyService
        with storage_directory() as directory:
            class Loader(FakeLoader):
                calls = 0
                async def load(self, p):
                    self.calls += 1
                    return await super().load(p)
            loader = Loader()
            for rebuild in (False, False, True):
                store = index(Path(directory))
                queries = []
                original = store.search
                async def search(query, **kwargs):
                    queries.append(query)
                    return await original(query, **kwargs)
                store.search = search
                report = await StudyService(ResearchOptions(rebuild_index=rebuild),
                    loader=loader, team=FakeTeam(), index=store).run('topic', papers=[paper()])
                self.assertTrue(report.analyses[0].citations)
                self.assertGreaterEqual(len(queries), 3)
            self.assertEqual(loader.calls, 2)

    async def test_live_default_uses_real_local_embedder_demo_remains_offline(self):
        from paper_agent.tools.local_embeddings import LocalMultilingualEmbedder
        live = ResearchService(ResearchOptions())._build_evidence()
        self.assertIsInstance(live.index, ChromaVectorIndex)
        self.assertIsInstance(live.index.embedder, LocalMultilingualEmbedder)
        demo = ResearchService(ResearchOptions(mode='demo'))._build_evidence()
        self.assertIsInstance(demo.index.embedder, HashingEmbedder)

    async def test_saved_study_evidence_is_frozen_across_same_url_rebuild(self):
        from paper_agent.services.study import StudyService
        from paper_agent.core.study import StudyReport
        with storage_directory() as directory:
            class Loader(FakeLoader):
                text = 'Original full paper method and experiments.'
                async def load(self, p):
                    chunks = await super().load(p)
                    chunks[0].text = self.text
                    return chunks
            loader = Loader()
            first = await StudyService(loader=loader, team=FakeTeam(), index=index(Path(directory))).run('topic', papers=[paper()])
            saved = first.model_dump_json()
            loader.text = 'Revised full paper with different experiment results.'
            second = await StudyService(ResearchOptions(rebuild_index=True), loader=loader,
                team=FakeTeam(), index=index(Path(directory))).run('topic', papers=[paper()])
            old = StudyReport.model_validate_json(saved)
            self.assertIn('Original', old.evidence_snapshots['p1'][0].text)
            self.assertIn('Revised', second.evidence_snapshots['p1'][0].text)


if __name__ == '__main__':
    unittest.main()
