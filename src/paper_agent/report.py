from __future__ import annotations

from html import escape
from pathlib import Path

from paper_agent.models import ResearchReport

def render_markdown(report: ResearchReport) -> str:



    lines = [
        f"# 研究方向报告：{report.topic}",
        "",
        f"> 生成时间：{report.generated_at.isoformat()}",
        f"> 证据边界：{_evidence_boundary(report)}",
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

    if report.analysis_failures:
        lines[5:5] = [
            "> [!WARNING]",
            (
                f"> ⚠️ **覆盖不完整**：检索到 {len(report.papers)} 篇论文，"
                f"成功分析 {len(report.analyses)} 篇，"
                f"失败 {len(report.analysis_failures)} 篇。"
            ),
            "> 当前总结和研究想法仅基于成功分析的论文。",
            "",
            "> 失败明细：",
            *[
                (
                    f"> - `{failure.paper_id}`："
                    f"{failure.error_type}，"
                    f"重试 {failure.retry_count} 次"
                )
                for failure in report.analysis_failures
            ],
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
                "**数据集与引用**",
                "",
                *_bullets(analysis.datasets),
                *_bullets([f"证据块 `{item}`" for item in analysis.citations]),
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

    if report.context_audits:
        lines.extend(["## 上下文工程审计", ""])
        for audit in report.context_audits:
            lines.extend(
                [
                    f"- `{audit.paper_id}`：来源={audit.source_mode}，"
                    f"选中={len(audit.selected_chunk_ids)}，丢弃={audit.dropped_count}，"
                    f"估算 token={audit.estimated_tokens}/{audit.token_budget}",
                ]
            )
        lines.append("")

    return "\n".join(lines)

def render_html(report: ResearchReport) -> str:
    def text(value: object) -> str:
        return escape(str(value))

    def unordered_list(items: list[str]) -> str:
        if not items:
            return "<ul><li>暂无</li></ul>"
        content = "".join(f"<li>{text(item)}</li>" for item in items)
        return f"<ul>{content}</ul>"

    def ordered_list(items: list[str]) -> str:
        if not items:
            return "<ol><li>暂无</li></ol>"
        content = "".join(f"<li>{text(item)}</li>" for item in items)
        return f"<ol>{content}</ol>"

    warning_html = ""
    if report.analysis_failures:
        failure_items = "".join(
            (
                f"<li><code>{text(failure.paper_id)}</code>："
                f"{text(failure.error_type)}，"
                f"重试 {failure.retry_count} 次</li>"
            )
            for failure in report.analysis_failures
        )

        warning_html = f"""
        <section class="warning">
            <h2>⚠️ 覆盖不完整</h2>
            <p>
                检索到 {len(report.papers)} 篇论文，
                成功分析 {len(report.analyses)} 篇，
                失败 {len(report.analysis_failures)} 篇。
            </p>
            <p>当前总结和研究想法仅基于成功分析的论文。</p>
            <ul>{failure_items}</ul>
        </section>
        """

    paper_by_id = {
        paper.paper_id: paper
        for paper in report.papers
    }

    analysis_html = ""
    for analysis in report.analyses:
        paper = paper_by_id[analysis.paper_id]

        analysis_html += f"""
        <article class="paper">
            <h3>{text(analysis.title)}</h3>
            <p><strong>论文 ID：</strong>
                <code>{text(analysis.paper_id)}</code>
            </p>
            <p><strong>文献源：</strong>{text(paper.source)}</p>
            <p><strong>作者：</strong>{text(", ".join(paper.authors))}</p>
            <p>
                <strong>链接：</strong>
                <a href="{text(paper.page_url)}">{text(paper.page_url)}</a>
            </p>
            <p><strong>研究问题：</strong>{text(analysis.research_problem)}</p>

            <h4>数据集</h4>
            {unordered_list(analysis.datasets)}

            <h4>创新点</h4>
            {unordered_list(analysis.innovation_points)}

            <h4>方法</h4>
            {unordered_list(analysis.methods)}

            <h4>结果</h4>
            {unordered_list(analysis.results)}

            <h4>证据引用</h4>
            {unordered_list(analysis.citations)}

            <h4>局限与证据说明</h4>
            {unordered_list(analysis.limitations + analysis.evidence_notes)}
        </article>
        """

    ideas_html = ""
    for index, idea in enumerate(report.idea_portfolio.ideas, start=1):
        ideas_html += f"""
        <article class="idea">
            <h3>{index}. {text(idea.title)}</h3>
            <p><strong>对应空白：</strong>{text(idea.target_gap)}</p>
            <p><strong>假设：</strong>{text(idea.hypothesis)}</p>
            <p><strong>预期贡献：</strong>{text(idea.expected_contribution)}</p>
            <p>
                <strong>关联论文：</strong>
                {text(", ".join(idea.related_paper_ids))}
            </p>

            <h4>方法步骤</h4>
            {ordered_list(idea.proposed_method)}

            <h4>评测方案</h4>
            {unordered_list(idea.evaluation_plan)}

            <h4>风险</h4>
            {unordered_list(idea.risks)}
        </article>
        """

    context_html = ""
    if report.context_audits:
        context_html = "<section><h2>上下文工程审计</h2><ul>" + "".join(
            (
                f"<li><code>{text(audit.paper_id)}</code>："
                f"来源={text(audit.source_mode)}，"
                f"选中={len(audit.selected_chunk_ids)}，"
                f"丢弃={audit.dropped_count}，"
                f"估算 token={audit.estimated_tokens}/{audit.token_budget}</li>"
            )
            for audit in report.context_audits
        ) + "</ul></section>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <title>研究方向报告：{text(report.topic)}</title>
    <style>
        body {{
            max-width: 900px;
            margin: 40px auto;
            padding: 0 24px;
            font-family: sans-serif;
            line-height: 1.7;
        }}

        .warning {{
            margin: 24px 0;
            padding: 16px;
            border: 2px solid #d97706;
            background: #fff7ed;
        }}

        .paper, .idea {{
            margin: 24px 0;
            padding: 16px;
            border: 1px solid #ddd;
            border-radius: 8px;
        }}
    </style>
</head>
<body>
    <h1>研究方向报告：{text(report.topic)}</h1>

    <p>生成时间：{text(report.generated_at.isoformat())}</p>
    <p>证据边界：{text(_evidence_boundary(report))}</p>

    {warning_html}

    <section>
        <h2>领域概览</h2>
        <p>{text(report.synthesis.overview)}</p>

        <h3>方法分类</h3>
        {unordered_list(report.synthesis.method_taxonomy)}

        <h3>共同发现</h3>
        {unordered_list(report.synthesis.common_findings)}

        <h3>分歧与信息不足</h3>
        {unordered_list(report.synthesis.disagreements)}

        <h3>研究空白</h3>
        {unordered_list(report.synthesis.research_gaps)}

        <h3>证据映射</h3>
        {unordered_list(report.synthesis.evidence_map)}
    </section>

    <section>
        <h2>单篇论文分析</h2>
        {analysis_html}
    </section>

    <section>
        <h2>候选研究想法</h2>
        {ideas_html}
        <p><strong>注意：</strong>{text(report.idea_portfolio.caution)}</p>
    </section>

    {context_html}
</body>
</html>
"""


def save_report(report: ResearchReport, output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = "_".join(report.topic.lower().split())[:50] or "research"
    timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
    markdown_path = output_dir / f"{timestamp}_{slug}.md"
    json_path = output_dir / f"{timestamp}_{slug}.json"
    html_path = output_dir / f"{timestamp}_{slug}.html"
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return markdown_path, json_path, html_path


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- 暂无"]


def _numbered(items: list[str]) -> list[str]:
    return [f"{index}. {item}" for index, item in enumerate(items, start=1)]


def _evidence_boundary(report: ResearchReport) -> str:
    modes = {audit.source_mode for audit in report.context_audits}
    if "pdf" in modes:
        return "至少部分论文基于 PDF 正文检索片段；结论应通过 chunk 引用回查原文。"
    if modes:
        return "已通过 RAG 选择摘要证据，但尚未核对 PDF 全文。"
    return "当前仅分析论文标题与摘要，不代表已核对全文。"
