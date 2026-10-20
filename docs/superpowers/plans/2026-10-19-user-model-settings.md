# Model settings implementation plan

> Execute with executing-plans and test-driven-development using independent bounded implementation tasks and review. No Git repository: no commits or worktrees.

**Goal:** Add authenticated Vue model settings that actually supply per-account credentials to Python report generation.

**Architecture:** Existing Vue styling and Java Controller → Service/interface/implementation → MyBatis. Java AES-GCM encrypted credentials; dispatch-only plaintext; worker in-memory task-local secrets excluded from hashes and SQLite. Keep server environment compatibility for tasks without personal settings.

**Tech stack:** Vue3/TypeScript, Spring Boot/MyBatis/Flyway, Java AES-GCM, Pydantic SecretStr and per-call AsyncOpenAI clients.

## Shared contracts

- GET `/api/model-settings`: `{default_provider: 'qwen'|'openai'|null, providers:[{provider,model,configured,key_hint}]}` inside existing Result wrapper. Always two providers. No raw secret response.
- PUT `/api/model-settings/{provider}`: `{model,api_key?:string|null}`. Empty/absent key preserves existing; first save requires a key. Provider limited qwen/openai; model nonblank max128, key trimmed max4096 no control characters.
- PUT `/api/model-settings/default`: `{provider:'qwen'|'openai'|null}`. Null selects environment compatibility; setting a provider requires saved usable key.
- DELETE `/api/model-settings/{provider}/key`: clears key, keeps provider settings and explicit personal marker; queued personal tasks must fail, never fall back to environment.
- POST `/api/model-settings/{provider}/test`: tests saved provider/model, returns `{success:boolean,message:string}`. Timeout ≤20s; frontend25s. Uses authenticated worker endpoint.
- Worker TaskInput optional `runtime_credentials:{provider,api_key}`. `api_key` SecretStr, redacted repr, excluded from hash/payload persistence. WorkerOptions `credential_source:'server'|'personal'` defaults server. Personal must match selected provider, missing secret fails; no environment fallback.
- Worker POST `/internal/v1/models/test`: `{provider,model,api_key}`; same service-token auth and bounded body, no persistence. Returns safe success/message; no raw provider exceptions. Small real completion, ≤15sec, ≤16 output tokens, SDK retries0.
- Java durable payload holds only resolved provider/model/credential_source. Dispatch attaches freshly decrypted key. Personal default/model apply to live tasks; demo remains offline. Explicit provider/model override defaults.

## Task1 Java settings and dispatch

Files: new ModelSettings controller/DTO/VO/entity/mapper/service/impl + encryption helper + Flyway migration, existing ResearchTaskServiceImpl/ResearchSynchronizer/WorkerClient/ResearchTaskDTO.

- [x] Add failing integration tests for save/read masked, empty preserve, deletion/default, two accounts, ciphertext and master-key reuse/missing-file errors.
- [x] Implement AES-GCM master-key file under ignored data directory, atomic creation and owner-only permissions when available; never silently replace missing key for existing ciphertext.
- [x] Implement authenticated/CSRF settings CRUD and saved connection test, ordinary three-layer architecture.
- [x] Add red dispatch tests: task payload contains no plaintext, per-account provider/model defaults, dispatch-only credentials, deleted key fails queued personal tasks, old/demo paths compatible.
- [x] Run Java tests/package and inspect counts/logs. Do not log secrets.

## Task2 Python runtime credentials

Files: new services/model_runtime.py, worker.py, ResearchService/StudyService + options; tests/test_runtime_credentials.py.

- [x] Red tests for credentials excluded from SQLite/hash, concurrent distinct keys, duplicate retry cannot replace runtime key, cleanup, strict personal source and legacy compatibility.
- [x] Add task-local SecretStr runtime dependency carried only in memory and explicitly excluded from option dumps; remove on completion/failure/shutdown.
- [x] Build per-client Qwen/OpenAI Agent models, no environment/global API key mutation. Disable model tracing for personal calls.
- [x] Add service-auth saved-configuration probe, bounded timeout/output/retries, safe error categories and injectable remote boundary for tests.
- [x] Run Python full regression and dependency check.

## Task3 Vue page and defaults

Files: new ModelSettingsView/tests, router/navigation, api/types, ResearchNewView tests.

- [x] Red tests for loading masked configuration, password-only input, save clearing raw key, independent delete/default/test actions and errors.
- [x] Build responsive settings page matching existing project tokens, labeled controls, save/test/delete statuses and default-provider action. Never store secrets in browser persistence.
- [x] Load defaults into new study/research, allow explicit override without asynchronous reset of user edits. Add settings link to missing configuration guidance.
- [x] Run Vue tests and production build.

## Task4 integration, review, docs

- [x] Run isolated real Vue/Java/Python browser settings save/refresh/test/default/task flow with controlled remote model boundary; no user's credentials accessed.
- [x] Independently review account scoping, secret storage/delivery/idempotency/cleanup and failure paths; fix important findings.
- [x] Verify existing search/collection/report/Word flows, write usage and master-key backup notes. Report actual external-model validation limits.
