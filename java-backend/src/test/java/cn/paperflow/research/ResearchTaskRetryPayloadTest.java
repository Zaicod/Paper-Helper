package cn.paperflow.research;

import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import cn.paperflow.dto.RetryTaskDTO;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.service.LibraryService;
import cn.paperflow.service.ModelSettingsService;
import cn.paperflow.service.impl.ResearchTaskServiceImpl;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class ResearchTaskRetryPayloadTest {
 @Test void refusesUnavailableWorkerWithoutPersisting() {
  var mapper=mock(ResearchTaskMapper.class);var worker=mock(WorkerClient.class);
  when(mapper.findOwned("original",7)).thenReturn(original("{}"));
  var service=new ResearchTaskServiceImpl(mapper,mock(LibraryService.class),new ObjectMapper(),worker,1800);
  assertThatThrownBy(()->service.retry(7,"original",new RetryTaskDTO(UUID.randomUUID().toString()))).isInstanceOfSatisfying(ApiException.class,e->assertThat(e.status()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE));
  verify(mapper,never()).insert(any());
 }
 @Test void rejectsOversizedRetryPayloadBeforePersisting() throws Exception {
  var mapper=mock(ResearchTaskMapper.class);var worker=mock(WorkerClient.class);var json=new ObjectMapper();when(worker.configured()).thenReturn(true);
  when(mapper.findOwned("original",7)).thenReturn(original(json.writeValueAsString(Map.of("topic","Snapshot","notes",Map.of("p","中".repeat(800000)),"options",Map.of("mode","live")))));
  var service=new ResearchTaskServiceImpl(mapper,mock(LibraryService.class),json,worker,1800);
  assertThatThrownBy(()->service.retry(7,"original",new RetryTaskDTO(UUID.randomUUID().toString()))).isInstanceOfSatisfying(ApiException.class,e->{assertThat(e.status()).isEqualTo(HttpStatus.BAD_REQUEST);assertThat(e.getMessage()).contains("2 MiB");});
  verify(mapper,never()).insert(any());
 }
 @Test void demoRemainsOfflineDespitePersonalDefault() throws Exception {
  var mapper=mock(ResearchTaskMapper.class);var worker=mock(WorkerClient.class);var json=new ObjectMapper();var settings=mock(ModelSettingsService.class);when(worker.configured()).thenReturn(true);
  when(mapper.findOwned("original",7)).thenReturn(original("{\"topic\":\"Snapshot\",\"options\":{\"mode\":\"demo\",\"rag\":\"none\",\"provider\":\"openai\",\"credential_source\":\"personal\",\"model\":\"stale-model\"}}"));
  when(settings.resolve(7,null,null,false)).thenReturn(new ModelSettingsService.Selection("qwen",null,"server"));
  var service=new ResearchTaskServiceImpl(mapper,mock(LibraryService.class),json,worker,1800,settings);
  service.retry(7,"original",new RetryTaskDTO(UUID.randomUUID().toString()));
  var saved=org.mockito.ArgumentCaptor.forClass(ResearchTask.class);verify(mapper).insert(saved.capture());
  var options=json.readTree(saved.getValue().getPayloadJson()).path("options");assertThat(options.path("mode").asText()).isEqualTo("demo");assertThat(options.path("rag").asText()).isEqualTo("none");assertThat(options.path("credential_source").asText()).isEqualTo("server");verify(settings).resolve(7,null,null,false);
  verify(mapper,never()).countOwnedPaper(anyLong(),anyString(),anyString());
 }
 private ResearchTask original(String payload) {var t=new ResearchTask();t.setTaskId("original");t.setOwnerId(7);t.setStatus("failed");t.setTopic("Snapshot");t.setPayloadJson(payload);return t;}
}
