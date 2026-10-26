# Analysis Search Agent Implementation Plan

> **For agentic workers:** Execute using test-driven-development, with independent Java and Vue implementation tasks and a final code review.

**Goal:** Add an authenticated asynchronous intelligent literature search with planning, real-source retrieval, grounded screening and bounded follow-up.

**Architecture:** Reuse research task storage/synchronization with task_type `search`. Python produces report_type `search_report`. A separate Python SearchAgent plans and reviews; application code controls sources, budgets and candidate identity. Vue adds an intelligent search form and a dedicated result component.

**Tech Stack:** Existing Python/Pydantic/Agents SDK, Spring Boot/MyBatis, Vue/TypeScript/Vitest.

## Constraints

- Approved spec: docs/superpowers/specs/2026-10-24-analysis-search-agent-design.md. No Git repo at project root, no commits or publishing in this task.
- Search: live only, no selected collection/papers, personal default model, rag none. At most 2 active search tasks per owner; same quota for retries; idempotent replay precedes quota/credential checks.
- 120-second execution timeout, at most 2 rounds / 6 source calls / 3 model runs, 60 candidates / 20 returned results. Existing arXiv rate gate remains.
- Do not call actual personal credentials. Fixed model and source tests must identify their controlled boundaries.

## Shared JSON interface

Submit existing POST /api/research/tasks with `{idempotency_key, topic, mode:"live", limit:10, rag:"none", task_type:"search"}`. Task list/detail task_type gains `search`; report union gains `search_report`.

Report fields: `report_type:"search_report"`, `topic:string`, `generated_at:ISO datetime`, `plan:{summary:string,concepts:string[],entities:{name:string,aliases:string[]}[],entity_relation:"any"|"all",constraints:string[],queries:{source:"arxiv"|"openalex"|"crossref",keywords:{text:string,match_mode:"exact"|"fuzzy"}[],purpose:string}[]}`, `results:{candidate_id:string,paper:existing SearchPaper,relevance:"match"|"uncertain"|"background",reason:string,evidence:string[],matched_entities:string[],modality:"multimodal"|"unimodal"|"unknown",provenance:{source:string,query:string}[]}[]`, `searches:{round:1|2,source:string,query:string,count:number,status:"ok"|"empty"|"unavailable"|"timeout"|"rate_limited"}[]`, `warnings:string[]`, `gaps:string[]`, `rounds:1|2`.

`results` may be empty. Only validated actual provider papers populate `paper`. Returned evidence must be a substring of the candidate title or abstract. matched_entities only asserted when aliases are found in candidate metadata; uncertain results explicitly keep missing evidence. No automatic claim of experimental usage.

### Task 1: Python planner, retrieval and review

Files: create core/search_agent.py (contracts), agents/search.py (structured planner/reviewer), services/intelligent_search.py (execution/budgets/validation), tests/test_intelligent_search.py.

- [x] Add failing tests with injected model planner/reviewer and source function for SEED-IV/SEED-VII OR, cross-source dedup, false IDs/evidence, unimodal/unknown distinctions, refinement and limits.
- [x] Run `.venv/Scripts/python.exe -m unittest discover -s tests -p test_intelligent_search.py`; verify red before implementation.
- [x] Implement bounded contracts and task-local model construction; planner.run returns SearchPlan, reviewer.run returns candidate assessments + follow-up queries + gaps. Three model calls max.
- [x] Execute at most four initial source queries then up to two follow-ups, validating all source responses with SearchPaper; preserve canonical paper metadata. De-duplicate by normalized URL/arXiv identity or sufficiently supported metadata.
- [x] Validate candidate IDs, evidence substrings, entity matches and fixed limits; no invented links. Handle partial upstream failure versus legitimate zero results distinctly.
- [x] Extend worker task union and inject intelligent_search_factory in tests; persist typed SearchReport and safe search_failed messages, preserve runtime-key cleanup.

### Task 2: Java lifecycle and contract

Files: ResearchTaskDTO, ResearchTaskServiceImpl, ResearchTaskMapper, WorkerClient, ResearchTaskStoreImpl; focused tests.

- [x] Test task_type search acceptance, live-only/no collections, 2-active quota with owner lock, idempotent replay, retry quota/current model, cross-account isolation, credentials non-persistence.
- [x] Implement using existing task table and namespace. Count active search tasks in mapper with H2/MySQL-compatible JSON-free SQL (select owner active tasks and parse payload in service).
- [x] Add strict bounded search report validation in dedicated client validator; retain other report paths. Reject unknown/malformed report types and unsafe result metadata.
- [x] Preserve search_failed safe error messages by task type in store; test local controlled HTTP contract.
- [x] Run targeted Java suite and report logs. Use JDK C:/Users/20476/.jdks/openjdk-25 and existing .tools/apache-maven-3.9.11/bin/mvn.cmd.

### Task 3: Vue search and results

Files: types.ts, api types if needed, PaperSearchView, SearchReportView (new), TaskDetailView, ResearchView task labels; focused tests.

- [x] Test intelligent search submission, idempotent-key retention after ambiguous errors, settings guidance, rendering plans/traces/grounded evidence/gaps, result collection, correct report discrimination.
- [x] Add separate intelligent search section preserving existing search UI. Submit existing task endpoint then navigate to task detail. Clearly explain personal default model usage and asynchronous progress.
- [x] Render search report distinct from study/research, safe external links, provenance and evidence, ordinary collection-saving API with full existing Paper DTO.
- [x] Match existing visual design and accessible controls; retain current ordinary search pagination and draft behavior.
- [x] Run complete Vue tests and build.

### Task 4: Integration, review and learning

- [x] Run Python full suite, Java full suite/package, Vue full suite/build; inspect exact results including opt-in Redis skips.
- [x] Run controlled worker and browser full flow where feasible; explicitly label all substituted boundaries and do not claim external live-model verification.
- [x] Request independent code review, fix important findings, run checks justified by changes.
- [x] Write docs/intelligent-search-learning.md, README link, update spec/plan state and exact verification record.

## Final verification — 2026-10-24

- Python: 15 new controlled search/worker tests; final full suite 157 passed, no failures (verification-logs/intelligent-search-python-final.log). Initial existing Chroma failure was isolated: its 4-test suite and subsequent complete suite pass; no Chroma production changes.
- Actual Agents SDK strict SearchPlan/SearchReview schemas and agent construction validated without invoking a model.
- Java: 117 total, 111 passed, 6 opt-in Redis integration skips, zero failures/errors, package success (.tools/intelligent-search-java-final-package.log).
- Vue: 83 tests / 15 files, TypeScript and Vite build passed. Chrome controlled E2E passed; screenshots inspected for desktop and mobile, no horizontal overflow.
- Full bridge: final packaged Java plus real worker, SQLite, search control loop and collection database passed. Model and source boundaries were controlled fixtures. Account isolation, request replay, two dataset results and collection save verified (.tools/intelligent-search-bridge-smoke.json and verification-logs/intelligent-search-bridge-final.log). First bridge assertions passed but Windows child-interpreter cleanup failed; helper now terminates only its owned process trees and final run exits successfully.
- Independent review found duplicate entity annotations could bypass all constraints and arXiv DOI/page dedup mismatch. Added red regressions, fixed in Python and Java; reviewer rechecked and reported no remaining material findings.
- No actual personal model calls, user-service restarts, commits or publishing performed. Live model retrieval quality and external API availability remain separate validation.