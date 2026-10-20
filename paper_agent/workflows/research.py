"""workflows research implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Literal

from paper_agent.core.errors import PublicResearchError, public_error_message
from paper_agent.core.models import (
    AnalysisFailure,
    ContextAudit,
    ContextPacket,
    Paper,
    PaperAnalysis,
    ResearchReport,
    ResearchStageEvent,
)
from paper_agent.core.protocols import EvidenceDecider, EvidenceProvider, PaperSearch, ResearchTeam


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
        decider: EvidenceDecider | None = None,
        decision_confidence_threshold: float = 0.55,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if decider is not None and evidence is None:
            raise ValueError("a decider requires an evidence provider")
        if not 0 <= decision_confidence_threshold <= 1:
            raise ValueError("decision confidence threshold must be between 0 and 1")

        self.search = search
        self.team = team
        self.max_concurrency = max_concurrency
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.evidence = evidence
        self.decider = decider
        self.decision_confidence_threshold = decision_confidence_threshold

    async def run(
        self,
        topic: str,
        limit: int = 5,
        category: str | None = None,
        *,
        papers: list[Paper] | None = None,
        on_event: Callable[[ResearchStageEvent], Awaitable[None]] | None = None,
    ) -> ResearchReport:
        if not topic.strip():
            raise ValueError("topic cannot be empty")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        if papers is not None:
            self._validate_papers(papers)
            papers = list(papers)

        stage: Literal["search", "index", "analyze", "synthesize", "ideate"] = "search"

        async def emit(
            status: Literal["started", "completed", "failed"], message: str
        ) -> None:
            if on_event is not None:
                await on_event(ResearchStageEvent(stage=stage, status=status, message=message))

        try:
            await emit("started", "正在获取研究论文。")
            if papers is None:
                papers = await self.search.search(topic, limit, category)
            if not papers:
                raise PublicResearchError("no papers acquired for the research topic")
            self._validate_papers(papers)
            await emit("completed", f"已获取 {len(papers)} 篇论文。")

            if self.evidence is not None:
                stage = "index"
                await emit("started", "正在建立论文证据索引。")
                await self.evidence.index_papers(papers)
                await emit("completed", "论文证据索引已就绪。")

            stage = "analyze"
            await emit("started", "正在分析论文与证据。")
            analyses, failures, context_audits = await self._analyze_all(papers)
            if not analyses:
                raise PublicResearchError("all paper analyses failed")
            await emit("completed", f"已完成 {len(analyses)} 篇分析，失败 {len(failures)} 篇。")

            stage = "synthesize"
            await emit("started", "正在综合论文结论。")
            synthesis = await self.team.synthesize(topic, analyses)
            await emit("completed", "论文综合已完成。")

            stage = "ideate"
            await emit("started", "正在生成研究构思。")
            idea_portfolio = await self.team.ideate(topic, synthesis)
            await emit("completed", "研究构思已完成。")
        except Exception as exc:
            message = f"{stage}: {public_error_message(exc)}"
            await emit("failed", message)
            raise PublicResearchError(message) from exc

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

    @staticmethod
    def _validate_papers(papers: list[Paper]) -> None:
        if not 1 <= len(papers) <= 20:
            raise ValueError("papers must contain between 1 and 20 records")
        identities = [paper.paper_id for paper in papers]
        if len(set(identities)) != len(identities):
            raise ValueError("papers cannot contain duplicate paper_id values")

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
                            message=public_error_message(exc),
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
                    evidence_chunks=[c.model_copy(deep=True) for c in context.chunks],
                )
                if context is not None and self.evidence is not None
                else None
            )

            if self.decider is not None and context is not None and audit is not None:
                try:
                    # Never send an empty retrieval packet to an external model.
                    if not context.chunks:
                        return self._decision_failure(paper, "NoEvidence", audit)

                    decision = await self.decider.decide(paper, context)
                    audit.decisions.append(decision)
                    needs_more = (
                        decision.action == "retrieve_more"
                        or decision.confidence < self.decision_confidence_threshold
                    )
                    if needs_more:
                        assert self.evidence is not None
                        expanded = await self.evidence.expand_analysis_context(paper, context)
                        old_ids = {chunk.chunk_id for chunk in context.chunks}
                        context = expanded
                        audit.query = context.query
                        audit.selected_chunk_ids = [chunk.chunk_id for chunk in context.chunks]
                        audit.evidence_chunks = [c.model_copy(deep=True) for c in context.chunks]
                        audit.dropped_count = len(context.dropped_chunk_ids)
                        audit.estimated_tokens = context.estimated_tokens
                        if not context.chunks:
                            return self._decision_failure(paper, "NoEvidence", audit)
                        if not any(chunk.chunk_id not in old_ids for chunk in context.chunks):
                            return self._decision_failure(
                                paper, "NoAdditionalEvidence", audit
                            )
                        decision = await self.decider.decide(paper, context)
                        audit.decisions.append(decision)

                    if (
                        decision.action != "analyze"
                        or decision.confidence < self.decision_confidence_threshold
                    ):
                        return self._decision_failure(paper, "InsufficientEvidence", audit)
                except Exception as exc:
                    return (
                        AnalysisFailure(
                            paper_id=paper.paper_id,
                            error_type=type(exc).__name__,
                            retry_count=0,
                            stage="decision",
                            message=public_error_message(exc),
                        ),
                        audit,
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
                                message=public_error_message(exc),
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

    @staticmethod
    def _decision_failure(
        paper: Paper, error_type: str, audit: ContextAudit
    ) -> tuple[AnalysisFailure, ContextAudit]:
        return (
            AnalysisFailure(
                paper_id=paper.paper_id,
                error_type=error_type,
                retry_count=0,
                stage="decision",
                message="Retrieved evidence did not pass the decision gate.",
            ),
            audit,
        )
