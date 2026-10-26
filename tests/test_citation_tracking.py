import unittest
import asyncio
import json
import httpx
from paper_agent.core.models import Paper
from paper_agent.core.errors import PublicResearchError
from paper_agent.core.search_agent import SearchPlan, SearchReview, SearchAssessment
from paper_agent.tools.citation_graph import OpenAlexGraphClient, GraphBatch, GraphError
from paper_agent.services.citation_tracking import CitationTrackingService


def work(number, refs=(), title=None, doi=None):
    return dict(id=f'https://openalex.org/W{number}', doi=doi,
        display_name=title or f'SEED-IV multimodal emotion recognition {number}',
        referenced_works=[f'https://openalex.org/W{x}' for x in refs],
        authorships=[], abstract_inverted_index={'EEG':[0], 'and':[1], 'eye':[2], 'SEED-IV':[3]},
        primary_location={}, publication_date='2025-01-01')


def seed(number):
    return Paper(paper_id=f'W{number}', source='openalex', title=f'Seed {number}',
        authors=[], abstract='', page_url=f'https://openalex.org/W{number}')


class Agent:
    def __init__(self, fabricated=False): self.calls=0; self.fabricated=fabricated
    async def plan(self, topic):
        self.calls+=1
        return SearchPlan(summary='SEED-IV', concepts=['emotion recognition'], entities=[],
            entity_relation='any',constraints=[], queries=[{'source':'openalex',
            'keywords':[{'text':'SEED-IV','match_mode':'fuzzy'}], 'purpose':'find papers'}])
    async def review(self, topic, plan, candidates, round_number):
        self.calls+=1
        return SearchReview(assessments=[SearchAssessment(candidate_id=c.candidate_id,
            relevance='match',reason='related metadata',evidence=['invented' if self.fabricated else c.paper.title],
            matched_entities=[],modality='multimodal') for c in candidates],queries=[],gaps=[])


class Graph:
    def __init__(self, fail=None, count=3): self.requests=0; self.fail=fail; self.count=count; self.calls=[]
    async def resolve(self,p):
        self.requests+=1
        return work(int(p.paper_id[1:]), refs=[2,3])
    async def neighbors(self, value, direction):
        self.requests+=1; self.calls.append((value['id'],direction))
        if self.fail==direction or self.fail=='all': raise GraphError('unavailable')
        return GraphBatch([work(n,refs=[1] if direction=='citations' else []) for n in range(1,self.count+1)],truncated=self.count>20)


