"""Offline behavioral coverage for the shared research workflow."""

import unittest

from paper_agent.agents.demo import DemoResearchTeam
from paper_agent.core.models import EvidenceDecision, Paper
from paper_agent.tools.rag import HashingEmbedder, PaperRAG
from paper_agent.workflows.research import ResearchWorkflow


def sample_papers(count=3):
    return [
        Paper(
            paper_id=f"paper-{index}", source="fixture", title=f"RAG study {index}",
            authors=["Researcher"], abstract="Research problem: retrieval. Method: evidence ranking. "
            "Experiment dataset and result: improved evidence grounding with limitations.",
            page_url=f"https://example.test/papers/{index}",
        )
        for index in range(count)
    ]


class FixtureSearch:
    def __init__(self, papers=None, failure=None):
        self.papers = sample_papers() if papers is None else papers
        self.failure = failure
        self.calls = []

    async def search(self, topic, limit, category=None):
        self.calls.append((topic, limit, category))
        if self.failure:
            raise self.failure
        return self.papers[:limit]


class UnboundedFixtureSearch(FixtureSearch):
    async def search(self, topic, limit, category=None):
        self.calls.append((topic, limit, category))
        return self.papers


SECRET_ERROR = "https://private.example/api?token=sk-fixture-secret user-input=private-prompt"


class SecretFailureTeam(DemoResearchTeam):
    async def analyze_paper(self, paper, context=None):
        if paper.paper_id == "paper-1":
            raise RuntimeError(SECRET_ERROR)
        return await super().analyze_paper(paper, context)


class SecretSynthesisTeam(DemoResearchTeam):
    def __init__(self):
        self.failure = ValueError(SECRET_ERROR)

    async def synthesize(self, topic, analyses):
        raise self.failure


class SelectiveFailureTeam(DemoResearchTeam):
    def __init__(self, failed_ids):
        self.failed_ids = failed_ids
        self.attempts = {}

    async def analyze_paper(self, paper, context=None):
        self.attempts[paper.paper_id] = self.attempts.get(paper.paper_id, 0) + 1
        if paper.paper_id in self.failed_ids:
            raise RuntimeError("fixture analysis unavailable")
        return await super().analyze_paper(paper, context)


class SynthesisFailureTeam(DemoResearchTeam):
    async def synthesize(self, topic, analyses):
        raise ValueError("fixture synthesis unavailable")


class IdeationFailureTeam(DemoResearchTeam):
    async def ideate(self, topic, synthesis):
        raise ValueError("fixture ideation unavailable")


class IndexFailureRAG(PaperRAG):
    async def index_papers(self, papers):
        raise OSError("fixture index unavailable")


class ContextFailureRAG(PaperRAG):
    async def build_analysis_context(self, paper):
        if paper.paper_id == "paper-1":
            raise OSError(SECRET_ERROR)
        return await super().build_analysis_context(paper)


class ApproveEvidence:
    async def decide(self, paper, context):
        return EvidenceDecision(action="analyze", confidence=0.9, source="fixture")


class SecretFailureDecider(ApproveEvidence):
    async def decide(self, paper, context):
        if paper.paper_id == "paper-1":
            raise ValueError(SECRET_ERROR)
        return await super().decide(paper, context)


class ResearchWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, workflow, **kwargs):
        events = []

        async def receive(event):
            events.append(event)

        result = await workflow.run("RAG", on_event=receive, **kwargs)
        return result, events

    async def test_supplied_papers_skip_search_and_are_all_used(self):
        search = FixtureSearch(failure=AssertionError("must not search"))
        papers = sample_papers(6)
        result, _ = await self.collect(ResearchWorkflow(search, DemoResearchTeam()), papers=papers)
        self.assertEqual(search.calls, [])
        self.assertEqual(result.papers, papers)
        self.assertEqual(len(result.analyses), 6)

    async def test_invalid_input_fails_before_search_or_events(self):
        papers = sample_papers()
        cases = [
            {"topic": " "}, {"topic": "RAG", "limit": 0},
            {"topic": "RAG", "limit": 21}, {"topic": "RAG", "papers": []},
            {"topic": "RAG", "papers": sample_papers(21)},
            {"topic": "RAG", "papers": [papers[0], papers[0]]},
            {"topic": "RAG", "papers": [papers[0], papers[0].model_copy(update={"source": "other"})]},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                search = FixtureSearch()
                events = []

                async def receive(event):
                    events.append(event)

                with self.assertRaises(ValueError):
                    await ResearchWorkflow(search, DemoResearchTeam()).run(on_event=receive, **kwargs)
                self.assertEqual(search.calls, [])
                self.assertEqual(events, [])

    async def test_search_preserves_old_arguments_and_stage_order(self):
        search = FixtureSearch()
        report, events = await self.collect(
            ResearchWorkflow(search, DemoResearchTeam()), limit=2, category="cs.AI"
        )
        self.assertEqual(search.calls, [("RAG", 2, "cs.AI")])
        self.assertEqual(len(report.analyses), 2)
        self.assertEqual(
            [(event.stage, event.status) for event in events],
            [(stage, status) for stage in ("search", "analyze", "synthesize", "ideate")
             for status in ("started", "completed")],
        )
        self.assertTrue(all(event.paper_id is None for event in events))
        self.assertTrue(all(event.timestamp.utcoffset().total_seconds() == 0 for event in events))
        self.assertTrue(all(event.message for event in events))

    async def test_no_callback_is_backward_compatible(self):
        report = await ResearchWorkflow(FixtureSearch(), DemoResearchTeam()).run("RAG", 2, "cs.AI")
        self.assertEqual(len(report.analyses), 2)

    async def test_empty_search_is_an_acquisition_failure(self):
        events = []

        async def receive(event):
            events.append(event)

        with self.assertRaisesRegex(RuntimeError, "search:.*no papers"):
            await ResearchWorkflow(FixtureSearch([]), DemoResearchTeam()).run("RAG", on_event=receive)
        self.assertEqual([(e.stage, e.status) for e in events], [("search", "started"), ("search", "failed")])

    async def test_search_error_preserves_original_cause(self):
        error = OSError("fixture source unavailable")
        events = []

        async def receive(event):
            events.append(event)

        with self.assertRaisesRegex(RuntimeError, "search: OSError") as caught:
            await ResearchWorkflow(FixtureSearch(failure=error), DemoResearchTeam()).run("RAG", on_event=receive)
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual((events[-1].stage, events[-1].status), ("search", "failed"))

    async def test_single_failed_paper_retains_two_successes_and_retries(self):
        team = SelectiveFailureTeam({"paper-1"})
        report, events = await self.collect(
            ResearchWorkflow(FixtureSearch(), team, max_retries=1, retry_base_delay=0)
        )
        self.assertEqual(len(report.analyses), 2)
        self.assertEqual(len(report.analysis_failures), 1)
        self.assertEqual(report.analysis_failures[0].paper_id, "paper-1")
        self.assertEqual(report.analysis_failures[0].retry_count, 1)
        self.assertEqual(team.attempts["paper-1"], 2)
        self.assertIn(("analyze", "completed"), [(e.stage, e.status) for e in events])

    async def test_all_failed_papers_emit_failed_analysis_without_synthesis(self):
        events = []

        async def receive(event):
            events.append(event)

        workflow = ResearchWorkflow(FixtureSearch(), SelectiveFailureTeam({f"paper-{i}" for i in range(3)}), max_retries=0)
        with self.assertRaisesRegex(RuntimeError, "analyze:.*all paper analyses failed"):
            await workflow.run("RAG", on_event=receive)
        self.assertEqual((events[-1].stage, events[-1].status), ("analyze", "failed"))
        self.assertFalse(any(e.stage == "synthesize" for e in events))

    async def test_synthesis_failure_emits_failed_event_and_stops(self):
        events = []

        async def receive(event):
            events.append(event)

        with self.assertRaisesRegex(RuntimeError, "synthesize: ValueError"):
            await ResearchWorkflow(FixtureSearch(), SynthesisFailureTeam()).run("RAG", on_event=receive)
        self.assertEqual((events[-1].stage, events[-1].status), ("synthesize", "failed"))
        self.assertFalse(any(e.stage == "ideate" for e in events))

    async def test_rag_stage_retains_three_audits_and_evidence_citations(self):
        report, events = await self.collect(
            ResearchWorkflow(FixtureSearch(), DemoResearchTeam(), evidence=PaperRAG(HashingEmbedder()))
        )
        self.assertEqual(len(report.context_audits), 3)
        self.assertTrue(all(audit.selected_chunk_ids for audit in report.context_audits))
        self.assertTrue(all(analysis.citations for analysis in report.analyses))
        self.assertEqual(
            [(event.stage, event.status) for event in events],
            [(stage, status) for stage in ("search", "index", "analyze", "synthesize", "ideate")
             for status in ("started", "completed")],
        )

    async def test_index_failure_has_its_own_failed_stage(self):
        events = []

        async def receive(event):
            events.append(event)

        workflow = ResearchWorkflow(
            FixtureSearch(), DemoResearchTeam(), evidence=IndexFailureRAG(HashingEmbedder())
        )
        with self.assertRaisesRegex(RuntimeError, "index: OSError"):
            await workflow.run("RAG", on_event=receive)
        self.assertEqual((events[-1].stage, events[-1].status), ("index", "failed"))
        self.assertFalse(any(e.stage == "analyze" for e in events))

    async def test_ideation_failure_has_its_own_failed_stage(self):
        events = []

        async def receive(event):
            events.append(event)

        with self.assertRaisesRegex(RuntimeError, "ideate: ValueError"):
            await ResearchWorkflow(FixtureSearch(), IdeationFailureTeam()).run("RAG", on_event=receive)
        self.assertEqual((events[-1].stage, events[-1].status), ("ideate", "failed"))

    async def test_context_failure_is_isolated_and_recorded_as_retrieval(self):
        report = await ResearchWorkflow(
            FixtureSearch(), DemoResearchTeam(), evidence=ContextFailureRAG(HashingEmbedder())
        ).run("RAG")
        self.assertEqual(len(report.analyses), 2)
        self.assertEqual(len(report.context_audits), 2)
        self.assertEqual(len(report.analysis_failures), 1)
        failure = report.analysis_failures[0]
        self.assertEqual((failure.paper_id, failure.stage, failure.retry_count), ("paper-1", "retrieval", 0))
        self.assertEqual(failure.message, "OSError")
        self.assertNotIn("sk-fixture-secret", report.model_dump_json())

    async def test_evidence_gate_decisions_remain_in_three_audits(self):
        report = await ResearchWorkflow(
            FixtureSearch(), DemoResearchTeam(), evidence=PaperRAG(HashingEmbedder()),
            decider=ApproveEvidence(),
        ).run("RAG")
        self.assertEqual(len(report.analyses), 3)
        self.assertEqual(len(report.context_audits), 3)
        self.assertTrue(all(len(audit.decisions) == 1 for audit in report.context_audits))
        self.assertTrue(all(audit.decisions[0].action == "analyze" for audit in report.context_audits))

    async def test_malformed_search_results_fail_before_index_or_model(self):
        papers = sample_papers()
        cases = [sample_papers(21), [papers[0], papers[0]],
                 [papers[0], papers[0].model_copy(update={"source": "other"})]]
        for records in cases:
            with self.subTest(count=len(records)):
                events = []

                async def receive(event):
                    events.append(event)

                team = SelectiveFailureTeam(set())
                workflow = ResearchWorkflow(
                    UnboundedFixtureSearch(records), team,
                    evidence=IndexFailureRAG(HashingEmbedder()),
                )
                with self.assertRaisesRegex(RuntimeError, "search:"):
                    await workflow.run("RAG", on_event=receive)
                self.assertEqual(team.attempts, {})
                self.assertEqual([(e.stage, e.status) for e in events],
                                 [("search", "started"), ("search", "failed")])

    async def test_search_secret_is_only_preserved_in_private_cause(self):
        events = []

        async def receive(event):
            events.append(event)

        error = OSError(SECRET_ERROR)
        with self.assertRaisesRegex(RuntimeError, "search: OSError") as caught:
            await ResearchWorkflow(FixtureSearch(failure=error), DemoResearchTeam()).run("RAG", on_event=receive)
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(str(error), SECRET_ERROR)
        self.assertEqual(events[-1].message, str(caught.exception))
        public_text = str(caught.exception) + " ".join(event.model_dump_json() for event in events)
        for private in ("sk-fixture-secret", "private.example", "private-prompt"):
            self.assertNotIn(private, public_text)

    async def test_synthesis_secret_is_only_preserved_in_private_cause(self):
        events = []

        async def receive(event):
            events.append(event)

        team = SecretSynthesisTeam()
        with self.assertRaisesRegex(RuntimeError, "synthesize: ValueError") as caught:
            await ResearchWorkflow(FixtureSearch(), team).run("RAG", on_event=receive)
        self.assertIs(caught.exception.__cause__, team.failure)
        self.assertEqual(events[-1].message, str(caught.exception))
        public_text = str(caught.exception) + " ".join(event.model_dump_json() for event in events)
        for private in ("sk-fixture-secret", "private.example", "private-prompt"):
            self.assertNotIn(private, public_text)

    async def test_partial_model_failure_has_safe_report_message(self):
        report, events = await self.collect(
            ResearchWorkflow(FixtureSearch(), SecretFailureTeam(), max_retries=0)
        )
        self.assertEqual(len(report.analyses), 2)
        self.assertEqual(report.analysis_failures[0].message, "RuntimeError")
        public_text = report.model_dump_json() + " ".join(event.model_dump_json() for event in events)
        for private in ("sk-fixture-secret", "private.example", "private-prompt"):
            self.assertNotIn(private, public_text)

    async def test_decision_failure_has_safe_report_message(self):
        report = await ResearchWorkflow(
            FixtureSearch(), DemoResearchTeam(), evidence=PaperRAG(HashingEmbedder()),
            decider=SecretFailureDecider(),
        ).run("RAG")
        self.assertEqual(len(report.analyses), 2)
        failure = report.analysis_failures[0]
        self.assertEqual((failure.stage, failure.message), ("decision", "ValueError"))
        self.assertNotIn("sk-fixture-secret", report.model_dump_json())

    async def test_public_error_helper_preserves_only_explicit_safe_errors(self):
        from paper_agent.core.errors import PublicResearchError, public_error_message

        self.assertEqual(public_error_message(ValueError(SECRET_ERROR)), "ValueError")
        self.assertEqual(public_error_message(PublicResearchError("controlled failure")), "controlled failure")


if __name__ == "__main__":
    unittest.main()
