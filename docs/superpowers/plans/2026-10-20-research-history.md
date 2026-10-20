# Research history implementation plan

Goal: Implement the approved research-history design with three categories, topic search and ten records per page.

Status: Completed 2026-10-20. Java 70 tests passed, Vue 77 tests passed, Vue production build passed. Browser fixture checks verified category switching, 10-row pages, detail return, search, reload restoration and desktop/mobile layout. Independent read-only code review found no blocking issues. Browser checks used fixture API data; backend behavior was verified separately with MockMvc and H2. Actual MySQL was not connected.

Architecture: Extend the existing Controller, Service interface/implementation and MyBatis mapper. Vue stores category, keyword and page in route query and requests only the matching server page. No Python changes or schema migration.

Constraints: Preserve current-user isolation, old unfiltered API calls, existing records and task-detail/retry behavior. Do not restart user services. This directory has no Git repository; no commit or worktree operations.

## 1. Backend filtering
- [x] Add ResearchHistoryApiTest using MockMvc and database fixtures: category coverage, ten-record pagination, exact totals, Chinese/case-insensitive/literal wildcard search, user isolation and invalid parameters.
- [x] Run `.tools/apache-maven-3.9.11/bin/mvn.cmd -f java-backend/pom.xml -Dtest=ResearchHistoryApiTest test`, observe missing-filter failures.
- [x] Extend service list with category/keyword, retain three-argument overload, validate category and keyword length, escape LIKE wildcard characters; share SQL conditions for list and count in ResearchTaskMapper. Controller accepts optional category/keyword and defaults size to 10.
- [x] Rerun backend tests.

## 2. Vue lists
- [x] Add mounted ResearchView tests for navigation, submitted search, page reset, URL restoration, race handling, refresh and error states; add API query encoding test.
- [x] Run `npm test -- tests/unit/research-history.test.ts tests/unit/research-history-api.test.ts`, observe missing-feature failures.
- [x] Extend tasks.list(page=0,size=10,category?,keyword=''); add TaskCategory type. Replace ResearchView with three accessible tabs, search form, refresh, contextual empty states and pagination. Use route query as source of truth, request generation guard and clear previous results while loading.
- [x] Run frontend tests and `npm run build`.

## 3. Verification
- [x] Run all Java and Vue unit tests, verify production Vue build.
- [x] Review changed files for SQL binding, duplicate/missing states, search totals, page boundaries and old-result races; record results in learning documentation.
