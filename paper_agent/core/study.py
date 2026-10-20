"""Evidence-grounded learning reports; distinct from research idea reports."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from paper_agent.core.models import EvidenceChunk, Paper


class StudyModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class EvidenceReference(StudyModel):
    chunk_id: str = Field(min_length=1, max_length=512)
    page_number: int = Field(ge=1, le=200)
    source_url: str = Field(min_length=1, max_length=2048)


class StudyModule(StudyModel):
    name: str = Field(min_length=1, max_length=1000)
    purpose: str = Field(min_length=1, max_length=6000)
    inputs: str = Field(min_length=1, max_length=6000)
    outputs: str = Field(min_length=1, max_length=6000)


class StudyAnalysis(StudyModel):
    paper_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=1024)
    overview: str = Field(min_length=1, max_length=12000)
    background: str = Field(min_length=1, max_length=16000)
    methods: list[StudyModule] = Field(min_length=1, max_length=30)
    innovations: list[str] = Field(min_length=1, max_length=30)
    results: list[str] = Field(min_length=1, max_length=40)
    reflection: list[str] = Field(min_length=1, max_length=30)
    citations: list[EvidenceReference] = Field(min_length=1, max_length=100)


class StudySynthesis(StudyModel):
    synthesis: list[str] = Field(min_length=1, max_length=40)
    learning_plan: list[str] = Field(min_length=1, max_length=40)


class StudyReport(StudyModel):
    report_type: Literal['study_report'] = 'study_report'
    topic: str = Field(min_length=1, max_length=500)
    generated_at: datetime
    papers: list[Paper] = Field(min_length=1, max_length=20)
    analyses: list[StudyAnalysis] = Field(min_length=1, max_length=20)
    synthesis: list[str] = Field(min_length=1, max_length=40)
    learning_plan: list[str] = Field(min_length=1, max_length=40)
    evidence_mode: Literal['pdf'] = 'pdf'
    mode: Literal['live', 'demo'] = 'live'
    evidence_snapshots: dict[str, list[EvidenceChunk]] = Field(default_factory=dict, max_length=20)

    @model_validator(mode='after')
    def matching_papers(self):
        ids = [paper.paper_id for paper in self.papers]
        if len(ids) != len(set(ids)) or ids != [a.paper_id for a in self.analyses]:
            raise ValueError('Study report must analyze every selected paper exactly once in order')
        if any(p.title != a.title for p, a in zip(self.papers, self.analyses)):
            raise ValueError('Study report titles must match selected papers')
        if self.evidence_snapshots:
            if set(self.evidence_snapshots) != set(ids):
                raise ValueError('Evidence snapshots must cover selected papers')
            for analysis in self.analyses:
                chunks = self.evidence_snapshots[analysis.paper_id]
                if not 1 <= len(chunks) <= 30 or any(
                    c.paper_id != analysis.paper_id or not c.page_number or not c.text.strip() for c in chunks
                ):
                    raise ValueError('Invalid PDF evidence snapshot')
                allowed = {c.chunk_id: c for c in chunks}
                for citation in analysis.citations:
                    chunk = allowed.get(citation.chunk_id)
                    if chunk is None or citation.page_number != chunk.page_number or citation.source_url != chunk.source_url:
                        raise ValueError('Citation must match frozen evidence')
        return self
