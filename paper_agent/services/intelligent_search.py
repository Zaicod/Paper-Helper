"""Code-controlled two-round search; model suggestions never become paper metadata."""
from __future__ import annotations
import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from paper_agent.core.errors import PublicResearchError
from paper_agent.core.models import ResearchStageEvent
from paper_agent.core.search_agent import (
    SearchPlan, SearchReview, SearchCandidate, SearchResult, SearchProvenance,
    SearchTrace, SearchReport,
)
from paper_agent.core.search_query import display_query
from paper_agent.services.paper_search import SearchPaper, search_paper_page
from paper_agent.services.research import ResearchOptions
from paper_agent.tools.search import SearchTimeout, SearchRateLimit


def mentions(text, alias):
    """Match punctuation variants without confusing SEED-IV with SEED-IVI."""
    text=unicodedata.normalize('NFKC',text).casefold()
    terms=re.findall(r'\w+',unicodedata.normalize('NFKC',alias).casefold())
    if not terms: return False
    pattern=r'(?<!\w)'+r'[\s_\-‐‑–—]*'.join(re.escape(t) for t in terms)+r'(?!\w)'
    return re.search(pattern,text) is not None


def entity_matches(text, entity):
    return any(mentions(text,alias) for alias in [entity.name,*entity.aliases])


def permitted_query(query, plan):
    if not plan.entities: return True
    hits=[entity_matches(display_query(query.keywords),entity) for entity in plan.entities]
    return all(hits) if plan.entity_relation=='all' else any(hits)


def identity(paper):
    url=urlsplit(paper.page_url)
    host=(url.hostname or '').lower()
    path=url.path.rstrip('/')
    if host in ('doi.org','dx.doi.org'):
        arxiv_doi=re.fullmatch(r'/10\.48550/arxiv\.(.+)',path,re.I)
        if arxiv_doi:
            return ('arxiv',re.sub(r'v\d+$','',arxiv_doi.group(1).lower()))
        return ('doi',path.casefold())
    if paper.source=='arxiv' or host in ('arxiv.org','www.arxiv.org','export.arxiv.org'):
        identifier=paper.paper_id if paper.source=='arxiv' else path.removeprefix('/abs/').removeprefix('/pdf/')
        return ('arxiv',re.sub(r'v\d+$','',identifier.removesuffix('.pdf')))
    return ('url',urlunsplit((url.scheme.lower(),url.netloc.lower(),path,url.query,'')))


def metadata_multimodal(text):
    # This is a conservative metadata check, never a claim about the full method.
    if re.search(r'multi[ -]?modal|cross[ -]?modal|多模态',text,re.I): return True
    groups=[r'\bEEG\b|electroencephal|脑电',r'eye[ -]?(movement|tracking)|\bgaze\b|眼动',
            r'\b(audio|speech|voice)\b|语音',r'\b(text|language)\b|文本',
            r'\b(facial|face|visual|image)\b|视觉|人脸|图像']
    return sum(bool(re.search(g,text,re.I)) for g in groups)>=2


