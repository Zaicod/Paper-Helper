# Task Scheduling Reliability Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task in this session. Request an independent code review after implementation.

**Goal:** Allow other synchronization requests to progress while one request is slow, with bounded concurrency and no overlapping dispatch of one task.

**Architecture:** ResearchSynchronizer owns a fixed-size executor with a SynchronousQueue and a concurrent set of admitted task IDs. tick submits available work and returns a CompletableFuture for that batch; the scheduler ignores the future, while deterministic callers may await it. Each work item retains the existing short-transaction store and WorkerClient behavior.

**Tech Stack:** Java 21, Spring Boot, JUnit 5, Mockito, AssertJ, existing Maven setup.

## Global constraints

- Approved design: docs/superpowers/specs/2026-10-24-task-scheduling-reliability-design.md.
- One Java instance; no Python, schema, public API or frontend changes.
- Default concurrency 4, range 1–16, no executor backlog.
- Close stops admission, interrupts HTTP waits, awaits termination at most 10 seconds.
- No credential or payload logging. No real model calls or daily-service restart.
- Directory has no Git repository: preserve local files, no Git initialization or commits.

### Task 1: Concurrent admission and lifecycle

Files: modify java-backend/src/main/java/cn/paperflow/task/ResearchSynchronizer.java; create java-backend/src/test/java/cn/paperflow/research/ResearchSynchronizerTest.java.

- [x] Write a latch-controlled test blocking one WorkerClient request and requiring a second task's store.apply before releasing the first. Invoke tick from an independent test executor so serial behavior fails at the observable completion assertion rather than hanging.
- [x] Run `mvn -Dtest=ResearchSynchronizerTest test`, verify failure from blocked fast-task completion.
- [x] Change `public synchronized void tick()` to `public synchronized CompletableFuture<Void> tick()`. Atomically reserve task ID, enforce `inFlight.size() < concurrency`, execute one Runnable per admitted task; use `CompletableFuture.allOf(...)` for the batch completion.
- [x] Wrap the existing dispatch/recovery logic in a per-task method. Release the ID in finally before completing the future. Catch RuntimeException by safe exception type, attempt worker_unavailable recording, isolate a secondary storage failure.
- [x] Add `@PreDestroy public void close()` with synchronized admission shutdown and shutdownNow, then await termination outside the admission monitor. Preserve InterruptedException's flag.
- [x] Add tests for capacity, overlap, completion/error slot release, expired task, disabled scheduler, missing-credential recovery, shutdown interruption, and invalid concurrency. Use latches/futures with bounded waits.

### Task 2: Configuration and existing callers

Files: application.yml, .env.example, PersonalDispatchTest.java, ResearchApiTest.java.

- [x] Inject `${paperflow.worker.sync-concurrency:4}` in the Spring constructor, validate 1–16 before allocating executor. Preserve existing direct constructors with default 4.
- [x] Map `sync-concurrency: ${PAPERFLOW_WORKER_SYNC_CONCURRENCY:4}` in application.yml and document optional process environment setting in .env.example.
- [x] Existing direct tests await the returned batch future with a bounded get; use try-with-resources for directly constructed synchronizers. Existing Spring API test helper awaits each batch so database assertions follow finished updates.
- [x] Run targeted tests: `mvn -Dtest=ResearchSynchronizerTest,PersonalDispatchTest,ResearchApiTest,WorkerClientTest test`.

### Task 3: Review, regression and learning

Files: docs/task-scheduling-learning.md, README.md, verification-logs/scheduling-*.log.

- [x] Independent reviewer checks admission races, zero-backlog rejection cleanup, interruption, no transaction around HTTP, safe logging and tests. Fix material findings with regression tests.
- [x] Run `mvn test package` with JDK 25 and inspect aggregate results, failures, skips and package success. Redis integration requires its pre-existing dedicated Redis opt-in; report skips accurately.
- [x] Write Chinese walkthrough of the actual call chain, CompletableFuture vs executor, task IDs vs distributed locks, synchronization concurrency vs Agent concurrency, shutdown and configuration.
- [x] Add README link, record exact verification evidence and update this checklist.

## Verification and review — 2026-10-24

- Baseline: 20 existing dispatch/API/client tests passed (`verification-logs/scheduling-baseline.log`).
- Red: original serial synchronizer failed `slowRequestDoesNotBlockAnotherTask` at the fast-task completion assertion, not compilation (`verification-logs/scheduling-red.log`).
- Green: initial 9 scheduling tests passed; targeted dispatch/API/client regression: 29 passed (`scheduling-green.log`, `scheduling-targeted.log`).
- Independent read-only review found no important defects. Added deterministic zero-backlog rejection cleanup with configured concurrency 1; reviewer checked the additional test. A simultaneous tick/close stress test was suggested as optional coverage; admission and close share the same monitor.
- Boundary suite: 10 scheduling tests passed (`verification-logs/scheduling-boundaries.log`).
- Final `mvn -B -ntp test package`, JDK 25 / Java 21 target: 92 discovered, 86 passed, 6 skipped, 0 failures, 0 errors; executable jar repackaged successfully (`verification-logs/scheduling-final.log`). The 6 skipped tests are opt-in RedisWorkflowApiTest cases: no dedicated `PAPERFLOW_TEST_REDIS_PORT` was configured. Redis unit tests passed.
- Production Redis, live models and multi-instance dispatch were not exercised. No daily services restarted. JDK/Mockito/Netty emit existing dependency warnings; the injected storage-failure test intentionally emits sanitized warning types.
- Shutdown caveat documented: the ten-second limit applies to executor termination waiting after admission stops; a blocked pending database read can delay acquiring the admission lock.
