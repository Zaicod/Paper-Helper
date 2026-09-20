from paper_agent.demo_team import DemoResearchTeam
from paper_agent.report import render_markdown
from paper_agent.search import FixtureSearchClient
from paper_agent.workflow import ResearchWorkflow


async def test_markdown_contains_main_sections() -> None:
    report = await ResearchWorkflow(
        FixtureSearchClient(), DemoResearchTeam()
    ).run("RAG", limit=1)

    markdown = render_markdown(report)

    assert "# 研究方向报告：RAG" in markdown
    assert "## 单篇论文分析" in markdown
    assert "## 候选研究想法" in markdown
    assert "demo-001" in markdown

