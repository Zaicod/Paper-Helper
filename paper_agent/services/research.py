"""Shared research configuration and execution for CLI and HTTP adapters."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from paper_agent.core.errors import PublicResearchError
from paper_agent.core.models import Paper, ResearchReport, ResearchStageEvent
from paper_agent.core.protocols import EvidenceDecider, EvidenceProvider, PaperSearch, ResearchTeam
from paper_agent.tools.search import ArxivSearchClient, FallbackSearchClient, OpenAlexSearchClient
from paper_agent.workflows.research import ResearchWorkflow
from paper_agent.services.model_runtime import RuntimeCredentials


class ResearchConfigurationError(ValueError, PublicResearchError):
    """A requested execution mode cannot be configured safely."""


class ResearchOptions(BaseModel):
    mode: Literal['demo', 'live'] = 'live'
    rag: Literal['none', 'abstract', 'pdf'] = 'abstract'
    decision: Literal['none', 'fixture', 'jev'] = 'none'
    provider: Literal['qwen', 'openai'] = 'qwen'
    model: str | None = None
    source: Literal['auto', 'arxiv', 'openalex'] = 'auto'
    embedding_provider: Literal['local', 'qwen'] = 'local'
    embedding_model: str | None = None
    context_token_budget: int = Field(default=6000, ge=1, le=128000)
    rag_top_k: int = Field(default=4, ge=1, le=20)
    index_namespace: str = Field(default='cli-local', min_length=1, max_length=128, pattern=r'^[A-Za-z0-9:_-]+$')
    rebuild_index: bool = False
    credential_source: Literal['server', 'personal'] = 'server'
    runtime_credentials: RuntimeCredentials | None = Field(default=None, exclude=True, repr=False)

    @model_validator(mode='after')
    def validate_evidence_mode(self):
        if self.decision != 'none' and self.rag == 'none':
            raise ValueError('证据决策需要 RAG：请选择 abstract 或 pdf。')
        if self.mode == 'live' and self.decision == 'fixture':
            raise ValueError('fixture 决策仅用于 demo 模式。')
        if self.mode == 'demo' and (
            self.rag == 'pdf' or self.embedding_provider != 'local' or self.decision == 'jev'
        ):
            raise ValueError('demo 必须离线：使用摘要 RAG、本地向量和 none/fixture 决策。')
        return self


def build_live_search(source: str) -> PaperSearch:
    if source == 'arxiv':
        return ArxivSearchClient()
    if source == 'openalex':
        return OpenAlexSearchClient(api_key=os.getenv('OPENALEX_API_KEY'))
    return FallbackSearchClient([
        ArxivSearchClient(timeout_seconds=8.0),
        OpenAlexSearchClient(api_key=os.getenv('OPENALEX_API_KEY')),
    ])


class ResearchService:
    """Build task-local dependencies; never silently substitute a demo in live mode."""

    def __init__(
        self,
        options: ResearchOptions | None = None,
        *,
        search: PaperSearch | None = None,
        team: ResearchTeam | None = None,
        evidence: EvidenceProvider | None = None,
        decider: EvidenceDecider | None = None,
        index_path: Path | None = None,
    ) -> None:
        self.options = options or ResearchOptions()
        self.search = search
        self.team = team
        self.evidence = evidence
        self.decider = decider
        self.index_path = index_path

    async def run(
        self, topic: str, limit: int = 5, category: str | None = None,
        *, papers: list[Paper] | None = None,
        on_event: Callable[[ResearchStageEvent], Awaitable[None]] | None = None,
    ) -> ResearchReport:
        if not topic.strip():
            raise ResearchConfigurationError('研究主题不能为空。')
        if not 1 <= limit <= 20:
            raise ResearchConfigurationError('论文数量必须为 1 至 20 篇。')
        if papers is not None:
            if not 1 <= len(papers) <= 20:
                raise ResearchConfigurationError('请选择 1 至 20 篇论文。')
            if len({p.paper_id for p in papers}) != len(papers):
                raise ResearchConfigurationError('论文 ID 重复，无法区分证据来源。')
        team = self.team if self.team is not None else self._build_team()
        if self.search is not None:
            search = self.search
        elif self.options.mode == 'demo':
            from paper_agent.tools.search import FixtureSearchClient
            search = FixtureSearchClient()
        else:
            search = build_live_search(self.options.source)
        # Build a fresh index for each run to avoid mixing task evidence.
        evidence = self.evidence if self.evidence is not None else self._build_evidence()
        decider = self.decider if self.decider is not None else self._build_decider()
        workflow = ResearchWorkflow(search, team, evidence=evidence, decider=decider)
        return await workflow.run(
            topic, limit, category, papers=papers, on_event=on_event,
        )

    def _build_team(self) -> ResearchTeam:
        if self.options.mode == 'demo':
            from paper_agent.agents.demo import DemoResearchTeam
            return DemoResearchTeam()
        if self.options.credential_source == 'personal':
            from paper_agent.services.model_runtime import build_personal_model
            from paper_agent.agents.team import AgentResearchTeam
            model, settings = build_personal_model(self.options)
            return AgentResearchTeam(model, model, model, model, model_settings=settings, disable_tracing=True)
        if self.options.provider == 'openai':
            key = os.getenv('OPENAI_API_KEY', '').strip()
            if not key:
                raise ResearchConfigurationError('OpenAI live 模式需要 OPENAI_API_KEY。')
            from paper_agent.agents.team import AgentResearchTeam
            model = self.options.model or os.getenv('OPENAI_MODEL', 'gpt-5.6-luna')
            return AgentResearchTeam(model, model, model, model)
        key = os.getenv('DASHSCOPE_API_KEY', '').strip()
        if not key:
            raise ResearchConfigurationError('Qwen live 模式需要 DASHSCOPE_API_KEY。')
        from paper_agent.agents.providers import (
            DEFAULT_QWEN_BASE_URL, DEFAULT_QWEN_MODEL, build_qwen_model, qwen_model_settings,
        )
        from paper_agent.agents.team import AgentResearchTeam
        model = build_qwen_model(
            key, self.options.model or os.getenv('QWEN_MODEL', DEFAULT_QWEN_MODEL),
            os.getenv('DASHSCOPE_BASE_URL', os.getenv('QWEN_BASE_URL', DEFAULT_QWEN_BASE_URL)),
        )
        return AgentResearchTeam(model, model, model, model, model_settings=qwen_model_settings())

    def _build_evidence(self) -> EvidenceProvider | None:
        if self.options.rag == 'none':
            return None
        from paper_agent.tools.context import ContextBuilder
        from paper_agent.tools.rag import HashingEmbedder, PaperRAG
        from paper_agent.services.vector_store import build_paper_index
        index = build_paper_index(self.options) if self.options.mode == 'live' else None
        embedder = index.embedder if index is not None else HashingEmbedder()
        return PaperRAG(
            embedder,
            include_pdfs=self.options.rag == 'pdf',
            top_k_per_query=self.options.rag_top_k,
            context_builder=ContextBuilder(
                token_budget=self.options.context_token_budget,
                max_chunks=max(3, self.options.rag_top_k * 3),
            ),
            index_path=self.index_path,
            index=index,
            rebuild_index=self.options.rebuild_index,
        )

    def _build_decider(self) -> EvidenceDecider | None:
        if self.options.decision == 'none':
            return None
        from paper_agent.tools.decision import FixtureEvidenceDecider, JevEvidenceDecider
        if self.options.decision == 'fixture':
            return FixtureEvidenceDecider()
        key = os.getenv('TYPESAFE_API_KEY', '').strip()
        if not key:
            raise ResearchConfigurationError('jev 决策需要 TYPESAFE_API_KEY。')
        return JevEvidenceDecider(key, model=os.getenv('JEV_MODEL', 'jev-latest'))
