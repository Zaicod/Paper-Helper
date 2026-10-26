"""Bounded, auditable contracts for analysis-driven literature search."""
from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from paper_agent.core.search_query import SearchKeyword, normalize_keywords
from paper_agent.services.paper_search import SearchPaper

Short = Annotated[str, Field(min_length=1, max_length=500)]
Evidence = Annotated[str, Field(min_length=1, max_length=2000)]


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchEntity(Contract):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    aliases: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(max_length=8)


class SearchQuery(Contract):
    source: Literal['arxiv','openalex','crossref']
    keywords: list[SearchKeyword] = Field(min_length=1,max_length=10)
    purpose: Short

    @model_validator(mode='after')
    def valid_keywords(self):
        normalize_keywords(self.keywords)
        if self.source=='crossref' and any(k.match_mode=='exact' for k in self.keywords):
            raise ValueError('Crossref cannot preserve exact phrase semantics')
        return self


class SearchPlan(Contract):
    summary: Annotated[str, Field(min_length=1,max_length=2000)]
    concepts: list[Short] = Field(min_length=1,max_length=12)
    entities: list[SearchEntity] = Field(max_length=10)
    entity_relation: Literal['any','all']
    constraints: list[Short] = Field(max_length=10)
    queries: list[SearchQuery] = Field(min_length=1,max_length=6)


class SearchAssessment(Contract):
    candidate_id: Annotated[str, Field(min_length=1,max_length=64)]
    relevance: Literal['match','uncertain','background']
    reason: Annotated[str, Field(min_length=1,max_length=2000)]
    evidence: list[Evidence] = Field(max_length=6)
    matched_entities: list[Annotated[str, Field(min_length=1,max_length=100)]] = Field(max_length=10)
    modality: Literal['multimodal','unimodal','unknown']


class SearchReview(Contract):
    assessments: list[SearchAssessment] = Field(max_length=60)
    queries: list[SearchQuery] = Field(max_length=6)
    gaps: list[Short] = Field(max_length=10)


class SearchProvenance(Contract):
    source: Literal['arxiv','openalex','crossref']
    query: Short


class SearchCandidate(Contract):
    candidate_id: str
    paper: SearchPaper
    provenance: list[SearchProvenance] = Field(max_length=6)


class SearchResult(SearchAssessment):
    paper: SearchPaper
    provenance: list[SearchProvenance] = Field(min_length=1,max_length=6)


class SearchTrace(Contract):
    round: Literal[1,2]
    source: Literal['arxiv','openalex','crossref']
    query: Short
    count: int = Field(ge=0,le=20)
    status: Literal['ok','empty','unavailable','timeout','rate_limited']


class SearchReport(Contract):
    report_type: Literal['search_report'] = 'search_report'
    topic: Annotated[str, Field(min_length=1,max_length=500)]
    generated_at: datetime
    plan: SearchPlan
    results: list[SearchResult] = Field(max_length=20)
    searches: list[SearchTrace] = Field(max_length=6)
    warnings: list[Short] = Field(max_length=20)
    gaps: list[Short] = Field(max_length=10)
    rounds: Literal[1,2]
