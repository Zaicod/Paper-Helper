"""Task-local study workflow with strict PDF evidence and structured analysis."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from paper_agent.core.errors import PublicResearchError
from paper_agent.core.models import ResearchStageEvent
from paper_agent.core.study import StudyAnalysis, StudyReport, StudySynthesis
from paper_agent.services.research import ResearchConfigurationError, ResearchOptions
from paper_agent.tools.context import ContextBuilder
from paper_agent.tools.study_pdf import StudyPDFLoader


class StudyEvidenceError(PublicResearchError):
    """An explicitly safe evidence failure, never a raw network/model exception."""


class StudyService:
    def __init__(self, options: ResearchOptions | None = None, *, loader=None, team=None, index=None):
        self.options = options or ResearchOptions()
        self.loader = loader or StudyPDFLoader()
        self.team = team
        self.index = index

    async def run(self, topic, *, papers, on_event=None, notes=None, learning_goal='', reflection='', collection_note=''):
        if not topic.strip() or not papers or not 1 <= len(papers) <= 20:
            raise ResearchConfigurationError('学习报告需要主题及 1 至 20 篇已选论文。')
        if len({p.paper_id for p in papers}) != len(papers):
            raise ResearchConfigurationError('学习报告论文标识不能重复。')
        if self.options.mode != 'live':
            raise ResearchConfigurationError('学习报告需要真实模型及开放 PDF，请选择 live 模式。')
        team = self.team if self.team is not None else self._build_team()
        from paper_agent.services.vector_store import build_paper_index
        try:
            index = self.index if self.index is not None else build_paper_index(self.options)
        except Exception:
            raise StudyEvidenceError('学习报告向量模型配置不可用，请检查 RAG 依赖和本地模型目录。') from None
        persistent = hasattr(index, 'load_paper')
        if persistent:
            index.reset_active()
        notes = notes or {}
        analyses = []
        snapshots = {}

        async def emit(stage, status, message, paper_id=None):
            if on_event:
                await on_event(ResearchStageEvent(stage=stage, status=status,
                    message=message, paper_id=paper_id))

        for paper in papers:
            await emit('index', 'started', '正在获取并解析开放 PDF。', paper.paper_id)
            try:
                phase = 'index'
                recipe = 'study-public-pdf-chars4000-overlap400-e5-token500-v1'
                version_recipe=getattr(self.loader,'recipe_for',None)
                if version_recipe:recipe+=':'+version_recipe(paper)
                cached = persistent and not self.options.rebuild_index and await index.load_paper(paper, 'pdf', recipe)
                if not cached:
                    phase = 'pdf'
                    chunks = await self.loader.load(paper)
                    if not chunks or any(c.paper_id != paper.paper_id or not c.page_number for c in chunks):
                        raise ValueError('Invalid PDF evidence')
                    phase = 'index'
                    splitter = getattr(index.embedder, 'split_chunks', None)
                    if splitter:
                        chunks = await splitter(chunks)
                    if persistent:
                        await index.replace_paper(paper, chunks, 'pdf', recipe)
                    else:
                        await index.add(chunks)
                chunks = []
                for query in (
                    f'{topic} research background problem motivation limitations',
                    f'{paper.title} model method architecture modules inputs outputs innovation',
                    f'{paper.title} experiments datasets baseline metrics ablation results conclusion',
                ):
                    chunks.extend(await index.search(query, top_k=max(4, self.options.rag_top_k), paper_id=paper.paper_id))
                packet = ContextBuilder(token_budget=self.options.context_token_budget,
                    max_chunks=30, max_chunks_per_paper=30).build(
                        f'{topic} 方法 模块 创新 实验 结果', chunks)
                if not packet.chunks:
                    raise ValueError('PDF evidence exceeds context limits')
            except Exception:
                if phase == 'index':
                    raise StudyEvidenceError(f'论文「{paper.title[:180]}」的向量索引处理失败。'
                        '请检查 RAG 依赖、本地向量模型和 Chroma 数据目录是否可用后重试。') from None
                raise StudyEvidenceError(f'论文「{paper.title[:180]}」无法获取足够的 PDF 正文证据。'
                    '请在论文资料中补充可公开访问的 HTTPS PDF 链接后重新提交；摘要和笔记不会代替 PDF 正文。') from None
            await emit('index', 'completed', '已从论文向量索引检索带页码的 PDF 正文证据。', paper.paper_id)
            await emit('analyze', 'started', 'Agent 正在解释方法模块与实验结果。', paper.paper_id)
            try:
                async with asyncio.timeout(180):
                    goal_context = (learning_goal if learning_goal.strip() else topic) + ('\n收藏夹整体笔记：' + collection_note if collection_note else '')
                    value = await team.analyze(paper, packet.chunks, goal_context,
                        notes.get(paper.paper_id, ''), reflection)
                item = StudyAnalysis.model_validate(value)
                allowed = {c.chunk_id: c for c in packet.chunks}
                if item.paper_id != paper.paper_id or item.title != paper.title:
                    raise ValueError('Foreign paper identity')
                for citation in item.citations:
                    chunk = allowed.get(citation.chunk_id)
                    if (chunk is None or citation.page_number != chunk.page_number
                            or citation.source_url != chunk.source_url):
                        raise ValueError('Fabricated citation')
            except Exception:
                raise StudyEvidenceError(f'论文「{paper.title[:180]}」的 Agent 分析或证据引用校验失败，'
                    '请检查模型配置后重新生成。报告未完成，未省略该论文。') from None
            analyses.append(item)
            snapshots[paper.paper_id] = [c.model_copy(deep=True) for c in packet.chunks]
            await emit('analyze', 'completed', '该论文学习分析已完成。', paper.paper_id)
        await emit('synthesize', 'started', 'Agent 正在综合方法对比与学习计划。')
        try:
            async with asyncio.timeout(180):
                summary = StudySynthesis.model_validate(await team.synthesize(topic, analyses, learning_goal))
        except Exception:
            raise StudyEvidenceError('学习报告综合生成失败，请检查模型配置后重试。') from None
        report = StudyReport(topic=topic, generated_at=datetime.now(timezone.utc), papers=papers,
            analyses=analyses, synthesis=summary.synthesis, learning_plan=summary.learning_plan,
            evidence_mode='pdf', mode='live', evidence_snapshots=snapshots)
        await emit('synthesize', 'completed', '学习报告已就绪，可查看并下载 Word。')
        return report

    def _build_team(self):
        from paper_agent.agents.study import AgentStudyTeam
        if self.options.credential_source == 'personal':
            from paper_agent.services.model_runtime import build_personal_model
            model, settings = build_personal_model(self.options)
            return AgentStudyTeam(model, settings, disable_tracing=True)
        if self.options.provider == 'openai':
            if not os.getenv('OPENAI_API_KEY', '').strip():
                raise ResearchConfigurationError('请在“个人设置”保存 OpenAI 密钥并设为默认后新建学习报告；若使用服务端配置，需要 OPENAI_API_KEY。')
            return AgentStudyTeam(self.options.model or os.getenv('OPENAI_MODEL', 'gpt-5.6-luna'))
        key = os.getenv('DASHSCOPE_API_KEY', '').strip()
        if not key:
            raise ResearchConfigurationError('请在“个人设置”保存 Qwen 密钥并设为默认后新建学习报告；若使用服务端配置，需要 DASHSCOPE_API_KEY。')
        from paper_agent.agents.providers import (DEFAULT_QWEN_BASE_URL, DEFAULT_QWEN_MODEL,
                                                  build_qwen_model, qwen_model_settings)
        model = build_qwen_model(key, self.options.model or os.getenv('QWEN_MODEL', DEFAULT_QWEN_MODEL),
            os.getenv('DASHSCOPE_BASE_URL', os.getenv('QWEN_BASE_URL', DEFAULT_QWEN_BASE_URL)))
        return AgentStudyTeam(model, qwen_model_settings())
