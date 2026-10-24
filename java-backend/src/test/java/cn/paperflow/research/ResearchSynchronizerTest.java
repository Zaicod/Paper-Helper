package cn.paperflow.research;

import cn.paperflow.client.WorkerClient;
import cn.paperflow.service.ResearchTaskStore;
import cn.paperflow.task.ResearchSynchronizer;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class ResearchSynchronizerTest {
    @Test void slowRequestDoesNotBlockAnotherTask() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var fastApplied = new CountDownLatch(1);
        var snapshot = new ObjectMapper().createObjectNode().put("status", "running");
        when(store.pending()).thenReturn(List.of(pending("slow"), pending("fast")));
        when(worker.exchange("slow", "running", "{}")).thenAnswer(call -> {
            entered.countDown();
            if (!release.await(5, TimeUnit.SECONDS)) throw new AssertionError("slow request not released");
            return snapshot;
        });
        when(worker.exchange("fast", "running", "{}")).thenReturn(snapshot);
        doAnswer(call -> { fastApplied.countDown(); return null; }).when(store).apply("fast", snapshot);
        try (var synchronizer = new ResearchSynchronizer(store, worker, false);
             var caller = Executors.newSingleThreadExecutor()) {
            var batch = caller.submit(() -> synchronizer.tick());
            try {
                assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
                assertThat(fastApplied.await(2, TimeUnit.SECONDS))
                    .as("fast task must finish while slow request is still blocked").isTrue();
            } finally {
                release.countDown();
                batch.get(5, TimeUnit.SECONDS).get(5, TimeUnit.SECONDS);
            }
        }
    }

    @Test void capacityIsBoundedAndOverflowRemainsAvailableForNextPoll() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        var entered = new CountDownLatch(4);
        var release = new CountDownLatch(1);
        when(store.pending()).thenReturn(List.of(pending("a"), pending("b"), pending("c"), pending("d"), pending("overflow")));
        when(worker.exchange(anyString(), anyString(), anyString())).thenAnswer(call -> {
            entered.countDown();
            if (!release.await(5, TimeUnit.SECONDS)) throw new AssertionError("requests not released");
            return new ObjectMapper().createObjectNode().put("status", "running");
        });
        try (var synchronizer = new ResearchSynchronizer(store, worker, false)) {
            var batch = synchronizer.tick();
            try {
                assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
                synchronizer.tick().get(2, TimeUnit.SECONDS);
                verify(worker, times(4)).exchange(anyString(), anyString(), anyString());
                verify(worker, never()).exchange(eq("overflow"), anyString(), anyString());
                verify(store, never()).problem(anyString(), anyString());
            } finally { release.countDown(); }
            batch.get(5, TimeUnit.SECONDS);
            when(store.pending()).thenReturn(List.of(pending("overflow")));
            synchronizer.tick().get(5, TimeUnit.SECONDS);
            verify(worker).exchange("overflow", "running", "{}");
        }
    }

    @Test void simultaneousPollsNeverOverlapOneTask() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        when(store.pending()).thenReturn(List.of(pending("same")));
        when(worker.exchange("same", "running", "{}")).thenAnswer(call -> {
            entered.countDown();
            release.await();
            return new ObjectMapper().createObjectNode();
        });
        try (var synchronizer = new ResearchSynchronizer(store, worker, false);
             var callers = Executors.newFixedThreadPool(6)) {
            var batch = synchronizer.tick();
            try {
                assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
                var polls = new java.util.ArrayList<Future<?>>();
                for (int i = 0; i < 20; i++) polls.add(callers.submit(() -> synchronizer.tick()));
                for (var poll : polls) poll.get(2, TimeUnit.SECONDS);
                verify(worker, times(1)).exchange("same", "running", "{}");
            } finally { release.countDown(); }
            batch.get(5, TimeUnit.SECONDS);
        }
    }

    @Test void communicationFailureReleasesTaskForRetryWithSameId() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        when(store.pending()).thenReturn(List.of(pending("retry")));
        var snapshot = new ObjectMapper().createObjectNode();
        when(worker.exchange("retry", "running", "{}"))
            .thenThrow(new java.io.IOException("private response" )).thenReturn(snapshot);
        try (var synchronizer = new ResearchSynchronizer(store, worker, false)) {
            synchronizer.tick().get(5, TimeUnit.SECONDS);
            synchronizer.tick().get(5, TimeUnit.SECONDS);
            verify(worker, times(2)).exchange("retry", "running", "{}");
            verify(store).problem("retry", "worker_unavailable");
            verify(store).apply("retry", snapshot);
        }
    }

    @Test void unexpectedStorageFailureDoesNotStrandTaskOrBlockOtherTasks() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        var snapshot = new ObjectMapper().createObjectNode();
        when(store.pending()).thenReturn(List.of(pending("broken"), pending("healthy")));
        when(worker.exchange(anyString(), anyString(), anyString())).thenReturn(snapshot);
        doThrow(new IllegalStateException("private database details")).doNothing().when(store).apply("broken", snapshot);
        doThrow(new IllegalStateException("private database details")).when(store).problem("broken", "worker_unavailable");
        try (var synchronizer = new ResearchSynchronizer(store, worker, false)) {
            synchronizer.tick().get(5, TimeUnit.SECONDS);
            verify(store).apply("healthy", snapshot);
            when(store.pending()).thenReturn(List.of(pending("broken")));
            synchronizer.tick().get(5, TimeUnit.SECONDS);
            verify(store, times(2)).apply("broken", snapshot);
        }
    }

    @Test void expiredTaskNeverCallsWorker() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        when(store.pending()).thenReturn(List.of(new ResearchTaskStore.Pending("expired", "queued", "{}", Instant.now().minusSeconds(1), 7)));
        try (var synchronizer = new ResearchSynchronizer(store, worker, false)) {
            synchronizer.tick().get(5, TimeUnit.SECONDS);
            verify(store).problem("expired", "sync_deadline_exceeded");
            verifyNoInteractions(worker);
        }
    }

    @Test void closeInterruptsRequestWithoutFailingDurableTaskAndStopsAdmission() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        var entered = new CountDownLatch(1);
        var interrupted = new CountDownLatch(1);
        when(store.pending()).thenReturn(List.of(pending("running")));
        when(worker.exchange("running", "running", "{}")).thenAnswer(call -> {
            entered.countDown();
            try { new CountDownLatch(1).await(); }
            catch (InterruptedException ex) { interrupted.countDown(); throw ex; }
            throw new AssertionError("must be interrupted");
        });
        try (var synchronizer = new ResearchSynchronizer(store, worker, false)) {
            var batch = synchronizer.tick();
            assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
            synchronizer.close();
            assertThat(interrupted.await(2, TimeUnit.SECONDS)).isTrue();
            batch.get(2, TimeUnit.SECONDS);
            synchronizer.tick().get(2, TimeUnit.SECONDS);
            verify(store, times(1)).pending();
            verify(store, never()).problem(anyString(), anyString());
            verify(store, never()).apply(anyString(), any());
        }
    }

    @Test void disabledScheduleDoesNotReadDatabase() {
        var store = mock(ResearchTaskStore.class);
        try (var synchronizer = new ResearchSynchronizer(store, mock(WorkerClient.class), false)) {
            synchronizer.scheduled();
            verifyNoInteractions(store);
        }
    }

    @Test void concurrencyConfigurationHasExplicitBounds() {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        for (int invalid : new int[]{-1, 0, 17}) {
            assertThatIllegalArgumentException().isThrownBy(() -> new ResearchSynchronizer(store, worker, false, null, invalid))
                .withMessageContaining("sync-concurrency");
        }
        for (int valid : new int[]{1, 16}) {
            try (var ignored = new ResearchSynchronizer(store, worker, false, null, valid)) { }
        }
    }

    @Test void singleWorkerRejectsDuringHandoffThenRetriesWithoutStrandingRegistration() throws Exception {
        var store = mock(ResearchTaskStore.class);
        var worker = mock(WorkerClient.class);
        var entered = new CountDownLatch(1);
        var releaseRequest = new CountDownLatch(1);
        var completing = new CountDownLatch(1);
        var releaseCompletion = new CountDownLatch(1);
        var retried = new CountDownLatch(1);
        var calls = new java.util.concurrent.atomic.AtomicInteger();
        when(store.pending()).thenReturn(List.of(pending("handoff")));
        when(worker.exchange("handoff", "running", "{}")).thenAnswer(call -> {
            if (calls.incrementAndGet() == 1) {
                entered.countDown();
                releaseRequest.await();
            } else { retried.countDown(); }
            return new ObjectMapper().createObjectNode();
        });
        try (var synchronizer = new ResearchSynchronizer(store, worker, false, null, 1)) {
            var first = synchronizer.tick();
            try {
                assertThat(entered.await(2, TimeUnit.SECONDS)).isTrue();
                // The task-ID set is released before its completion callbacks finish.
                // Block this worker's callback so SynchronousQueue must reject the next handoff.
                var callback = first.thenRun(() -> {
                    completing.countDown();
                    try { releaseCompletion.await(); }
                    catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
                });
                releaseRequest.countDown();
                assertThat(completing.await(2, TimeUnit.SECONDS)).isTrue();
                synchronizer.tick().get(2, TimeUnit.SECONDS);
                assertThat(calls.get()).as("one configured worker cannot accept another handoff").isEqualTo(1);
                verify(store, never()).problem(anyString(), anyString());
                releaseCompletion.countDown();
                callback.get(2, TimeUnit.SECONDS);
                org.awaitility.Awaitility.await().atMost(java.time.Duration.ofSeconds(3)).until(() -> {
                    synchronizer.tick();
                    return retried.getCount() == 0;
                });
            } finally {
                releaseRequest.countDown();
                releaseCompletion.countDown();
            }
        }
    }

    private static ResearchTaskStore.Pending pending(String id) {
        return new ResearchTaskStore.Pending(id, "running", "{}", Instant.now().plusSeconds(60), 7);
    }
}
