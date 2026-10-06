from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from paper_agent.demo_team import DemoResearchTeam
from paper_agent.models import (
    FieldSynthesis,
    IdeaPortfolio,
    Paper,
    PaperAnalysis,
    ResearchReport,
)
from paper_agent.protocols import PaperSearch, ResearchTeam
from paper_agent.report import render_markdown
from paper_agent.search import FixtureSearchClient


class ResearchGraphState(TypedDict, total=False):
    """Raw data shared by the nodes in the phase-one graph.

    ``total=False`` means later-node fields may be absent at the beginning of a
    run. Each node returns only the fields it produces instead of copying the
    complete state.
    """

    topic: str
    limit: int
    category: str | None
    papers: list[Paper]
    analyses: list[PaperAnalysis]
    synthesis: FieldSynthesis
    idea_portfolio: IdeaPortfolio
    report: ResearchReport
    rendered_markdown: str


def build_fixture_research_graph(
    search: PaperSearch | None = None,
    team: ResearchTeam | None = None,
):
    """Build the minimal offline graph used in the first learning phase.

    The injected defaults never access the network or a model API. Dependency
    injection also keeps every node independently testable.
    """

    search_client = search or FixtureSearchClient()
    research_team = team or DemoResearchTeam()

    async def search_papers(state: ResearchGraphState) -> dict[str, object]:
        topic = state["topic"]
        limit = state["limit"]
        category = state.get("category")

        if not topic.strip():
            raise ValueError("topic cannot be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        # A collection-backed task injects trusted papers into the state.  The
        # graph stays reusable: only the acquisition source changes, while the
        # analysis, synthesis and rendering nodes remain identical.
        papers = state.get("papers")
        if papers is None:
            papers = await search_client.search(topic, limit, category)
        if not papers:
            raise RuntimeError("research task contains no papers")
        return {"papers": papers}

    async def analyze_papers(state: ResearchGraphState) -> dict[str, object]:
        # Phase one is intentionally sequential. Phase two will replace this
        # loop with LangGraph Send fan-out and a reducer.
        analyses = [
            await research_team.analyze_paper(paper)
            for paper in state["papers"]
        ]
        return {"analyses": analyses}

    async def synthesize_field(state: ResearchGraphState) -> dict[str, object]:
        synthesis = await research_team.synthesize(
            state["topic"], state["analyses"]
        )
        return {"synthesis": synthesis}

    async def ideate(state: ResearchGraphState) -> dict[str, object]:
        portfolio = await research_team.ideate(
            state["topic"], state["synthesis"]
        )
        return {"idea_portfolio": portfolio}

    def render_report(state: ResearchGraphState) -> dict[str, object]:
        report = ResearchReport(
            topic=state["topic"],
            generated_at=datetime.now(timezone.utc),
            papers=state["papers"],
            analyses=state["analyses"],
            synthesis=state["synthesis"],
            idea_portfolio=state["idea_portfolio"],
        )
        return {
            "report": report,
            "rendered_markdown": render_markdown(report),
        }

    builder = StateGraph(ResearchGraphState)
    builder.add_node("search", search_papers)
    builder.add_node("analyze", analyze_papers)
    builder.add_node("synthesize", synthesize_field)
    builder.add_node("ideate", ideate)
    builder.add_node("render", render_report)

    builder.add_edge(START, "search")
    builder.add_edge("search", "analyze")
    builder.add_edge("analyze", "synthesize")
    builder.add_edge("synthesize", "ideate")
    builder.add_edge("ideate", "render")
    builder.add_edge("render", END)
    return builder.compile()


async def run_fixture_research_graph(
    topic: str,
    limit: int = 3,
    category: str | None = None,
) -> ResearchGraphState:
    """Convenience entry point used by the CLI and beginner exercises."""

    graph = build_fixture_research_graph()
    return await graph.ainvoke(
        {"topic": topic, "limit": limit, "category": category}
    )
