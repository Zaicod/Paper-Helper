"""Domain data contracts shared across the PaperFlow application."""

from __future__ import annotations

from datetime import datetime, timezone

from typing import Literal

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
    cited_by_count: int | None = Field(default=None, ge=0)


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


class EvidenceDecision(BaseModel):
    """One bounded judgment about whether retrieved evidence can be used."""

    action: Literal["analyze", "retrieve_more", "insufficient"]
    confidence: float = Field(ge=0, le=1)
    source: str
    probabilities: dict[str, float] = Field(default_factory=dict)


class ContextAudit(BaseModel):
    """Context trace with frozen passages for reproducible historical citations."""

    paper_id: str
    query: str
    selected_chunk_ids: list[str]
    dropped_count: int
    estimated_tokens: int
    token_budget: int
    source_mode: str
    evidence_chunks: list[EvidenceChunk] = Field(default_factory=list)
    decisions: list[EvidenceDecision] = Field(default_factory=list)


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


class ResearchStageEvent(BaseModel):
    """A shared progress event emitted by every research entry point."""

    stage: Literal["search", "index", "analyze", "synthesize", "ideate"]
    status: Literal["started", "completed", "failed"]
    paper_id: str | None = None
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchReport(BaseModel):
    topic: str
    generated_at: datetime
    papers: list[Paper]
    analyses: list[PaperAnalysis]
    synthesis: FieldSynthesis
    idea_portfolio: IdeaPortfolio
    analysis_failures: list[AnalysisFailure] = Field(default_factory=list)
    context_audits: list[ContextAudit] = Field(default_factory=list)


class MindMapNode(BaseModel):
    """One auditable concept in a paper-derived mind map."""

    id: str
    label: str
    summary: str = ""
    level: int = Field(default=0, ge=0, le=4)
    paper_ids: list[str] = Field(default_factory=list)


class MindMapEdge(BaseModel):
    source: str
    target: str
    relationship: str = "包含"


class MindMapDraft(BaseModel):
    """Structured output contract shared by fixture and live agents."""

    title: str
    overview: str
    nodes: list[MindMapNode]
    edges: list[MindMapEdge]
