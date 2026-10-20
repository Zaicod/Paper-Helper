# Chroma Paper RAG Implementation Plan

> Execute with executing-plans and test-driven-development, using independent implementation tasks and review checkpoints. Workspace has no Git repository; no commits/worktrees.

**Goal:** Persist real multilingual paper embeddings in local Chroma and retrieve scoped evidence for research/study reports.

**Architecture:** Python owns lazy CPU embedder, Chroma storage and RAG orchestration. Java attaches trusted per-account index namespace. Vue contracts and business tables remain compatible.

**Tech Stack:** Chroma PersistentClient, CPU ONNX multilingual E5, tokenizers, Hugging Face model cache, existing FastAPI/Pydantic and Spring Boot/MyBatis.

## Constraints

- Existing demo uses in-memory hashing only; live defaults to Chroma and real local semantic embeddings.
- Never mix model identities/dimensions, account namespaces, selected papers or revisions.
- Persist chunks/pages/source URLs and vectors; actual Agent contexts must come from stored retrieval.
- PDF-only learning reports never silently use abstracts. No model/PDF download at ordinary service startup.
- Ingestion completion markers published only after all records persist; old JSON indexes remain untouched.
- Model cache/download failure is explicit; no fake fallback to hashing. No secrets in vector metadata.

## Task1 compatibility and local embedder

Files: tools/local_embeddings.py; scripts/prepare_embeddings.py; pyproject.toml; tests/test_local_embeddings.py.

- [x] Verify Windows/Python wheels with pip dry run, install required CPU dependencies, read model card/files and pin model revision.
- [x] Red tests for query/document prefixes, mean pooling+mask/normalization, lazy loading, batch behavior and safe errors with injected session/tokenizer.
- [x] Implement LocalMultilingualEmbedder.embed(texts) and embed_query(texts), stable embedding_id/dimensions, lazy singleton loading off event loop.
- [x] Prepare actual model using hf CLI/helper, run Chinese+English semantic smoke and record evidence. No synthetic model claim.

## Task2 Chroma persistent index

Files: tools/chroma_index.py; tests/test_chroma_index.py.

- [x] Red tests against real temporary PersistentClient for write/reopen, duplicate upsert, account/paper/model/version isolation and failed-ingestion invisibility.
- [x] Implement async load_paper(paper,source_mode,recipe)->bool, replace_paper(paper,chunks,source_mode,recipe), search(query,top_k,paper_id), source_mode_for(paper_id), with active selected bindings.
- [x] Persist manifests separately from chunk records; source/document/content hashes and count define a complete reusable revision. Bound batches and validate finite nonzero dimensions.
- [x] Reopen in another process and verify vectors/query still work; failed partial writes remain unbound.

## Task3 research and study integration

Files: services/research.py; services/study.py; tools/rag.py; services/vector_store.py; tests/test_chroma_workflows.py; existing tests injection updates.

- [x] Red tests that Agent receives Chroma-selected evidence, cache avoids repeated loader/document embedding, cache changes on paper metadata/PDF/model recipe, strict PDF failure remains visible.
- [x] Factor shared indexed evidence orchestration; replace StudyService keyword scoring with semantic retrieval for background/method/results followed by ContextBuilder.
- [x] Inject real Chroma store and local model for live; preserve in-memory/demo/controlled fixtures through explicit injection. Extend ResearchOptions with trusted namespace/rebuild controls, optional Chroma directory configuration.
- [x] Add backend/CLI rebuild entry, no additional UI required; document cache semantics for changed remote contents at same URL.

## Task4 namespace bridge

Files: worker.py; Java ResearchTaskServiceImpl; tests/test_worker.py; Java ResearchApiTest.

- [x] Red tests for namespace persistence/derivation and non-user-selectable scope. Java builds account namespace after ownership checks; client body cannot override it.
- [x] Add optional trusted internal index_namespace field; missing legacy namespace derives from task UUID. Merge it into ResearchOptions, never change existing injectable factory signatures.
- [x] Keep existing queued/persistent task contracts and stage enums; no auth-free index query endpoint.
- [x] Run Python full suite, Java tests/package and relevant browser smoke.

## Task5 verification and learning docs

Files: docs/chroma-rag-learning.md; README.md; scripts/chroma_smoke.py.

- [x] Real-model+real-Chroma smoke covers Chinese/English retrieval and process restart, with repeat-index reuse and selected paper scope.
- [x] Controlled three-service browser report flow verifies compatibility; label model fixture boundaries.
- [x] Read-only review; fix substantive findings and rerun affected checks.
- [x] Record installation/startup/storage directory/rebuild commands, model download requirement and any unverified limits. Do not claim live model report quality from fixture tests.

## Verification record — 2026-10-19

- Python: 127 tests passed (`.tools/chroma-python-final.log`); dependencies `pip check` passed.
- Java: 49 tests and package passed (`.tools/chroma-namespace-java-final.log`).
- Vue: 41 tests and production build passed (`.tools/chroma-vue-tests.log`, `.tools/chroma-vue-build.log`).
- Real ONNX E5: default cache works offline, multilingual retrieval and token-aware full-text splitting passed (`.tools/local-embedding-default-live.json`).
- Real Chroma + E5: writer process exited; new reader retrieved scoped evidence without re-embedding documents (`.tools/chroma-live-smoke.json`).
- Real StudyService storage path: two reports with real vectors/Chroma reused one controlled PDF load; generation team controlled (`.tools/study-chroma-live-smoke.json`).
- Review fixed legacy Web namespace spoofing, distinguished PDF/index failures, exposed trusted rebuild, preserved safe model errors and historical evidence snapshots. Same-URL rebuild leaves old report evidence unchanged.
- Fresh browser regression after snapshot fields: 3/3 passed (`.tools/chroma-paper-search-snapshots-smoke.log`), including Java-persisted report and Word download.
- Browser uses controlled upstream, PDF and generation fixtures; it does not establish external source availability or LLM report quality.
