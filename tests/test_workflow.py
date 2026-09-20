from paper_agent.demo_team import DemoResearchTeam
from paper_agent.models import Paper
from paper_agent.search import FixtureSearchClient
from paper_agent.workflow import ResearchWorkflow
from paper_agent.rag import HashingEmbedder, PaperRAG
import pytest


class FivePaperSearch:
    async def search(self, topic, limit, category=None):
        papers = [
            Paper(
                paper_id=f"test-{index}",
                source="test",
                title=f"Test paper {index}",
                authors=["Test Author"],
                abstract="A stable abstract used for workflow testing.",
                page_url=f"https://example.com/test-{index}",
            )
            for index in range(1, 6)
        ]
        return papers[:limit]


class OnePaperFailsTeam(DemoResearchTeam):
    def __init__(self) -> None:
        self.attempts: dict[str, int] = {}

    async def analyze_paper(self, paper):
        self.attempts[paper.paper_id] = self.attempts.get(paper.paper_id, 0) + 1
        if paper.paper_id == "test-3":
            raise TimeoutError("simulated analysis timeout")
        return await super().analyze_paper(paper)


class AllPapersFailTeam(DemoResearchTeam):
    async def analyze_paper(self, paper):
        raise TimeoutError("simulated analysis timeout")


async def test_demo_workflow_produces_traceable_report() -> None:
    workflow = ResearchWorkflow(FixtureSearchClient(), DemoResearchTeam())

    report = await workflow.run("RAG", limit=2)

    assert report.topic == "RAG"
    assert len(report.papers) == 2
    assert [item.paper_id for item in report.analyses] == [
        "demo-001",
        "demo-002",
    ]
    assert report.synthesis.research_gaps
    assert report.idea_portfolio.ideas[0].related_paper_ids


@pytest.mark.parametrize("limit", [0, 21])
async def test_workflow_rejects_invalid_limit(limit: int) -> None:
    workflow = ResearchWorkflow(FixtureSearchClient(), DemoResearchTeam())

    with pytest.raises(ValueError, match="between 1 and 20"):
        await workflow.run("RAG", limit=limit)


async def test_workflow_continues_when_one_of_five_analyses_fails() -> None:
    team = OnePaperFailsTeam()
    workflow = ResearchWorkflow(
        FivePaperSearch(),
        team,
        max_retries=2,
        retry_base_delay=0,
    )

    report = await workflow.run("RAG", limit=5)

    assert len(report.papers) == 5
    assert len(report.analyses) == 4
    assert [item.paper_id for item in report.analyses] == [
        "test-1",
        "test-2",
        "test-4",
        "test-5",
    ]
    assert len(report.analysis_failures) == 1
    failure = report.analysis_failures[0]
    assert failure.paper_id == "test-3"
    assert failure.error_type == "TimeoutError"
    assert failure.retry_count == 2
    assert team.attempts["test-3"] == 3
    assert report.synthesis.topic == "RAG"


async def test_workflow_stops_when_all_analyses_fail() -> None:
    workflow = ResearchWorkflow(
        FivePaperSearch(),
        AllPapersFailTeam(),
        max_retries=0,
        retry_base_delay=0,
    )

    with pytest.raises(RuntimeError, match="all paper analyses failed"):
        await workflow.run("RAG", limit=5)


async def test_workflow_records_rag_context_audit() -> None:
    evidence = PaperRAG(HashingEmbedder())
    workflow = ResearchWorkflow(
        FixtureSearchClient(),
        DemoResearchTeam(),
        evidence=evidence,
    )

    report = await workflow.run("RAG", limit=1)

    assert len(report.context_audits) == 1
    assert report.context_audits[0].paper_id == "demo-001"
    assert report.context_audits[0].source_mode == "abstract"
    assert report.analyses[0].citations
