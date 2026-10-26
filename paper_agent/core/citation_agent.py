"""Source-owned citation edges, separately screened for metadata relevance."""
from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, model_validator
from paper_agent.core.models import Paper
from paper_agent.core.search_agent import Contract, Short, Evidence
from paper_agent.services.paper_search import SearchPaper

Direction = Literal['references', 'citations', 'both']
WorkID = Annotated[str, Field(pattern=r'^W[1-9]\d*$')]


class CitationPath(Contract):
    seed_id: Annotated[str, Field(min_length=1, max_length=255)]
    seed_title: Annotated[str, Field(min_length=1, max_length=1024)]
    direction: Literal['references', 'citations']
    from_id: WorkID
    to_id: WorkID


class CitationResult(Contract):
    candidate_id: Annotated[str, Field(min_length=1, max_length=64)]
    paper: SearchPaper
    relevance: Literal['match', 'uncertain', 'background']
    reason: Annotated[str, Field(min_length=1, max_length=2000)]
    evidence: list[Evidence] = Field(max_length=6)
    paths: list[CitationPath] = Field(min_length=1, max_length=10)


class CitationReport(Contract):
    report_type: Literal['citation_report'] = 'citation_report'
    topic: Annotated[str, Field(min_length=1, max_length=500)]
    generated_at: datetime
    direction: Direction
    seeds: list[Paper] = Field(min_length=1, max_length=5)
    results: list[CitationResult] = Field(max_length=20)
    warnings: list[Short] = Field(max_length=30)
    gaps: list[Short] = Field(max_length=10)
    source_requests: int = Field(ge=0, le=20)
    depth: Literal[1] = 1

    @model_validator(mode='after')
    def owned_paths(self):
        seeds = {p.paper_id: p.title for p in self.seeds}
        candidates = set()
        for result in self.results:
            if result.candidate_id in candidates:
                raise ValueError('Duplicate candidate')
            candidates.add(result.candidate_id)
            for path in result.paths:
                if seeds.get(path.seed_id) != path.seed_title or path.from_id == path.to_id:
                    raise ValueError('Invalid seed provenance')
                if self.direction != 'both' and self.direction != path.direction:
                    raise ValueError('Unexpected direction')
                endpoint = path.to_id if path.direction == 'references' else path.from_id
                if endpoint != result.paper.paper_id:
                    raise ValueError('Edge must point to the candidate')
        return self
