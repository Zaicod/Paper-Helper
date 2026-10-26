package cn.paperflow.task;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.service.ResearchTaskStore;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.time.Instant;
import cn.paperflow.service.ModelSettingsService;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.ArrayList;
import java.util.Set;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

@Component
public class ResearchSynchronizer implements AutoCloseable {
    private static final Logger log = LoggerFactory.getLogger(ResearchSynchronizer.class);
    private final ResearchTaskStore store;
    private final WorkerClient worker;
    private final boolean enabled;
    private final ModelSettingsService settings;
    private final int concurrency;
    private final ThreadPoolExecutor executor;
    private final Set<String> inFlight = ConcurrentHashMap.newKeySet();
    private boolean closed;
    public ResearchSynchronizer(ResearchTaskStore store,WorkerClient worker,
        @Value("${paperflow.worker.scheduling-enabled:true}") boolean enabled) {
        this(store,worker,enabled,null);
    }
    public ResearchSynchronizer(ResearchTaskStore store,WorkerClient worker,
        boolean enabled,ModelSettingsService settings) {
        this(store,worker,enabled,settings,4);
    }
    @org.springframework.beans.factory.annotation.Autowired
    public ResearchSynchronizer(ResearchTaskStore store,WorkerClient worker,
        @Value("${paperflow.worker.scheduling-enabled:true}") boolean enabled,ModelSettingsService settings,
        @Value("${paperflow.worker.sync-concurrency:4}") int concurrency) {
        if (concurrency < 1 || concurrency > 16)
            throw new IllegalArgumentException("paperflow.worker.sync-concurrency must be between 1 and 16");
        this.store=store; this.worker=worker; this.enabled=enabled; this.settings=settings;
        this.concurrency=concurrency;
        var sequence = new AtomicInteger();
        executor = new ThreadPoolExecutor(concurrency,concurrency,0,TimeUnit.MILLISECONDS,
            new SynchronousQueue<>(), runnable -> new Thread(runnable,"research-sync-"+sequence.incrementAndGet()),
            new ThreadPoolExecutor.AbortPolicy());
    }
    @Scheduled(fixedDelayString="${paperflow.worker.poll-delay-ms:2000}")
    public void scheduled() { if (enabled) tick(); }
    // Admission is serialized; HTTP and short store transactions execute outside this monitor.
    // The future describes only work admitted by this tick, not every durable pending task.
    public synchronized CompletableFuture<Void> tick() {
        if (closed) return CompletableFuture.completedFuture(null);
        var batch = new ArrayList<CompletableFuture<Void>>();
        for (var task:store.pending()) {
            if (inFlight.size() >= concurrency) break;
            if (!inFlight.add(task.taskId())) continue;
            var done = new CompletableFuture<Void>();
            try {
                executor.execute(() -> {
                    try {
                        if (!Thread.currentThread().isInterrupted()) synchronize(task);
                    } catch (RuntimeException ex) {
                        // Never log exception messages, payloads, keys or remote response bodies.
                        log.warn("Research synchronization failed ({})",ex.getClass().getSimpleName());
                        try { store.problem(task.taskId(),"worker_unavailable"); }
                        catch (RuntimeException storeFailure) {
                            log.warn("Research synchronization error could not be saved ({})",storeFailure.getClass().getSimpleName());
                        }
                    } finally {
                        inFlight.remove(task.taskId());
                        done.complete(null);
                    }
                });
                batch.add(done);
            } catch (RejectedExecutionException full) {
                // A completing worker may not yet be ready to accept another handoff.
                inFlight.remove(task.taskId());
                break;
            }
        }
        return CompletableFuture.allOf(batch.toArray(CompletableFuture[]::new));
    }

    private void synchronize(ResearchTaskStore.Pending task) {
        if (!task.deadline().isAfter(Instant.now())) { store.problem(task.taskId(),"sync_deadline_exceeded"); return; }
        try {
            String payload=settings!=null && "queued".equals(task.status())
                ? settings.dispatchPayload(task.ownerId(),task.payload()) : task.payload();
            store.apply(task.taskId(),worker.exchange(task.taskId(),task.status(),payload));
        } catch (ModelSettingsService.MissingCredentials ex) {
            // A previous POST may have been accepted before its response was lost.
            // Recover that execution without sending a replacement credential or a new POST.
            try { store.apply(task.taskId(),worker.exchange(task.taskId(),"running",task.payload())); }
            catch (WorkerClient.LostExecution missing) { store.problem(task.taskId(),"model_credentials_missing"); }
            catch (IOException unavailable) { store.problem(task.taskId(),"worker_unavailable"); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
        } catch (WorkerClient.LostExecution ex) { store.problem(task.taskId(),"execution_lost"); }
        catch (IOException ex) { store.problem(task.taskId(),"worker_unavailable"); }
        catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
    }

    @Override @PreDestroy
    public void close() {
        synchronized (this) {
            if (closed) return;
            closed=true;
            executor.shutdownNow();
        }
        try {
            if (!executor.awaitTermination(10,TimeUnit.SECONDS))
                log.warn("Research synchronization workers did not stop within 10 seconds");
        } catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
    }
}

@Configuration @EnableScheduling
class ResearchSchedulingConfiguration {}
