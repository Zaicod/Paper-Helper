from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Paper(BaseModel):
    """A paper record returned by a trusted search provider."""

    paper_id: str
    source: str = "unknown"
    title: str
    authors: list[str]
    abstract: str
    published: str | None = None
    categories: list[str] = Field(default_factory=list)
    page_url: str
    pdf_url: str | None = None


class PaperAnalysis(BaseModel):
    """Structured evidence extracted from one paper's title and abstract."""

    paper_id: str
    title: str
    research_problem: str
    innovation_points: list[str]
    methods: list[str]
    results: list[str]
    limitations: list[str]
    evidence_notes: list[str]
    datasets: list[str]
    citations: list[str] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    """A retrievable passage with enough metadata to audit its origin."""

    chunk_id: str
    paper_id: str
    text: str
    source_url: str
    page_number: int | None = None
    score: float = 0.0


class ContextPacket(BaseModel):
    """Evidence selected for one model call under an explicit token budget."""

    query: str
    chunks: list[EvidenceChunk]
    estimated_tokens: int
    token_budget: int
    dropped_chunk_ids: list[str] = Field(default_factory=list)


class ContextAudit(BaseModel):
    """Compact context-engineering trace stored without duplicating full passages."""

    paper_id: str
    query: str
    selected_chunk_ids: list[str]
    dropped_count: int
    estimated_tokens: int
    token_budget: int
    source_mode: str


class FieldSynthesis(BaseModel):
    """Cross-paper understanding of a research direction."""

    topic: str
    overview: str
    method_taxonomy: list[str]
    common_findings: list[str]
    disagreements: list[str]
    research_gaps: list[str]
    evidence_map: list[str]
    


class ResearchIdea(BaseModel):
    """A testable idea derived from the synthesis, not a novelty guarantee."""

    title: str
    target_gap: str
    hypothesis: str
    proposed_method: list[str]
    expected_contribution: str
    evaluation_plan: list[str]
    risks: list[str]
    related_paper_ids: list[str]


class IdeaPortfolio(BaseModel):
    topic: str
    ideas: list[ResearchIdea]
    caution: str


class AnalysisFailure(BaseModel):
    """A paper that could not be analyzed after retries."""

    paper_id: str
    error_type: str
    retry_count: int
    stage: str = "analysis"
    message: str = ""


class ResearchReport(BaseModel):
    topic: str
    generated_at: datetime
    papers: list[Paper]
    analyses: list[PaperAnalysis]
    synthesis: FieldSynthesis
    idea_portfolio: IdeaPortfolio
    analysis_failures: list[AnalysisFailure] = Field(default_factory=list)
    context_audits: list[ContextAudit] = Field(default_factory=list)
