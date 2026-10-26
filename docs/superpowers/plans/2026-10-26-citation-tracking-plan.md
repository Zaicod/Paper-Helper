# Citation Tracking Implementation Plan

**Goal:** Implement the approved one-hop bidirectional citation discovery task in PaperFlow.
**Architecture:** Owner-validated Java task snapshot -> authenticated Python worker -> fixed-origin OpenAlex graph adapter -> model screening -> citation_report -> Vue results and collection save.
**Execution:** Independent Java and Vue tasks, Python owned by root, then review and integration. User already approved implementation; no additional approval gate.

## Shared contracts

Task type `citation_trace`; optional `citation_direction` defaults `both`, allowed `references|citations|both`. Task has 1-5 selected owned papers, live/personal model, rag none. Result limit 1-20 independent of seed count. Blank topic uses `围绕所选论文的研究主题，追踪相关参考文献及后续研究，并说明相关性与发现路径。`.

Report `report_type:citation_report,topic,generated_at,direction,seeds:Paper[],results:[{candidate_id,paper,relevance:match|uncertain|background,reason,evidence:string[],paths:[{seed_id,seed_title,direction:references|citations,from_id,to_id}]}],warnings:string[],gaps:string[],source_requests:int,depth:1`. Seeds preserve submitted snapshots. Papers have existing PaperInput shape. Max 60 candidates, 10 paths each, result20, warnings30, gaps10. Every edge represents citing from_id -> cited to_id, OpenAlex W identifiers. paths seed_id identifies submitted seed paper_id. No runtime secrets persisted.

## Global bounds

5 seeds, 1 hop, each seed/direction20 neighbors, 60 candidates, source20 requests, model2 calls (plan/review), total120 seconds, per-request8 seconds, response4MiB, fixed https://api.openalex.org/works origin and no redirects. Partial upstream failures preserve successful directions; all failed raises a public error. Model evidence must be verbatim title/abstract. Source relationships do not mean scientific support. No PDF or code execution. No publishing or user-service restart.

## Task 1 Python

- [x] Red tests in tests/test_citation_tracking.py for exact ID/DOI mapping, directed edges, self/seed removal, cycles, duplicate paths, bounds and partial/all failure.
- [x] Add paper_agent/core/citation_agent.py typed report; paper_agent/tools/citation_graph.py adapter; paper_agent/services/citation_tracking.py service. Reuse SearchAgent.plan/review with code-validated evidence.
- [x] Worker TaskInput accepts direction only for citation tasks; live/personal, namespace and 1-5 seed checks. Branch executes injected factory, validates report topic/limit/seeds/direction. Empty direction omitted for legacy task hashes.
- [x] Worker endpoint tests prove auth, task execution and invalid inputs. Run targeted then full unittest discovery.

## Task 2 Java

- [x] Add citation_direction to ResearchTaskDTO while preserving existing constructors; taskType validation adds citation_trace; normalizes citation default only, unrelated tasks reject direction.
- [x] ResearchTaskServiceImpl checks owned seeds count1-5, personal default live/rag none, persists direction and selection. Result limit never overwritten by seed count. Reuse search quota for both expensive discovery types. Original retry copies direction/selection and retains seed snapshot. No prepared PDF requirement.
- [x] Red/green tests for payload/defaults/direction/count/owner/idempotency/retry and old DTO calls. Run Maven tests/package.

## Task 3 Vue

- [x] Extend TaskInput/TaskSummary/report union with shared contracts above.
- [x] CollectionDetail selected seed action routes to existing creation form task_type=citation_trace. Creation form supports direction, up to5 selected papers, no PDF gate, live/rag none/personal defaults, independent result limit and citation default topic.
- [x] TaskDetail uses CitationReportView showing paths, disclaimers and gaps; reuse safe links and collection saving. Label tasks as 引用追踪. Route/account/unmount guards match current conventions.
- [x] Add red tests for form submission/bounds and report direction/path rendering plus saves; run Vitest and vue-tsc/Vite build.

## Task 4 Review and verification

- [x] Review cross-layer field names, bound enforcement, outgoing/incoming direction, model provenance and account isolation. Fix material findings with regression tests.
- [x] Controlled Python/Java or browser integration, no personal API calls. Record sources unavailable vs no neighbors accurately.
- [x] Write docs/citation-tracking-learning.md and README link; update checklist and verification counts. Existing repository root has no .git, do not initialize or publish.


## Final verification (2026-10-26)

- Python: full unittest discovery includes 188 tests; final output recorded in verification-logs/citation-python-full.log. Dedicated regressions cover directed edges, fixed-origin API, exact ID/DOI mapping, alias conflicts, one-hop/no recursion, candidate/request bounds, timeout/partial failure, fabricated evidence, seed planning context, worker auth/snapshot/replay/secret cleanup.
- Java: 138 tests total, 132 passed, 6 optional Redis skips; package BUILD SUCCESS. verification-logs/citation-java-final-package.log. Reviewer found old OpenAlex/arXiv seed compatibility and it was corrected red/green.
- Vue: 99 tests across 19 files passed; vue-tsc and Vite build passed. verification-logs/citation-vue-full.log and citation-vue-build.log. Controlled desktop/mobile browser flow passed: citation-vue-browser.log.
- Packaged Java -> Python real graph adapter with controlled HTTP/model: both directions, independent result count, default topic, idempotency, owner isolation, OpenAlex/arXiv seed and result saving passed. verification-logs/citation-bridge.log; .tools/citation-bridge-summary.json. No real external/model calls or source recall claim.
- Independent code review: no remaining material findings after compatibility fix and final seed context prompt review.
- User guide docs/citation-tracking-learning.md linked from README. No Git publish, original-service restart or changes to synced sources.
