"""Controlled planning/retrieval tests; no real model or literature API calls."""
import asyncio
import unittest
from paper_agent.core.search_agent import SearchPlan, SearchQuery, SearchReview, SearchAssessment
from paper_agent.services.intelligent_search import IntelligentSearchService
from paper_agent.core.errors import PublicResearchError


def query(term, source='openalex'):
    return SearchQuery(source=source, keywords=[{'text': term, 'match_mode': 'fuzzy'}], purpose='检索指定数据集')


def paper(pid, title, abstract='', source='openalex'):
    return dict(paper_id=pid, source=source, title=title, abstract=abstract,
                authors=['Researcher'], categories=[], page_url=f'https://example.org/{pid}')


def plan():
    return SearchPlan(summary='查找 EEG 与眼动融合的情绪识别论文',
        concepts=['multimodal emotion recognition', 'EEG', 'eye movement'],
        entities=[{'name':'SEED-IV','aliases':['seediv','SEED IV']},
                  {'name':'SEED-VII','aliases':['seedvii','SEED VII']}], entity_relation='any',
        constraints=['优先多模态，两个数据集任一匹配'],
        queries=[query('SEED-IV emotion recognition'),query('SEED-VII multimodal','crossref')])


class FakeAgent:
    def __init__(self, review=None):
        self.plans=[]; self.reviews=[]; self.review_fn=review
    async def plan(self, topic):
        self.plans.append(topic)
        return plan()
    async def review(self, topic, search_plan, candidates, round_number):
        self.reviews.append((candidates,round_number))
        if self.review_fn:
            return self.review_fn(candidates,round_number)
        return SearchReview(assessments=[SearchAssessment(candidate_id=c.candidate_id,
            relevance='match',reason='元数据包含指定数据集与模态',
            evidence=[c.paper.abstract or c.paper.title],matched_entities=['SEED-IV'],
            modality='multimodal') for c in candidates],queries=[],gaps=[])


