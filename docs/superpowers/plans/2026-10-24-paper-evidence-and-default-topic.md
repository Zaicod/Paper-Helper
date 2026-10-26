# Paper Evidence Preparation and Default Topic Implementation Plan

> **For agentic workers:** Execute with test-driven-development, independent Java/Vue tasks, and read-only review before completion.

**Goal:** Prepare validated private PDF evidence before study-task creation, permit user uploads, support repaired new tasks and meaningful default analysis instructions.

**Architecture:** Java owns authenticated library/document registrations; Python stores immutable namespace-scoped PDFs and extracted chunks behind internal service authentication. Study task payload snapshots prepared document IDs; Python validates namespace and paper fingerprint before loading them. Existing legacy tasks retain their direct-PDF path.

**Tech Stack:** Existing Spring/MyBatis/Flyway, FastAPI/SQLite/files/pypdf, Vue/TypeScript.

## Global constraints

- Approved spec docs/superpowers/specs/2026-10-24-paper-evidence-and-default-topic-design.md.
- No user-service restart, personal model invocation, Git initialization or publishing. sources/ remains read-only.
- Preserve existing 25 MiB/200-page/text safeguards. No plaintext keys in files/logs, no arbitrary local paths or browser-supplied internal URLs.
- Preparation does no model calls. Its network and extraction happen outside Java DB transactions. Worker validates all redirects with the existing public HTTPS/DNS-pinned loader.
- Legacy study tasks without preparation fields still work. New Java study submission requires current ready preparation; original retry preserves document snapshots. Repair creates a fresh record using current owned paper metadata and prepared docs.

## Shared contracts (coordinate Java/Python/Vue)

Browser endpoints:
- GET `/api/library/collections/{collection}/papers/{paper}/document` status.
- POST same path + `/prepare` prepare from existing PDF URL / bounded DOI resolution.
- POST same path with multipart field `file` upload and prepare.
- GET `/api/library/documents/{document_id}/file` private download by authenticated owner.
- POST `/api/research/tasks/{id}/repair` body `{idempotency_key:UUID}` -> new Task; failed/interrupted study only, current owned metadata/documents/current model, preserve original history. UI also offers original retry explicitly.

Document status VO: `{document_id:string|null,status:'not_prepared'|'ready'|'missing'|'blocked'|'unreadable'|'timeout'|'unavailable',message:string,filename:string|null,sha256:string|null,source_kind:'uploaded'|'remote'|null,page_count:number|null,prepared_at:string|null}`. Preparation may return a non-ready status normally; task creation rejects until all selected docs ready. Status lookup for changed metadata returns not_prepared.

Internal worker endpoints (Bearer token always):
- POST `/internal/v1/documents/upload?namespace=java-user:N&filename=...`, raw application/pdf up to25MiB -> `{upload_id:UUID}`. Filename bounded255; never a filesystem path.
- POST `/internal/v1/documents/prepare`, JSON `{namespace:string,paper:WorkerPaper,upload_id?:UUID}` -> Document status VO above. Uploaded blob namespace must match. Server chooses document_id, persists exact paper fingerprint and immutable PDF/chunks. Without upload_id, try paper.pdf_url then DOI/OpenAlex-ID verified OA locations; never blindly reuse HTML as PDF.
- GET `/internal/v1/documents/{uuid}/file?namespace=...` raw application/pdf<=25MiB, namespace match required.
- Persist prepared files under worker ledger sibling `documents/`, identifiers validated UUID, per-file metadata JSON and PDFs; atomic publication, immutable prepared IDs, safe paths.

TaskInput optional new `prepared_documents:dict[paper_id,UUID]` and `library_selection:{collection_id:int,paper_ids:int[]}`. Java includes prepared_documents for all new study tasks, validated at submission. Worker injects a prepared loader into StudyService; downloaded files are already parsed, so loader checks namespace/fingerprint, returns frozen EvidenceChunks with page numbers. Uploaded evidence source_url `/api/library/documents/{document_id}/file`; UI accepts only this exact private path format in addition to existing http(s) links. Existing research/search payloads remain unchanged.

