from __future__ import annotations

from agents import Agent, Model, ModelSettings, Runner

from paper_agent.models import (
    FieldSynthesis,
    IdeaPortfolio,
    Paper,
    PaperAnalysis,
)
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

    async def analyze_paper(self, paper: Paper) -> PaperAnalysis:
        result = await Runner.run(
            self.analyst,
            "请分析以下论文元数据与摘要：\n" + paper.model_dump_json(indent=2),
        )
        return result.final_output

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
    import json

    return json.dumps(value, ensure_ascii=False, indent=2)
