from __future__ import annotations

from pathlib import Path

from paper_agent.models import ResearchReport


def render_markdown(report: ResearchReport) -> str:
    lines = [
        f"# 研究方向报告：{report.topic}",
        "",
        f"> 生成时间：{report.generated_at.isoformat()}",
        "> 证据边界：当前版本仅分析论文标题与摘要，不代表已核对全文。",
        "",
        "## 领域概览",
        "",
        report.synthesis.overview,
        "",
        "### 方法分类",
        "",
        *_bullets(report.synthesis.method_taxonomy),
        "",
        "### 共同发现",
        "",
        *_bullets(report.synthesis.common_findings),
        "",
        "### 分歧与信息不足",
        "",
        *_bullets(report.synthesis.disagreements),
        "",
        "### 研究空白",
        "",
        *_bullets(report.synthesis.research_gaps),
        "",
        "### 证据映射",
        "",
        *_bullets(report.synthesis.evidence_map),
        "",
        "## 单篇论文分析",
        "",
    ]

    paper_by_id = {paper.paper_id: paper for paper in report.papers}
    for analysis in report.analyses:
        paper = paper_by_id[analysis.paper_id]
        lines.extend(
            [
                f"### {analysis.title}",
                "",
                f"- 论文 ID：`{analysis.paper_id}`",
                f"- 文献源：{paper.source}",
                f"- 作者：{', '.join(paper.authors)}",
                f"- 链接：{paper.page_url}",
                f"- 研究问题：{analysis.research_problem}",
                f"- 数据集: {analysis.datasets}",
                "",
                "**创新点**",
                "",
                *_bullets(analysis.innovation_points),
                "",
                "**方法**",
                "",
                *_bullets(analysis.methods),
                "",
                "**结果**",
                "",
                *_bullets(analysis.results),
                "",
                "**局限与证据说明**",
                "",
                *_bullets(analysis.limitations + analysis.evidence_notes),
                "",
            ]
        )

    lines.extend(["## 候选研究想法", ""])
    for index, idea in enumerate(report.idea_portfolio.ideas, start=1):
        lines.extend(
            [
                f"### {index}. {idea.title}",
                "",
                f"- 对应空白：{idea.target_gap}",
                f"- 假设：{idea.hypothesis}",
                f"- 预期贡献：{idea.expected_contribution}",
                f"- 关联论文：{', '.join(idea.related_paper_ids)}",
                "",
                "**方法步骤**",
                "",
                *_numbered(idea.proposed_method),
                "",
                "**评测方案**",
                "",
                *_bullets(idea.evaluation_plan),
                "",
                "**风险**",
                "",
                *_bullets(idea.risks),
                "",
            ]
        )

    lines.extend([f"> 注意：{report.idea_portfolio.caution}", ""])
    return "\n".join(lines)


def save_report(report: ResearchReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = "_".join(report.topic.lower().split())[:50] or "research"
    timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
    markdown_path = output_dir / f"{timestamp}_{slug}.md"
    json_path = output_dir / f"{timestamp}_{slug}.json"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return markdown_path, json_path


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- 暂无"]


def _numbered(items: list[str]) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)]
