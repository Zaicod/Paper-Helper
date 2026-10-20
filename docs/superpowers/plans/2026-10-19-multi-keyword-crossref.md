# Multi-keyword and Crossref Implementation Plan

> Execute inline using executing-plans and test-driven-development, with independent implementation tasks and review checkpoints. No Git repository exists; do not create one.

**Goal:** Add removable per-keyword exact/broad modes and an honestly labelled Crossref citation-search fallback.

**Architecture:** Vue owns keyword selection; Java validates DTOs and forwards structured JSON; Python compiles source-specific expressions. Existing single-query and report APIs remain compatible.

**Constraints:** Maximum10 keywords, total500 UTF-16 units; trim/deduplicate ignoring case; exact means contiguous phrase, broad means ordinary term search; default AND for arXiv/OpenAlex. Crossref supports only broad relevance queries, no promise of Boolean AND/phrase semantics; disable exact rather than fake it. Display Crossref-only citation coverage and missing metadata explicitly. Citation auto fallback only when all supplied keywords are broad. No silent search-condition changes across pages.

## Task1 Python contracts and providers

Files: core/search_query.py; tools/search_pages.py; tools/crossref.py; services/paper_search.py; interfaces/worker.py; tests/test_keyword_search.py.

- [x] Add failing tests for per-term exact/broad compilation, operator escaping, bad/duplicate/oversized inputs, worker auth/validation, legacy calls and structured response echo.
- [x] Run `.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_keyword_search.py -v`; observe missing contracts, then implement.
- [x] Add Crossref metadata and source-sort tests at HTTP boundary, including citation fallback after OpenAlex429, missing abstracts/PDFs and explicit exact rejection.
- [x] Implement CrossrefSearchClient.search_page and keyword-aware provider page methods, preserving legacy methods. Keep source-pinned later-page validation.
- [x] Run focused and full Python unittest suite.

## Task2 Java bridge

Files: dto/SearchKeywordDTO.java; PaperSearchController; PaperSearchService/Impl; WorkerClient search overload; PaperSearchVO; PaperSearchApiTest.

- [x] Red tests: structured query JSON forwarded encoded, invalid mode/duplicates/limits400, Crossref source accepted and counts preserved, exactCrossref400, oldAPI unchanged.
- [x] Add optional keywords query parameter parsed as List<SearchKeywordDTO>, validate before HTTP; send JSON only when supplied, never treat user text as raw source query operators.
- [x] Verify returned keywords match normalized request; permit thirdsource in identity/warning validation; safe local source labels/messages; echo capabilities in notices.
- [x] Run Java package using java-backend/scripts/dev.ps1; no concurrent Maven.

## Task3 Vue keyword editor

Files: PaperSearchView.vue; types.ts; api/index.ts; tests/unit/papers.test.ts.

- [x] Red tests: add/delete/clear, per-keyword mode badges, duplicate/cap handling, IMEEnter, pending input included, query changes invalidate paging, conditions preserved on navigation.
- [x] Add list with accessible remove buttons, exact/broad selector and explicit add; use composition/key guards; list state included in filter identity.
- [x] Add Crossref source, limitation notice, exact unsupported handling; citation auto can fallback only if no exact requirements.
- [x] Run npm test and npm run build.

## Task4 integration/docs/review

Files: scripts/paper_search_fixture.py; tests/e2e/paper-search.spec.ts; docs/paper-search-learning.md; docs/study-report-learning.md.

- [x] Controlled three-service browser coverage for mixedkeywords, removal, modes, paging, Crossref fallback, citation display and save; existing reports regression preserved.
- [x] Real-source probe records currentOpenAlex429/SemanticScholar429/Crossref200 separately from fixtures.
- [x] Read-only review and fix substantive findings; repeat affected verification. Record final testcounts and current scope.

## Verification record

Python103tests, Java47tests+package, Vue36tests+productionbuild all passed. Three controlled-source browser scenarios passed, covering mixed modes, deletion, fallback, actualTomcat500Chinese keyword request, paging, library ownership and study Word exports. Desktop/mobile keyword screenshots inspected. Crossref live adapter request passed; OpenAlex and SemanticScholar live probes returned429. Review URLduplication finding fixed by sending structured terms only, with server-derived displayquery. No remaining substantive review findings.
