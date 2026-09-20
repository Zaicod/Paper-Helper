from __future__ import annotations

from typing import Protocol

from paper_agent.models import (
    FieldSynthesis,
    IdeaPortfolio,
    Paper,
    PaperAnalysis,
)


class PaperSearch(Protocol):
    async def search(
        self, topic: str, limit: int, category: str | None = None
    ) -> list[Paper]: ...


class ResearchTeam(Protocol):
    async def analyze_paper(self, paper: Paper) -> PaperAnalysis: ...

    async def synthesize(
        self, topic: str, analyses: list[PaperAnalysis]
    ) -> FieldSynthesis: ...

    async def ideate(
        self, topic: str, synthesis: FieldSynthesis
    ) -> IdeaPortfolio: ...
