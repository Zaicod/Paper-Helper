# Failed task retry

Execute with executing-plans and test-driven-development, using independent backend/frontend implementation and review. User requests a retry button on the failed learning report. Existing project has no Git repository.

## Contract and behavior

- Authenticated, CSRF protected POST `/api/research/tasks/{id}/retry`, body `{idempotency_key: UUID}`; return existing Task Result shape, status202 (idempotent replay may also202).
- Original task must belong to current account and be failed/interrupted. Preserve the original record; create new task ID, fresh deadline, empty events/errors/report.
- Clone nonsecret original topic/options/papers/notes/goal/reflection snapshot. Use CURRENT personal default provider/model/source for live execution; never copy stale credentials or credential source. Demo stays offline. Missing personal credentials never fall back silently.
- Revalidate that every snapshot paper still belongs to at least one collection of the authenticated account; missing papers ->400 with guidance to select again. Topic-only tasks have no paper ownership check.
- Derive namespace from current authenticated owner. Store only safe payload, no plaintext keys; normal synchronizer attaches credentials at dispatch.
- Retry request hash tied to original task ID and marker; owner lock + idempotency key ensures a replay returns the same new task. Same key on another task ->409.
- UI shows “重试任务” on failed/interrupted only, disables during submit, retains same idempotency key after ambiguous network failure, navigates to new task. Show personal-settings link and explain current settings/new record. Keep original create-new link.

## Tasks

- [x] Java: red auth/status/idempotency/selected ownership/current model tests; implement RetryTaskDTO/controller/service+mapper ownership query with no migration; tests/package.
- [x] Vue: red retry button/state/payload/error/idempotent replay/navigation tests; typed API and TaskDetailView; full unit suite/build.
- [x] Browser: controlled model/PDF scenario fails missing key, saves personal config, retries same papers/goal into successful new report and DOCX; verify original unchanged.
- [x] Independent review, fresh relevant verification, update learning docs. No actual user model calls or service restarts.

## Verification

- Java full suite: 66 passed and package succeeded (`java-backend/target/retry-final.log`), including 8 retry-specific tests.
- Vue full suite: 67 passed and production build succeeded (`verification-logs/retry-vue-unit.log`, `retry-vue-build.log`).
- Independent review found no important backend issue; same-task query/hash pending-state issue fixed with red/green regression.
- Browser: 1 full real Vue/Java/worker settings-and-study flow passed; failed task retried after changing personal default, new report preserved selected paper and old failed record remained unchanged (`.tools/task-retry-browser.log`, `.tools/model-settings-e2e-smoke.json`). Model/PDF boundaries explicitly controlled; no real model credentials used.
