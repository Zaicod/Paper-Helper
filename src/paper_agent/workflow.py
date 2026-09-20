from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from paper_agent.models import (
    AnalysisFailure,
    ContextAudit,
    ContextPacket,
    Paper,
    PaperAnalysis,
    ResearchReport,
)
from paper_agent.protocols import EvidenceProvider, PaperSearch, ResearchTeam


class ResearchWorkflow:
    """Code-driven orchestration with explicit dependencies and concurrency."""

    def __init__(
        self,
        search: PaperSearch,
        team: ResearchTeam,
        max_concurrency: int = 3,
        max_retries: int = 2,
        retry_base_delay: float = 1.0,
        evidence: EvidenceProvider | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")

        self.search = search
        self.team = team
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.evidence = evidence


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
        if self.evidence is not None:
            await self.evidence.index_papers(papers)

        analyses, failures, context_audits = await self._analyze_all(papers)

        if not analyses:
            raise RuntimeError("all paper analyses failed")

        synthesis = await self.team.synthesize(topic, analyses)
        idea_portfolio = await self.team.ideate(topic, synthesis)

        return ResearchReport(
            topic=topic,
            generated_at=datetime.now(timezone.utc),
            papers=papers,
            analyses=analyses,
            analysis_failures=failures,
            synthesis=synthesis,
            idea_portfolio=idea_portfolio,
            context_audits=context_audits,
        )

    async def _analyze_all(
        self,
        papers: list[Paper],
    ) -> tuple[list[PaperAnalysis], list[AnalysisFailure], list[ContextAudit]]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def analyze_one(
            paper: Paper,
        ) -> tuple[PaperAnalysis | AnalysisFailure, ContextAudit | None]:
            context: ContextPacket | None = None
            if self.evidence is not None:
                try:
                    context = await self.evidence.build_analysis_context(paper)
                except Exception as exc:
                    return (
                        AnalysisFailure(
                            paper_id=paper.paper_id,
                            error_type=type(exc).__name__,
                            retry_count=0,
                            stage="retrieval",
                            message=str(exc),
                        ),
                        None,
                    )

            audit = (
                ContextAudit(
                    paper_id=paper.paper_id,
                    query=context.query,
                    selected_chunk_ids=[chunk.chunk_id for chunk in context.chunks],
                    dropped_count=len(context.dropped_chunk_ids),
                    estimated_tokens=context.estimated_tokens,
                    token_budget=context.token_budget,
                    source_mode=self.evidence.source_mode_for(paper.paper_id),
                )
                if context is not None and self.evidence is not None
                else None
            )

            for retry_count in range(self.max_retries + 1):
                try:
                    async with semaphore:
                        analysis = (
                            await self.team.analyze_paper(paper, context)
                            if context is not None
                            else await self.team.analyze_paper(paper)
                        )
                        return analysis, audit

                except Exception as exc:
                    if retry_count == self.max_retries:
                        return (
                            AnalysisFailure(
                                paper_id=paper.paper_id,
                                error_type=type(exc).__name__,
                                retry_count=retry_count,
                                stage="analysis",
                                message=str(exc),
                            ),
                            audit,
                        )

                    delay = self.retry_base_delay * (2**retry_count)
                    await asyncio.sleep(delay)

            raise RuntimeError("unreachable")

        results = await asyncio.gather(
            *(analyze_one(paper) for paper in papers)
        )

        outcomes = [result for result, _ in results]
        analyses = [result for result in outcomes if isinstance(result, PaperAnalysis)]
        failures = [result for result in outcomes if isinstance(result, AnalysisFailure)]
        audits = [audit for _, audit in results if audit is not None]

        return analyses, failures, audits
