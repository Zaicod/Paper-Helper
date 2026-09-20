from __future__ import annotations

from paper_agent.models import (
    ContextPacket,
    FieldSynthesis,
    IdeaPortfolio,
    Paper,
    PaperAnalysis,
    ResearchIdea,
)


class DemoResearchTeam:
    """A zero-cost stand-in. Outputs are intentionally marked as demonstrations."""

    async def analyze_paper(
        self, paper: Paper, context: ContextPacket | None = None
    ) -> PaperAnalysis:
        return PaperAnalysis(
            paper_id=paper.paper_id,
            title=paper.title,
            research_problem=f"演示分析：{paper.title} 所描述的问题。",
            innovation_points=["演示字段：从摘要提取的候选创新点。"],
            methods=[f"演示字段：主题类别为 {', '.join(paper.categories)}。"],
            results=["演示字段：真实结果需要由 live 模式中的模型严格提取。"],
            limitations=["当前只提供摘要，无法验证完整实验细节。"],
            evidence_notes=[f"来源记录：{paper.paper_id}；此输出用于跑通工作流。"],
            datasets=["数据集"],
            citations=(
                [chunk.chunk_id for chunk in context.chunks]
                if context is not None
                else []
            ),
        )

    async def synthesize(
        self, topic: str, analyses: list[PaperAnalysis]
    ) -> FieldSynthesis:
        paper_ids = [analysis.paper_id for analysis in analyses]
        return FieldSynthesis(
            topic=topic,
            overview=f"演示总结：共处理 {len(analyses)} 篇示例论文。",
            method_taxonomy=["检索增强", "自适应检索", "证据一致性检查"],
            common_findings=["示例记录都关注外部证据如何改善生成。"],
            disagreements=["演示数据不足以判断论文间的真实分歧。"],
            research_gaps=["检索成本、证据质量与回答可靠性之间仍需联合优化。"],
            evidence_map=[f"演示结论来源：{', '.join(paper_ids)}"],
        )

    async def ideate(
        self, topic: str, synthesis: FieldSynthesis
    ) -> IdeaPortfolio:
        evidence_ids = synthesis.evidence_map[0].replace("：", ":")
        ids = [part.strip() for part in evidence_ids.split(":", 1)[-1].split(",")]
        return IdeaPortfolio(
            topic=topic,
            ideas=[
                ResearchIdea(
                    title="基于不确定性的自适应检索与证据复核",
                    target_gap=synthesis.research_gaps[0],
                    hypothesis="只在模型不确定或证据冲突时增加检索，可改善成本—可靠性折中。",
                    proposed_method=[
                        "训练或校准回答不确定性估计器。",
                        "按不确定性动态选择检索深度。",
                        "对高风险回答执行独立证据一致性检查。",
                    ],
                    expected_contribution="形成可测量的动态计算预算分配方法。",
                    evaluation_plan=[
                        "比较固定检索、自适应检索和不检索基线。",
                        "同时报告正确率、引用忠实度、延迟和检索次数。",
                    ],
                    risks=["不确定性可能校准不准。", "额外检查会增加尾延迟。"],
                    related_paper_ids=ids,
                )
            ],
            caution="这是离线演示想法，未经过全面新颖性检索或实验验证。",
        )
