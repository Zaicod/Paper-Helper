package cn.paperflow.research;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.dto.ResearchTaskDTO;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.service.*;
import cn.paperflow.service.impl.ResearchTaskServiceImpl;
import cn.paperflow.task.ResearchSynchronizer;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class PersonalDispatchTest {
 @Test void submitSnapshotsResolvedPersonalDefaultWithoutSecret() {
  var tasks=mock(ResearchTaskMapper.class);var settings=mock(ModelSettingsService.class);var worker=mock(WorkerClient.class);when(worker.configured()).thenReturn(true);
  when(settings.resolve(7,null,null,true)).thenReturn(new ModelSettingsService.Selection("openai","personal-model","personal"));
  var service=new ResearchTaskServiceImpl(tasks,mock(LibraryService.class),new ObjectMapper(),worker,1800,settings);
  service.submit(7,new ResearchTaskDTO(UUID.randomUUID().toString(),"topic","live",3,null,null,null,null,null));
  var captured=org.mockito.ArgumentCaptor.forClass(ResearchTask.class);verify(tasks).insert(captured.capture());
  assertThat(captured.getValue().getPayloadJson()).contains("personal-model","\"provider\":\"openai\"","\"credential_source\":\"personal\"").doesNotContain("api_key","runtime_credentials");
 }
 @Test void dispatchReadsOnlyQueuedCredentialsAndMissingKeyFailsTerminal() throws Exception {
  var store=mock(ResearchTaskStore.class);var settings=mock(ModelSettingsService.class);var worker=mock(WorkerClient.class);
  when(store.pending()).thenReturn(List.of(new ResearchTaskStore.Pending("one","queued","durable",Instant.now().plusSeconds(60),7),new ResearchTaskStore.Pending("two","running","durable",Instant.now().plusSeconds(60),7)));
  when(settings.dispatchPayload(7,"durable")).thenThrow(new ModelSettingsService.MissingCredentials());
  when(worker.exchange("one","running","durable")).thenThrow(new WorkerClient.LostExecution());
  new ResearchSynchronizer(store,worker,false,settings).tick();
  verify(store).problem("one","model_credentials_missing");verify(worker,never()).exchange("one","queued","durable");verify(worker).exchange("two","running","durable");
 }
 @Test void deletedKeyAfterLostPostAcknowledgementKeepsRemoteExecution() throws Exception {
  var store=mock(ResearchTaskStore.class);var settings=mock(ModelSettingsService.class);var worker=mock(WorkerClient.class);
  when(store.pending()).thenReturn(List.of(new ResearchTaskStore.Pending("one","queued","durable",Instant.now().plusSeconds(60),7)));
  when(settings.dispatchPayload(7,"durable")).thenThrow(new ModelSettingsService.MissingCredentials());
  var snapshot=new ObjectMapper().readTree("{\"status\":\"running\"}");when(worker.exchange("one","running","durable")).thenReturn(snapshot);
  new ResearchSynchronizer(store,worker,false,settings).tick();
  verify(store).apply("one",snapshot);verify(store,never()).problem(any(),any());verify(worker,never()).exchange("one","queued","durable");
 }
}
