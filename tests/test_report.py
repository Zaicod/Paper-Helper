from paper_agent.demo_team import DemoResearchTeam
from paper_agent.models import AnalysisFailure
from paper_agent.report import render_html, render_markdown, save_report
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


async def test_html_contains_main_sections() -> None:
    report = await ResearchWorkflow(
        FixtureSearchClient(),
        DemoResearchTeam(),
    ).run("RAG", limit=1)

    html = render_html(report)

    assert "<!doctype html>" in html
    assert "<h1>研究方向报告：RAG</h1>" in html
    assert "<h2>领域概览</h2>" in html
    assert "<h2>单篇论文分析</h2>" in html
    assert "<h2>候选研究想法</h2>" in html
    assert "demo-001" in html
    assert "覆盖不完整" not in html

async def test_html_warns_when_coverage_is_incomplete() -> None:
    report = await ResearchWorkflow(
        FixtureSearchClient(),
        DemoResearchTeam(),
    ).run("RAG", limit=1)

    report.analysis_failures.append(
        AnalysisFailure(
            paper_id="failed-001",
            error_type="TimeoutError",
            retry_count=2,
        )
    )

    html = render_html(report)

    assert "覆盖不完整" in html
    assert "failed-001" in html
    assert "TimeoutError" in html
    assert html.index("覆盖不完整") < html.index("领域概览")

async def test_html_escapes_dynamic_content() -> None:
    report = await ResearchWorkflow(
        FixtureSearchClient(),
        DemoResearchTeam(),
    ).run("<script>alert(1)</script>", limit=1)

    html = render_html(report)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


async def test_save_report_writes_all_three_presentations(tmp_path) -> None:
    report = await ResearchWorkflow(
        FixtureSearchClient(),
        DemoResearchTeam(),
    ).run("RAG", limit=1)

    markdown_path, json_path, html_path = save_report(report, tmp_path)

    assert markdown_path.exists()
    assert json_path.exists()
    assert html_path.exists()
