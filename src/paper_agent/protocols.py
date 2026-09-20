from __future__ import annotations

from typing import Protocol

from paper_agent.models import (
    ContextPacket,
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
    async def analyze_paper(
        self, paper: Paper, context: ContextPacket | None = None
    ) -> PaperAnalysis: ...

    async def synthesize(
        self, topic: str, analyses: list[PaperAnalysis]
    ) -> FieldSynthesis: ...

    async def ideate(
        self, topic: str, synthesis: FieldSynthesis
    ) -> IdeaPortfolio: ...


class EvidenceProvider(Protocol):
    async def index_papers(self, papers: list[Paper]) -> None: ...

    async def build_analysis_context(self, paper: Paper) -> ContextPacket: ...

    def source_mode_for(self, paper_id: str) -> str: ...
