from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from paper_agent.models import Paper, PaperAnalysis, ResearchReport
from paper_agent.protocols import PaperSearch, ResearchTeam


class ResearchWorkflow:
    """Code-driven orchestration with explicit dependencies and concurrency."""

    def __init__(
        self,
        search: PaperSearch,
        team: ResearchTeam,
        max_concurrency: int = 3,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.search = search
        self.team = team
        self.max_concurrency = max_concurrency

    async def run(
        self,
        topic: str,
        limit: int = 5,
        category: str | None = None,
    ) -> ResearchReport:
        if not topic.strip():
            raise ValueError("topic cannot be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        papers = await self.search.search(topic, limit, category)
        analyses = await self._analyze_all(papers)
        synthesis = await self.team.synthesize(topic, analyses)
        idea_portfolio = await self.team.ideate(topic, synthesis)

        return ResearchReport(
            topic=topic,
            generated_at=datetime.now(timezone.utc),
            papers=papers,
            analyses=analyses,
            synthesis=synthesis,
            idea_portfolio=idea_portfolio,
        )

    async def _analyze_all(self, papers: list[Paper]) -> list[PaperAnalysis]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def analyze_one(paper: Paper) -> PaperAnalysis:
            async with semaphore:
                return await self.team.analyze_paper(paper)

        # gather preserves input order while allowing independent calls to overlap.
        return list(await asyncio.gather(*(analyze_one(paper) for paper in papers)))