class IntelligentSearchService:
    def __init__(self,options=None,*,agent=None,search_page=None,timeout_seconds=120):
        self.options=options or ResearchOptions(mode='live',rag='none',credential_source='personal')
        self.agent=agent
        self.search_page=search_page or search_paper_page
        self.timeout=min(120,max(.001,timeout_seconds))

    async def run(self,topic,limit=10,*,on_event=None):
        topic=topic.strip()
        if not topic or len(topic.encode('utf-16-le'))//2>500 or not 1<=limit<=20:
            raise PublicResearchError('请输入 1 至 500 字的问题，结果数量为 1 至 20。')
        async def emit(status,message):
            if on_event: await on_event(ResearchStageEvent(stage='search',status=status,message=message))
        try:
            async with asyncio.timeout(self.timeout):
                await emit('started','正在理解问题并制定智能检索计划。')
                agent=self.agent or self._build_agent()
                plan=SearchPlan.model_validate(await agent.plan(topic))
                return await self._execute(topic,limit,plan,agent,emit)
        except TimeoutError:
            raise PublicResearchError('智能搜索执行超时，请缩小问题范围后重试。') from None
        except PublicResearchError:
            raise
        except Exception:
            raise PublicResearchError('智能搜索规划或审查失败，请检查模型配置后重试。') from None

    def _build_agent(self):
        if self.options.mode!='live' or self.options.credential_source!='personal':
            raise PublicResearchError('智能搜索需要在个人设置中配置默认模型和 API Key。')
        from paper_agent.services.model_runtime import build_personal_model
        from paper_agent.agents.search import SearchAgent
        model,settings=build_personal_model(self.options)
        return SearchAgent(model,settings)

    async def _execute(self,topic,limit,plan,agent,emit):
        candidates=[]; by_identity={}; traces=[]; warnings=[]; seen_queries=set(); assessments={}
        successes=0; rounds=1; gaps=[]
        wants_multimodal=bool(re.search(r'multi[ -]?modal|多模态',topic+' '+' '.join(plan.concepts),re.I))
        queries=plan.queries[:4]
        for round_number in (1,2):
            rounds=round_number
            if round_number==2: queries=review.queries[:2]
            await emit('started',f'第 {round_number} 轮：正在检索真实文献来源。')
            for query in queries:
                if len(traces)>=6: break
                label=display_query(query.keywords)
                query_key=(query.source,tuple((k.text.casefold(),k.match_mode) for k in query.keywords))
                if query_key in seen_queries: continue
                if not permitted_query(query,plan):
                    warnings.append('已跳过丢失指定实体约束的查询。')
                    continue
                seen_queries.add(query_key)
                status='ok'; count=0
                try:
                    response=await self.search_page(label,query.source,20,1,'relevance',
                        keywords=[k.model_dump() for k in query.keywords])
                    raw=response['papers']
                    if not isinstance(raw,list) or len(raw)>20: raise ValueError('Invalid source batch')
                    papers=[SearchPaper.model_validate(p) for p in raw]
                    if any(p.source!=query.source for p in papers): raise ValueError('Invalid source identity')
                    count=len(papers); successes+=1
                    status='ok' if papers else 'empty'
                    if response.get('warnings'):
                        warnings.append(f'{query.source} 返回来源提示，覆盖范围可能受限。')
                    for paper in papers:
                        key=identity(paper)
                        candidate=by_identity.get(key)
                        if candidate is None:
                            if len(candidates)>=60: continue
                            candidate=SearchCandidate(candidate_id=f'p{len(candidates)+1}',paper=paper,provenance=[])
                            by_identity[key]=candidate; candidates.append(candidate)
                        provenance=SearchProvenance(source=query.source,query=label)
                        if provenance not in candidate.provenance: candidate.provenance.append(provenance)
                except (TimeoutError,SearchTimeout): status='timeout'
                except SearchRateLimit: status='rate_limited'
                except Exception: status='unavailable'
                traces.append(SearchTrace(round=round_number,source=query.source,query=label,count=count,status=status))
                if status not in ('ok','empty'):
                    warnings.append(f'{query.source} 本次检索未完成（{status}），不能据此判断没有相关论文。')
            await emit('started',f'第 {round_number} 轮：正在审查 {len(candidates)} 篇候选的元数据相关性。')
            review=SearchReview.model_validate(await agent.review(topic,plan,candidates,round_number))
            gaps=review.gaps
            known={c.candidate_id:c for c in candidates}
            reviewed=set()
            for assessment in review.assessments:
                candidate=known.get(assessment.candidate_id)
                if candidate is None or assessment.candidate_id in reviewed:
                    warnings.append('已忽略无效或重复的候选引用。'); continue
                reviewed.add(assessment.candidate_id)
                metadata=[candidate.paper.title,candidate.paper.abstract]
                evidence=[s for s in assessment.evidence if any(s in text for text in metadata)]
                invalid_evidence=len(evidence)!=len(assessment.evidence)
                hits=[e.name for e in plan.entities if entity_matches('\n'.join(evidence),e)]
                matched=list(dict.fromkeys(name for name in assessment.matched_entities if name in hits))
                relevance=assessment.relevance
                required={e.name for e in plan.entities}
                missing_entities=required and (not required.issubset(set(matched)) if plan.entity_relation=='all' else not matched)
                modality=assessment.modality
                if modality=='multimodal' and not metadata_multimodal('\n'.join(evidence)):
                    modality='unknown'
                if relevance=='match' and (not evidence or invalid_evidence or missing_entities or (wants_multimodal and modality=='unknown')):
                    relevance='uncertain'
                if wants_multimodal and modality=='unimodal': relevance='background'
                if invalid_evidence or len(matched)!=len(assessment.matched_entities):
                    warnings.append('部分模型证据或实体标注缺少元数据依据，已移除并降低确定性。')
                reason=assessment.reason if not invalid_evidence else '候选元数据不足以支持模型给出的理由，需人工核实。'
                assessments[candidate.candidate_id]=SearchResult(candidate_id=candidate.candidate_id,paper=candidate.paper,
                    relevance=relevance,reason=reason,evidence=evidence,matched_entities=matched,
                    modality=modality,provenance=candidate.provenance)
            if round_number==2 or not review.queries or sum(r.relevance=='match' for r in assessments.values())>=limit:
                break
        if not traces:
            raise PublicResearchError('检索计划未保留指定实体，请补充问题后重试。')
        if successes==0:
            raise PublicResearchError('所有文献来源检索均未完成，请稍后重试或使用普通搜索。')
        for candidate in candidates:
            if candidate.candidate_id not in assessments:
                assessments[candidate.candidate_id]=SearchResult(candidate_id=candidate.candidate_id,paper=candidate.paper,
                    relevance='uncertain',reason='尚无足够元数据审查依据，请核对论文正文。',evidence=[],matched_entities=[],
                    modality='unknown',provenance=candidate.provenance)
        order={'match':0,'uncertain':1,'background':2}
        for candidate in candidates:
            assessments[candidate.candidate_id].provenance=list(candidate.provenance)
        results=sorted(assessments.values(),key=lambda r:order[r.relevance])[:limit]
        for entity in plan.entities:
            if not any(entity.name in r.matched_entities for r in results):
                gaps.append(f'本次返回候选尚未找到 {entity.name} 的充分元数据证据。')
        if not results: gaps=[*gaps,'本次查询没有召回候选；不代表不存在相关论文。']
        elif not any(r.relevance=='match' for r in results): gaps=[*gaps,'本次候选尚无足够证据满足全部检索条件。']
        await emit('completed',f'智能搜索完成：整理 {len(results)} 篇候选，请结合证据核对。')
        return SearchReport(topic=topic,generated_at=datetime.now(timezone.utc),plan=plan,results=results,
            searches=traces,warnings=list(dict.fromkeys(warnings))[:20],gaps=list(dict.fromkeys(gaps))[:10],rounds=rounds)
