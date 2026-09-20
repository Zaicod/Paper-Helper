from paper_agent.demo_team import DemoResearchTeam
from paper_agent.models import AnalysisFailure
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
    assert "覆盖不完整" not in markdown


async def test_markdown_warns_when_analysis_coverage_is_incomplete() -> None:
    report = await ResearchWorkflow(
        FixtureSearchClient(), DemoResearchTeam()
    ).run("RAG", limit=2)
    report.analysis_failures.append(
        AnalysisFailure(
            paper_id="failed-001",
            error_type="TimeoutError",
            retry_count=2,
        )
    )

    markdown = render_markdown(report)

    assert "> [!WARNING]" in markdown
    assert "覆盖不完整" in markdown
    assert "失败 1 篇" in markdown
    assert "failed-001" in markdown
    assert "TimeoutError" in markdown
    assert "重试 2 次" in markdown
    assert markdown.index("覆盖不完整") < markdown.index("## 领域概览")
    assert "## 单篇论文分析" in markdown
    assert "## 候选研究想法" in markdown
