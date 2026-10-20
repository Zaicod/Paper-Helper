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

@Component
public class ResearchSynchronizer {
    private final ResearchTaskStore store;
    private final WorkerClient worker;
    private final boolean enabled;
    private final cn.paperflow.service.ModelSettingsService settings;
    public ResearchSynchronizer(ResearchTaskStore store,WorkerClient worker,
        @Value("${paperflow.worker.scheduling-enabled:true}") boolean enabled) {
        this(store,worker,enabled,null);
    }
    @org.springframework.beans.factory.annotation.Autowired
    public ResearchSynchronizer(ResearchTaskStore store,WorkerClient worker,
        @Value("${paperflow.worker.scheduling-enabled:true}") boolean enabled,cn.paperflow.service.ModelSettingsService settings) {
        this.store=store; this.worker=worker; this.enabled=enabled;this.settings=settings;
    }
    @Scheduled(fixedDelayString="${paperflow.worker.poll-delay-ms:2000}")
    public void scheduled() { if (enabled) tick(); }
    // One Java instance owns synchronization in this first version; no network calls hold a DB transaction.
    public synchronized void tick() {
        for (var task:store.pending()) {
            if (!task.deadline().isAfter(Instant.now())) { store.problem(task.taskId(),"sync_deadline_exceeded"); continue; }
            try {
                String payload=settings!=null && "queued".equals(task.status()) ? settings.dispatchPayload(task.ownerId(),task.payload()) : task.payload();
                store.apply(task.taskId(),worker.exchange(task.taskId(),task.status(),payload));
            }
            catch (cn.paperflow.service.ModelSettingsService.MissingCredentials ex) {
                // A previous POST may have been accepted before its response was lost.
                // Recover that execution without sending a replacement credential or a new POST.
                try { store.apply(task.taskId(),worker.exchange(task.taskId(),"running",task.payload())); }
                catch (WorkerClient.LostExecution missing) { store.problem(task.taskId(),"model_credentials_missing"); }
                catch (IOException unavailable) { store.problem(task.taskId(),"worker_unavailable"); }
                catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); return; }
            }
            catch (WorkerClient.LostExecution ex) { store.problem(task.taskId(),"execution_lost"); }
            catch (IOException ex) { store.problem(task.taskId(),"worker_unavailable"); }
            catch (InterruptedException ex) { Thread.currentThread().interrupt(); return; }
        }
    }
}

@Configuration @EnableScheduling
class ResearchSchedulingConfiguration {}
