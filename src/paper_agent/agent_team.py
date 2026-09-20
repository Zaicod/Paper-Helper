from __future__ import annotations

import json

from agents import Agent, Model, ModelSettings, Runner

from paper_agent.models import (
    ContextPacket,
    FieldSynthesis,
    IdeaPortfolio,
    Paper,
    PaperAnalysis,
)
from paper_agent.context import render_context
from paper_agent.prompts import (
    ANALYST_INSTRUCTIONS,
    IDEATOR_INSTRUCTIONS,
    SYNTHESIZER_INSTRUCTIONS,
)


class AgentResearchTeam:
    """Three specialist agents using any Agents SDK compatible model backend."""

    def __init__(
        self,
        basemodel: str | Model,
        analyst_model: str | Model,
        synthesis_model: str | Model,
        ideator_model: str | Model,
        model_settings: ModelSettings | None = None,
    ) -> None:
        self.analyst = Agent(
            name="文献分析员",
            instructions=ANALYST_INSTRUCTIONS,
            model=analyst_model,
            model_settings=model_settings,
            output_type=PaperAnalysis,
        )
        self.synthesizer = Agent(
            name="文献总结员",
            instructions=SYNTHESIZER_INSTRUCTIONS,
            model=synthesis_model,
            model_settings=model_settings,
            output_type=FieldSynthesis,
        )
        self.ideator = Agent(
            name="研究构思员",
            instructions=IDEATOR_INSTRUCTIONS,
            model=ideator_model,
            model_settings=model_settings,
            output_type=IdeaPortfolio,
        )

    async def analyze_paper(
        self, paper: Paper, context: ContextPacket | None = None
    ) -> PaperAnalysis:
        payload = "请分析以下论文元数据与摘要：\n" + paper.model_dump_json(indent=2)
        if context is not None:
            payload += (
                "\n\n以下是检索得到的论文证据。引用结论时在 citations 中填写 chunk_id：\n"
                + render_context(context)
            )
        result = await Runner.run(
            self.analyst,
            payload,
        )
        analysis = result.final_output
        if context is not None:
            allowed = {chunk.chunk_id for chunk in context.chunks}
            normalized = _normalize_citations(analysis.citations, allowed)
            notes = list(analysis.evidence_notes)
            if context.chunks and not normalized:
                notes.append("引用校验：模型未返回有效 chunk_id，引用已被过滤。")
            analysis = analysis.model_copy(
                update={"citations": normalized, "evidence_notes": notes}
            )
        return analysis

    async def synthesize(
        self, topic: str, analyses: list[PaperAnalysis]
    ) -> FieldSynthesis:
        payload = {
            "topic": topic,
            "analyses": [item.model_dump(mode="json") for item in analyses],
        }
        result = await Runner.run(
            self.synthesizer,
            "请进行跨论文综合：\n" + _json(payload),
        )
        return result.final_output

    async def ideate(
        self, topic: str, synthesis: FieldSynthesis
    ) -> IdeaPortfolio:
        payload = {
            "topic": topic,
            "synthesis": synthesis.model_dump(mode="json"),
        }
        result = await Runner.run(
            self.ideator,
            "请基于领域总结提出候选研究想法：\n" + _json(payload),
        )
        return result.final_output


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _normalize_citations(citations: list[str], allowed: set[str]) -> list[str]:
    normalized: list[str] = []
    for value in citations:
        candidate = value.strip()
        if candidate not in allowed:
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                candidate = str(parsed.get("chunk_id", ""))
        if candidate in allowed and candidate not in normalized:
            normalized.append(candidate)
    return normalized