class TrackingTests(unittest.IsolatedAsyncioTestCase):
    async def test_planning_receives_seed_metadata_with_the_original_question(self):
        class ContextAgent(Agent):
            async def plan(self,topic):
                self.planning_input=topic
                return await super().plan(topic)
        agent=ContextAgent();p=seed(1).model_copy(update={'abstract':'SEED-VII EEG and gaze fusion'})
        r=await CitationTrackingService(agent=agent,graph=Graph()).run('Follow the selected topic',papers=[p])
        self.assertIn('SEED-VII EEG and gaze fusion',agent.planning_input)
        self.assertIn(p.title,agent.planning_input)
        self.assertIn('Follow the selected topic',agent.planning_input)
        self.assertEqual(r.topic,'Follow the selected topic')

    async def test_partial_timeout_retains_completed_direction(self):
        class SlowGraph(Graph):
            async def neighbors(self,value,direction):
                if direction=='citations': await asyncio.sleep(.1)
                return await super().neighbors(value,direction)
        r=await CitationTrackingService(agent=Agent(),graph=SlowGraph(),timeout_seconds=.02).run('SEED-IV',20,papers=[seed(1)])
        self.assertEqual(len(r.results),2)
        self.assertTrue(r.warnings)
        self.assertTrue(all(p.direction=='references' for r in r.results for p in r.paths))

    async def test_sixty_distinct_candidates_bound_model_input(self):
        class ManyGraph(Graph):
            async def neighbors(self,value,direction):
                self.requests+=1
                start=int(value['id'].split('W')[-1])*100+(50 if direction=='citations' else 0)
                return GraphBatch([work(start+i,[1]) for i in range(20)])
        class CountingAgent(Agent):
            async def review(self,topic,plan,candidates,round_number):
                self.candidate_count=len(candidates)
                return await super().review(topic,plan,candidates,round_number)
        agent=CountingAgent();graph=ManyGraph()
        r=await CitationTrackingService(agent=agent,graph=graph).run('SEED-IV',20,papers=[seed(i) for i in range(1,6)])
        self.assertEqual(agent.candidate_count,60)
        self.assertEqual(len(r.results),20)
        self.assertEqual(agent.calls,2)
        self.assertLessEqual(graph.requests,20)
        self.assertTrue(r.warnings)

    async def test_duplicate_doi_never_rewrites_source_edge_endpoints(self):
        class AliasGraph(Graph):
            async def neighbors(self, value, direction):
                self.requests+=1
                row=work(2 if direction=='references' else 3,refs=[1],doi='https://doi.org/10.1000/same')
                return GraphBatch([row])
        r=await CitationTrackingService(agent=Agent(),graph=AliasGraph()).run('SEED-IV',20,papers=[seed(1)])
        self.assertEqual(len(r.results),1)
        self.assertEqual([(p.from_id,p.to_id) for p in r.results[0].paths],[('W1','W2')])
        self.assertTrue(r.warnings)

    async def test_topic_multimodal_constraint_cannot_be_satisfied_by_unimodal_metadata(self):
        class UnimodalGraph(Graph):
            async def neighbors(self,value,direction):
                self.requests+=1
                row=work(2,[1],title='SEED-IV EEG emotion recognition')
                row['abstract_inverted_index']={'EEG':[0]}
                return GraphBatch([row])
        r=await CitationTrackingService(agent=Agent(),graph=UnimodalGraph()).run('多模态 SEED-IV',20,papers=[seed(1)])
        self.assertEqual(r.results[0].relevance,'uncertain')

    async def test_both_directions_deduplicate_and_keep_real_paths_without_recursing(self):
        graph=Graph(); agent=Agent()
        r=await CitationTrackingService(agent=agent,graph=graph).run('SEED-IV',20,papers=[seed(1)])
        self.assertEqual(r.report_type,'citation_report')
        self.assertEqual(len(r.results),2)
        self.assertEqual(len(graph.calls),2)
        self.assertEqual(agent.calls,2)
        for item in r.results:
            self.assertEqual({p.direction for p in item.paths},{'references','citations'})
            self.assertEqual({p.seed_id for p in item.paths},{'W1'})
            self.assertIn(('W1',item.paper.paper_id),[(p.from_id,p.to_id) for p in item.paths])
            self.assertIn((item.paper.paper_id,'W1'),[(p.from_id,p.to_id) for p in item.paths])
        self.assertEqual(r.depth,1)

    async def test_partial_failure_preserves_other_direction_and_all_failure_is_error(self):
        r=await CitationTrackingService(agent=Agent(),graph=Graph(fail='citations')).run('SEED-IV',10,papers=[seed(1)])
        self.assertEqual(len(r.results),2)
        self.assertTrue(r.warnings)
        with self.assertRaises(PublicResearchError):
            await CitationTrackingService(agent=Agent(),graph=Graph(fail='all')).run('SEED-IV',10,papers=[seed(1)])

    async def test_fabricated_evidence_is_removed_and_relevance_downgraded(self):
        r=await CitationTrackingService(agent=Agent(True),graph=Graph()).run('SEED-IV',1,papers=[seed(1)])
        self.assertEqual(len(r.results),1)
        self.assertEqual(r.results[0].evidence,[])
        self.assertEqual(r.results[0].relevance,'uncertain')
        self.assertNotIn('invented',r.model_dump_json())

    async def test_empty_and_limits_and_source_timeout(self):
        graph=Graph(count=1)
        r=await CitationTrackingService(agent=Agent(),graph=graph).run('SEED-IV',10,papers=[seed(1)])
        self.assertEqual(r.results,[])
        self.assertTrue(r.gaps)
        for papers,direction,limit in [([seed(i) for i in range(1,7)],'both',10),([seed(1)],'bad',10),([seed(1)],'both',21)]:
            with self.assertRaises((ValueError,PublicResearchError)):
                await CitationTrackingService(agent=Agent(),graph=Graph()).run('SEED-IV',limit,papers=papers,direction=direction)

    async def test_sixty_candidate_budget_and_duplicate_seeds_are_not_returned(self):
        r=await CitationTrackingService(agent=Agent(),graph=Graph(count=100)).run('SEED-IV',20,papers=[seed(i) for i in range(1,6)])
        self.assertLessEqual(len(r.results),20)
        self.assertTrue(all(x.paper.paper_id not in {f'W{i}' for i in range(1,6)} for x in r.results))
        self.assertTrue(r.warnings)


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_origin_identity_and_directed_neighbors(self):
        calls=[]
        def handle(request):
            calls.append(request)
            self.assertEqual(request.url.host,'api.openalex.org')
            if request.url.path.endswith('/W1'): return httpx.Response(200,json=work(1,[2]))
            if request.url.params.get('filter','').startswith('cites:'):
                return httpx.Response(200,json={'results':[work(3,[1]),work(99)],'meta':{'count':2}})
            return httpx.Response(200,json={'results':[work(2),work(99)],'meta':{'count':2}})
        g=OpenAlexGraphClient(transport=httpx.MockTransport(handle))
        s=await g.resolve(seed(1))
        outgoing=await g.neighbors(s,'references'); incoming=await g.neighbors(s,'citations')
        self.assertEqual([w['id'] for w in outgoing.works],['https://openalex.org/W2'])
        self.assertEqual([w['id'] for w in incoming.works],['https://openalex.org/W3'])
        self.assertTrue(outgoing.warnings and incoming.warnings)
        self.assertEqual(len(calls),3)

    async def test_mismatching_doi_and_unsafe_identity_never_resolve(self):
        calls=[]
        def handle(request):
            calls.append(request)
            return httpx.Response(200,json=work(8,doi='https://doi.org/10.1000/wrong'))
        g=OpenAlexGraphClient(transport=httpx.MockTransport(handle))
        p=seed(1).model_copy(update={'source':'crossref','paper_id':'10.1000/right','page_url':'https://doi.org/10.1000/right'})
        with self.assertRaises(GraphError): await g.resolve(p)
        self.assertEqual(len(calls),1)
        p=p.model_copy(update={'paper_id':'bad','page_url':'https://127.0.0.1/private'})
        with self.assertRaises(GraphError): await g.resolve(p)
        self.assertEqual(len(calls),1)

    async def test_request_budget_redirect_rate_limit_and_response_bound(self):
        def handle(request): return httpx.Response(200,json=work(1))
        g=OpenAlexGraphClient(transport=httpx.MockTransport(handle),max_requests=1)
        await g.resolve(seed(1))
        with self.assertRaises(GraphError): await g.resolve(seed(1))
        self.assertEqual(g.requests,1)
        for status in (302,429,503):
            g=OpenAlexGraphClient(transport=httpx.MockTransport(lambda req:httpx.Response(status,headers={'Location':'https://127.0.0.1'})))
            with self.assertRaises(GraphError): await g.resolve(seed(1))
        g=OpenAlexGraphClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b' '* (4*1024*1024+1))))
        with self.assertRaises(GraphError): await g.resolve(seed(1))

    async def test_reference_cap_is_explicit(self):
        def handle(req):
            if req.url.path.endswith('/W1'): return httpx.Response(200,json=work(1,range(2,100)))
            return httpx.Response(200,json={'results':[work(2)],'meta':{'count':98}})
        g=OpenAlexGraphClient(transport=httpx.MockTransport(handle))
        batch=await g.neighbors(await g.resolve(seed(1)),'references')
        self.assertTrue(batch.truncated)

    async def test_arxiv_exact_doi_mapping_and_missing_reference_metadata(self):
        calls=[]
        def handle(req):
            calls.append(req)
            return httpx.Response(200,json={'results':[work(9,doi='https://doi.org/10.48550/arXiv.2601.00001') ]})
        g=OpenAlexGraphClient(transport=httpx.MockTransport(handle))
        p=seed(1).model_copy(update={'source':'arxiv','paper_id':'2601.00001v2','page_url':'https://arxiv.org/abs/2601.00001v2'})
        value=await g.resolve(p)
        self.assertEqual(value['id'],'https://openalex.org/W9')
        self.assertIn('10.48550/arxiv.2601.00001',calls[0].url.params['filter'])
        value.pop('referenced_works')
        with self.assertRaises(GraphError): await g.neighbors(value,'references')