class IntelligentSearchTest(unittest.IsolatedAsyncioTestCase):
    async def test_seed_aliases_search_separately_and_merge_true_sources(self):
        calls=[]
        async def retrieve(q,source,limit,page,sort,**kwargs):
            calls.append((q,source))
            return {'papers':[paper(source,'Fusion','EEG and eye movement on SEED-IV',source)]}
        agent=FakeAgent()
        result=await IntelligentSearchService(agent=agent,search_page=retrieve).run('多模态情绪识别 seediv seedvii',10)
        self.assertEqual(len(calls),2)
        self.assertEqual({s.source for s in result.searches},{'openalex','crossref'})
        self.assertEqual(result.plan.entity_relation,'any')
        self.assertEqual(len(result.results),2)
        self.assertTrue(all(r.evidence and r.paper.page_url.startswith('https://') for r in result.results))

    async def test_invented_candidate_or_evidence_never_reaches_result(self):
        async def retrieve(*args,**kwargs): return {'papers':[paper('one','SEED-IV EEG study','Only EEG signals')]}
        def review(candidates,r):
            return SearchReview(assessments=[
                SearchAssessment(candidate_id='invented',relevance='match',reason='fake',evidence=['invented'],matched_entities=[],modality='unknown'),
                SearchAssessment(candidate_id=candidates[0].candidate_id,relevance='match',reason='fake evidence',
                    evidence=['EEG and eye movement fusion'],matched_entities=['SEED-VII'],modality='multimodal')],queries=[],gaps=[])
        result=await IntelligentSearchService(agent=FakeAgent(review),search_page=retrieve).run('seediv seedvii',10)
        self.assertEqual(result.results[0].relevance,'uncertain')
        self.assertEqual(result.results[0].evidence,[])
        self.assertEqual(result.results[0].matched_entities,[])
        self.assertTrue(result.warnings)

    async def test_cross_source_same_url_keeps_provenance_and_original_metadata(self):
        async def retrieve(q,source,*args,**kwargs):
            p=paper('shared','Original verified title','SEED-IV EEG and eye movement',source)
            p['page_url']='https://doi.org/10.1000/test'
            return {'papers':[p]}
        result=await IntelligentSearchService(agent=FakeAgent(),search_page=retrieve).run('SEED-IV',10)
        self.assertEqual(len(result.results),1)
        self.assertEqual(len(result.results[0].provenance),2)
        self.assertEqual(result.results[0].paper.title,'Original verified title')

    async def test_two_round_budget_and_refinements_retain_required_entities(self):
        calls=[]
        async def retrieve(q,source,*args,**kwargs):
            calls.append(q)
            return {'papers':[paper(str(len(calls)),'SEED-IV study','SEED-IV EEG')]} if source=='openalex' else {'papers':[]}
        def review(candidates,r):
            return SearchReview(assessments=[],queries=[query('SEED-IV EEG eye movement'),query('unrelated generic fusion')],gaps=['缺少多模态证据'])
        result=await IntelligentSearchService(agent=FakeAgent(review),search_page=retrieve).run('SEED-IV SEED-VII',10)
        self.assertEqual(result.rounds,2)
        self.assertNotIn('unrelated generic fusion',calls)
        self.assertLessEqual(len(calls),6)
        self.assertTrue(result.gaps)

    async def test_partial_failure_keeps_results_but_all_failure_is_error(self):
        async def partial(q,source,*args,**kwargs):
            if source=='crossref': raise RuntimeError('secret-upstream-body')
            return {'papers':[paper('ok','SEED-IV study','SEED-IV EEG and eye movement')]}
        result=await IntelligentSearchService(agent=FakeAgent(),search_page=partial).run('SEED-IV',10)
        self.assertTrue(result.results)
        self.assertNotIn('secret-upstream-body',result.model_dump_json())
        async def fail(*args,**kwargs): raise RuntimeError('secret-upstream-body')
        with self.assertRaisesRegex(PublicResearchError,'来源'):
            await IntelligentSearchService(agent=FakeAgent(),search_page=fail).run('SEED-IV',10)

    async def test_zero_is_valid_and_different_from_provider_failure(self):
        async def empty(*args,**kwargs): return {'papers':[]}
        result=await IntelligentSearchService(agent=FakeAgent(),search_page=empty).run('SEED-IV',10)
        self.assertEqual(result.results,[])
        self.assertTrue(result.gaps)

    async def test_timeout_covers_planner_and_never_leaks_exception_details(self):
        class Slow(FakeAgent):
            async def plan(self,topic): await asyncio.Event().wait()
        with self.assertRaisesRegex(PublicResearchError,'超时'):
            await IntelligentSearchService(agent=Slow(),timeout_seconds=.02).run('SEED-IV',10)

    async def test_unknown_modality_does_not_disqualify_non_multimodal_questions(self):
        class General(FakeAgent):
            async def plan(self,topic):
                return SearchPlan(summary='检索优化算法',concepts=['optimization'],entities=[],entity_relation='any',
                                  constraints=[],queries=[query('optimization')])
            async def review(self,topic,search_plan,candidates,round_number):
                return SearchReview(assessments=[SearchAssessment(candidate_id='p1',relevance='match',
                    reason='摘要包含优化算法',evidence=['optimization method'],matched_entities=[],modality='unknown')],
                    queries=[],gaps=[])
        async def retrieve(*args,**kwargs): return {'papers':[paper('one','An optimization method')]}
        report=await IntelligentSearchService(agent=General(),search_page=retrieve).run('优化算法',10)
        self.assertEqual(report.results[0].relevance,'match')

    async def test_missing_dataset_coverage_is_explicit_even_when_model_omits_gap(self):
        async def retrieve(q,source,*args,**kwargs):
            return {'papers':[paper(source,'Fusion','SEED-IV EEG and eye movement',source)]}
        report=await IntelligentSearchService(agent=FakeAgent(),search_page=retrieve).run('seediv seedvii',10)
        self.assertTrue(any('SEED-VII' in gap for gap in report.gaps))

    async def test_alias_matching_does_not_confuse_seed_versions(self):
        from paper_agent.services.intelligent_search import mentions
        self.assertTrue(mentions('Compared on SEED-IV and SEED VII.','SEED-IV'))
        self.assertFalse(mentions('Compared on SEED-IVI.','SEED-IV'))
        self.assertFalse(mentions('SEED-VIII results','SEED-VII'))

    async def test_duplicate_entity_annotations_cannot_satisfy_all_relation(self):
        class All(FakeAgent):
            async def plan(self,topic):
                p=plan();p.entity_relation='all'
                p.queries=[query('SEED-IV SEED-VII EEG')]
                return p
            async def review(self,topic,p,candidates,r):
                return SearchReview(assessments=[SearchAssessment(candidate_id='p1',relevance='match',
                    reason='错误地重复标注',evidence=['SEED-IV EEG and eye movement'],
                    matched_entities=['SEED-IV','SEED-IV'],modality='multimodal')],queries=[],gaps=[])
        async def retrieve(*args,**kwargs): return {'papers':[paper('one','Fusion','SEED-IV EEG and eye movement')]}
        result=await IntelligentSearchService(agent=All(),search_page=retrieve).run('同时满足两个数据集',10)
        self.assertEqual(result.results[0].matched_entities,['SEED-IV'])
        self.assertEqual(result.results[0].relevance,'uncertain')

    async def test_arxiv_doi_and_versioned_page_merge(self):
        async def retrieve(q,source,*args,**kwargs):
            p=paper(source,'A multimodal study','SEED-IV EEG and eye movement',source)
            p['page_url']=('https://doi.org/10.48550/arXiv.2005.11401' if source=='openalex'
                           else 'https://arxiv.org/abs/2005.11401v4')
            return {'papers':[p]}
        result=await IntelligentSearchService(agent=FakeAgent(),search_page=retrieve).run('SEED-IV',10)
        self.assertEqual(len(result.results),1)
        self.assertEqual(len(result.results[0].provenance),2)


if __name__=='__main__': unittest.main()
