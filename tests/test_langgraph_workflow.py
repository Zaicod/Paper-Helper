import pytest

from paper_agent.langgraph_workflow import (
    build_fixture_research_graph,
    run_fixture_research_graph,
)


async def test_fixture_graph_runs_the_minimal_pipeline() -> None:
    state = await run_fixture_research_graph("RAG", limit=2)

    assert [paper.paper_id for paper in state["papers"]] == [
        "demo-001",
        "demo-002",
    ]
    assert [analysis.paper_id for analysis in state["analyses"]] == [
        "demo-001",
        "demo-002",
    ]
    assert state["synthesis"].topic == "RAG"
    assert len(state["report"].idea_portfolio.ideas) == 1
    assert "# 研究方向报告：RAG" in state["rendered_markdown"]


async def test_fixture_graph_applies_category_filter() -> None:
    state = await run_fixture_research_graph("RAG", limit=3, category="cs.AI")

    assert [paper.paper_id for paper in state["papers"]] == ["demo-001"]


@pytest.mark.parametrize("limit", [0, 21])
async def test_fixture_graph_rejects_invalid_limit(limit: int) -> None:
    graph = build_fixture_research_graph()

    with pytest.raises(ValueError, match="between 1 and 20"):
        await graph.ainvoke({"topic": "RAG", "limit": limit, "category": None})


def test_fixture_graph_has_explicit_learning_nodes() -> None:
    graph = build_fixture_research_graph().get_graph()

    assert set(graph.nodes) == {
        "__start__",
        "search",
        "analyze",
        "synthesize",
        "ideate",
        "render",
        "__end__",
    }
    assert {(edge.source, edge.target) for edge in graph.edges} == {
        ("__start__", "search"),
        ("search", "analyze"),
        ("analyze", "synthesize"),
        ("synthesize", "ideate"),
        ("ideate", "render"),
        ("render", "__end__"),
    }
