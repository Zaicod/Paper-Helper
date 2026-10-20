import importlib
import importlib.util
import os
import unittest
from unittest.mock import patch

from paper_agent.agents.demo import DemoResearchTeam
from paper_agent.tools.search import FixtureSearchClient


class ResearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def service_module(self):
        self.assertIsNotNone(
            importlib.util.find_spec('paper_agent.services.research'),
            'Both entry points need the shared research application service',
        )
        return importlib.import_module('paper_agent.services.research')

    async def test_demo_default_builds_auditable_abstract_context(self):
        module = self.service_module()
        service = module.ResearchService(module.ResearchOptions(mode='demo'))
        events = []

        async def collect(event):
            events.append((event.stage, event.status))

        report = await service.run('RAG', limit=3, on_event=collect)
        self.assertEqual(len(report.analyses), 3)
        self.assertEqual(len(report.context_audits), 3)
        self.assertTrue(all(audit.evidence_chunks for audit in report.context_audits))
        self.assertIn(('index', 'completed'), events)
        self.assertTrue(all(analysis.citations for analysis in report.analyses))

    async def test_live_missing_credentials_never_falls_back_to_demo(self):
        module = self.service_module()
        with patch.dict(os.environ, {}, clear=True):
            service = module.ResearchService(module.ResearchOptions(mode='live'))
            with self.assertRaisesRegex(module.ResearchConfigurationError, 'DASHSCOPE_API_KEY'):
                await service.run('RAG', limit=3)

    async def test_live_rejects_fixture_decision_gate(self):
        module = self.service_module()
        with self.assertRaisesRegex(ValueError, 'fixture'):
            module.ResearchOptions(mode='live', decision='fixture')

    async def test_decision_requires_rag(self):
        module = self.service_module()
        with self.assertRaisesRegex(ValueError, 'RAG'):
            module.ResearchOptions(mode='demo', rag='none', decision='fixture')

    async def test_trusted_papers_are_shared_between_entry_points(self):
        module = self.service_module()
        papers = await FixtureSearchClient().search('RAG', 3)

        class NeverSearch:
            async def search(self, *args):
                raise AssertionError('Trusted papers must bypass the search provider')

        report = await module.ResearchService(
            module.ResearchOptions(mode='demo', decision='fixture'),
            search=NeverSearch(), team=DemoResearchTeam(),
        ).run('RAG', papers=papers)
        self.assertEqual([p.paper_id for p in report.papers], [p.paper_id for p in papers])
        self.assertTrue(all(a.decisions for a in report.context_audits))

    async def test_reusing_service_does_not_reuse_previous_evidence_index(self):
        module = self.service_module()
        papers = await FixtureSearchClient().search('RAG', 3)
        contexts = []

        class CaptureTeam(DemoResearchTeam):
            async def analyze_paper(self, paper, context=None):
                contexts.append([chunk.text for chunk in context.chunks])
                return await super().analyze_paper(paper, context)

        service = module.ResearchService(module.ResearchOptions(mode='demo'), team=CaptureTeam())
        first = await service.run('RAG', papers=[papers[0]])
        changed = papers[0].model_copy(update={'abstract': 'Replacement abstract only.'})
        second = await service.run('RAG', papers=[changed])
        self.assertEqual(len(first.context_audits), 1)
        self.assertEqual(len(second.context_audits), 1)
        self.assertEqual(second.papers[0].abstract, changed.abstract)
        self.assertEqual(contexts[1], ['Replacement abstract only.'])


if __name__ == '__main__':
    unittest.main()