Default text (shared verbatim between Java and Vue):
`请基于所选论文，分析研究背景与解决的问题、核心创新点、模型总体架构及各模块作用、实验设置与主要结果、局限性，以及可改进的方向。对正文未提供的信息明确标注，不补造细节。`

### Task 1 — Python document store and worker integration (root)
- [x] Write red tests for upload/namespace isolation/malformed+scanned PDFs, immutable versions/fingerprints, missing URL diagnosis, bounded OA resolver, HTTP middleware limit and prepared study path.
- [x] Implement `tools/prepared_documents.py` and controlled OA resolver helper; reuse `_fetch_public_pdf`/`_extract_pdf` and preserve failure categories without raw exception details.
- [x] Add authenticated routes and per-route request size bounds; total upload limit25MiB while other routes remain2MiB.
- [x] Extend TaskInput and worker prepared loader injection, preserve old unprepared tasks and credential cleanup. Verify original report paper snapshot unchanged.
- [x] Run targeted then full Python tests.

### Task 2 — Java private document registration and study task rules
- [x] Add migration V5, document entity/mapper/service/controller/VO, library owner checks before+after worker calls. Store local paper metadata hash separate from worker fingerprint; no sharing private attachment on public paper rows.
- [x] Extend WorkerClient for upload/prepare/download with bounded memory/time, internal token and validated typed status. Configure multipart25MiB.
- [x] New study creation requires ready records for exact current metadata and snapshots document IDs/library_selection. Default topic normalization applies selected paper tasks only; blank topic-only/search rejects.
- [x] Original retry copies document/context fields. Add repair service/controller path which revalidates and resolves current owned papers/docs and settings, new idempotent task, retains original. Support legacy snapshots by owner/source/external-ID lookup.
- [x] Red/green Java tests including isolation, stale versions, missing PDF rejected before insert/model dispatch, idempotency, upload/read, current-default model and repair history.

### Task 3 — Vue document preparation and defaults
- [x] Add typed status/API calls and FormData support preserving CSRF/auth/error rules, extended request timeout for preparation.
- [x] Library paper document component provides status, prepare, upload and private download, categorized errors; task form offers same controls for selected papers and blocks study submit until ready.
- [x] Auto default topic for selected papers/study form, preserve manual edits, restore default button, never use generic default text as external search query.
- [x] TaskDetail explains original retry snapshot, offers repair+create action for failed study; private PDF citation links resolve only exact approved path.
- [x] Tests first; run full Vue tests/build and controlled desktop/mobile browser flow.

### Task 4 — Review and integration
- [x] Independently review access boundaries, immutable snapshots, multipart limits, default input handling and no network in DB transactions.
- [x] Real packaged Java -> Python upload/prepare/task/repair on temporary databases with fixed PDFs/model boundary. No real private keys.
- [x] Full relevant suites/builds; inspect counts, record optional Redis skips. Update docs/README and spec state.


## Verification record — 2026-10-24

- Python: 170 tests passed, including a red/green regression proving blank learning goals pass the research topic to the per-paper analyst. `verification-logs/paper-evidence-python-full.log`; red evidence: `default-topic-analyst-red.log`.
- Java: 124 tests total, 118 passed and 6 optional Redis tests skipped; package build successful. `verification-logs/document-java-final-package.log`.
- Vue: full tests/build recorded in `verification-logs/paper-evidence-vue-full.log` and `paper-evidence-vue-build.log`; controlled browser report: `frontend-vue/.tools/paper-evidence-browser/vue-playwright-results.json`.
- Packaged Java/Python integration: passed real upload/extraction, preflight/default topic, immutable versions, failed-task repair, history and owner isolation. `verification-logs/paper-evidence-bridge.log`.
- Independent read-only review: HTTP 403 preparation classification corrected with red/green coverage; no material findings remaining.
- User guide and architecture walkthrough: `docs/paper-evidence-learning.md`, linked from README. No live model calls, verified MMSTG-Net full text, publishing or original-service restarts were claimed.
- Repair presents that current data/settings will be used; a field-by-field before/after comparison is not implemented.
