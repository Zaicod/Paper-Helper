from paper_agent.demo_team import DemoResearchTeam
from paper_agent.search import FixtureSearchClient
from paper_agent.workflow import ResearchWorkflow
import pytest


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
