# Search and Study Report Implementation Plan

> Execute inline using executing-plans and test-driven-development. This workspace has no Git repository; do not initialize one or commit.

**Goal:** Add source sorting/pagination and evidence-grounded Agent study reports with authenticated DOCX export.

**Architecture:** Vue owns search/selection/preview. Java Controller → Service → ServiceImpl → MyBatis retains ownership, snapshots and tasks. Python owns provider APIs, PDF evidence, Agent reasoning and deterministic DOCX rendering.

**Tech Stack:** Vue 3/TypeScript, Spring Boot/MyBatis, FastAPI/Pydantic, Agents SDK, pypdf, python-docx.

## Constraints

- Preserve existing research/search callers and stored tasks.
- Citation sorting requires OpenAlex; pin paging to the actual provider.
- PDF failure is visible and never silently replaced by abstract evidence.
- Reports contain overview and all four requested sections per paper; never invent experiments or user experiences.
- Only owners can submit selected collection papers or download snapshots.

## Task 1: Provider pages and worker endpoint

Files: paper_agent/tools/search.py; services/paper_search.py; interfaces/worker.py; tests/test_search_pages.py.

- [x] Add failing HTTP-boundary tests asserting arXiv start/sort and OpenAlex page/sort/total/unknown citations. Assert a second page does not repeat page one and no-abstract works remain visible.
- [x] Run `.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_search_pages.py -v`, observe missing page API.
- [x] Introduce `search_page(topic, limit, page=1, sort='relevance') -> ProviderPage` alongside unchanged `search`. Add `search_paper_page(query, source, limit, page, sort, factory=None)` and worker optional page/sort parameters; old requests call old function.
- [x] Re-run page tests and existing paper search tests.

## Task 2: Study Agent and Word serializer

Files: core/study.py; services/study.py; agents/study.py; interfaces/study_document.py; tools/study_pdf.py; tests/test_study_report.py; pyproject.toml.

- [x] Add failing tests for strict PDF failure, one/multiple paper reports, evidence/identity validation and DOCX structure.
- [x] Run focused unittest; observe absent modules/contracts.
- [x] Implement `StudyService.run(topic, papers, on_event, notes, learning_goal)` returning `StudyReport`; team consumes bounded cited evidence and returns per-paper structured analysis and multi-paper synthesis. Inject loader/team for deterministic tests.
- [x] Add public HTTPS PDF fetching with DNS/redirect checks, streaming size/time/page limits and no abstract fallback. Generate headings/styles with python-docx using report snapshots only.
- [x] Re-run tests; render representative documents and inspect all pages using bundled document runtime if available.

## Task 3: Durable tasks and Java bridge

Files: worker.py; Java ResearchTaskDTO, ResearchTaskServiceImpl, ResearchController, ResearchTaskVO/SummaryVO, WorkerClient; tests/test_worker.py; Java research/search tests.

- [x] Add red tests for study task submission, bad ownership, snapshot notes, study-specific completed contract and authenticated snapshot export.
- [x] Add optional task_type/learning_goal/reflection fields with research defaults; study submissions require collection selection and live model. Preserve old DTO constructors for existing tests.
- [x] Dispatch study work via existing worker queue; retain validated structured report; expose export from supplied saved snapshot to survive worker history loss.
- [x] Add Java search overload page/sort and response contract validation, preserve old signature. Download interface checks owned completed study task, serializes saved JSON through authenticated internal worker exporter, returns DOCX MIME and fixed filename.
- [x] Run Python full suite and Java package with scripts/dev.ps1.

## Task 4: Vue flows

Files: types.ts; api/index.ts; views/PaperSearchView.vue, CollectionDetailView.vue, ResearchNewView.vue, TaskDetailView.vue, ResearchView.vue; components/StudyReportView.vue; tests/unit.

- [x] Write red tests for page 2 source pinning, sort reset and study selection/preview/download.
- [x] Add search selectors/page navigation/citation display; selecting a new query resets page.
- [x] Add collection study links with selected IDs; task form has study fields and PDF behavior; existing research form remains available.
- [x] Render study report safely through Vue interpolation; owned GET document link downloads through Java.
- [x] Run `npm test` and `npm run build`.

## Task 5: Integration and review

Files: scripts test-only fixtures/browser smoke; docs/paper-search-learning.md; docs/study-report-learning.md.

- [x] Exercise three real local services against explicitly controlled provider/model boundaries; verify pagination, single/multi selection, report preview/download and cross-user denial.
- [x] Check representative DOCX XML, Chinese styles and browser downloads; real public PDF extraction checked independently.
- [ ] Word page rendering: unavailable bundled renderer/runtime loader in this host; recorded explicitly in learning guide. Live-model report quality not verified.
- [x] Request read-only code review, address substantive findings, rerun affected tests.
- [x] Update startup/learning documentation and report verification evidence.

## Verification record

Python 93 tests pass; Java 44 tests and package pass; Vue 29 tests and production build pass. Controlled three-service browser integration covers source paging/sorting, single/multi study report, document downloads, foreign user denial and PDF failure. DOCX ZIP/XML contains 1 and 2 complete per-paper sections respectively. Reviewer findings (arXiv HTTPS, note limits, payload admission, page-one pinning) resolved and checked. No Git operations were performed.
