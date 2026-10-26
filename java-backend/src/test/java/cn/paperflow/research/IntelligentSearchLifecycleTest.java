package cn.paperflow.research;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import cn.paperflow.dto.*;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.service.*;
import cn.paperflow.service.impl.ResearchTaskServiceImpl;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class IntelligentSearchLifecycleTest {
 final ResearchTaskMapper mapper=mock(ResearchTaskMapper.class);
 final WorkerClient worker=mock(WorkerClient.class);
 final ModelSettingsService settings=mock(ModelSettingsService.class);
 final ObjectMapper json=new ObjectMapper();
 final ResearchTaskServiceImpl service=new ResearchTaskServiceImpl(mapper,mock(LibraryService.class),json,worker,1800,settings);
 IntelligentSearchLifecycleTest(){when(worker.configured()).thenReturn(true);when(settings.resolve(anyLong(),isNull(),isNull(),eq(true))).thenReturn(new ModelSettingsService.Selection("openai","current","personal"));}
 ResearchTaskDTO input(String mode,String rag,Long collection,String provider){return new ResearchTaskDTO(UUID.randomUUID().toString(),"多模态情绪识别 seediv seedvii",mode,10,rag,provider,null,collection,null,"search","","");}
 ResearchTask task(String type,String status){var t=new ResearchTask();t.setTaskId(UUID.randomUUID().toString());t.setStatus(status);t.setTopic("saved");t.setPayloadJson("{\"task_type\":\""+type+"\",\"topic\":\"saved\",\"options\":{\"mode\":\"live\",\"rag\":\"none\"}}");t.setEventsJson("[]");return t;}
 void rejected(Runnable action,HttpStatus status){assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class,e->assertThat(e.status()).isEqualTo(status));}
 @Test void searchRejectsOfflineRagCollectionsAndExplicitModels(){for(var in:List.of(input("demo","none",null,null),input("live","abstract",null,null),input("live","none",1L,null),input("live","none",null,"openai")))rejected(()->service.submit(7,in),HttpStatus.BAD_REQUEST);verify(mapper,never()).insert(any());}
 @Test void requiresPersonalDefault(){when(settings.resolve(7,null,null,true)).thenReturn(new ModelSettingsService.Selection("qwen",null,"server"));rejected(()->service.submit(7,input("live","none",null,null)),HttpStatus.BAD_REQUEST);}
 @Test void acceptsSearchAndPersistsNoSecrets() throws Exception {service.submit(7,input("live","none",null,null));var cap=org.mockito.ArgumentCaptor.forClass(ResearchTask.class);verify(mapper).insert(cap.capture());var p=json.readTree(cap.getValue().getPayloadJson());assertThat(p.path("task_type").asText()).isEqualTo("search");assertThat(p.path("index_namespace").asText()).isEqualTo("java-user:7");assertThat(p.path("options").path("model").asText()).isEqualTo("current");assertThat(cap.getValue().getPayloadJson()).doesNotContain("api_key","runtime_credentials");verify(settings).resolve(7,null,null,true);}
 @Test void thirdSearchRejectedButOtherTaskTypesDoNotCount(){when(mapper.listOwned(7,0,Integer.MAX_VALUE,List.of("queued","running"),null)).thenReturn(List.of(task("search","queued"),task("search","running"))); rejected(()->service.submit(7,input("live","none",null,null)),HttpStatus.TOO_MANY_REQUESTS); verify(mapper).lockOwner(7); verify(mapper,never()).insert(any());}
 @Test void replayPrecedesQuotaAndSettings(){var in=input("live","none",null,null);service.submit(7,in);var cap=org.mockito.ArgumentCaptor.forClass(ResearchTask.class);verify(mapper).insert(cap.capture());when(mapper.findRequest(7,in.idempotencyKey())).thenReturn(cap.getValue());reset(settings);assertThat(service.submit(7,in).taskId()).isEqualTo(cap.getValue().getTaskId());verifyNoInteractions(settings);}
 @Test void otherOwnersAndOtherTypesDoNotCount(){when(mapper.listOwned(7,0,Integer.MAX_VALUE,List.of("queued","running"),null)).thenReturn(List.of(task("research","running"),task("study_report","queued")));service.submit(7,input("live","none",null,null));verify(mapper).insert(any());verify(mapper,never()).listOwned(eq(8L),anyLong(),anyInt(),any(),any());}
 @Test void retryEnforcesSameQuota(){when(mapper.findOwned("old",7)).thenReturn(task("search","failed"));when(mapper.listOwned(7,0,Integer.MAX_VALUE,List.of("queued","running"),null)).thenReturn(List.of(task("search","queued"),task("search","running")));rejected(()->service.retry(7,"old",new RetryTaskDTO(UUID.randomUUID().toString())),HttpStatus.TOO_MANY_REQUESTS);}
 @Test void retryUsesPersonalDefaultAndRejectsServerFallback(){var t=task("search","failed");when(mapper.findOwned("old",7)).thenReturn(t);when(settings.resolve(7,null,null,true)).thenReturn(new ModelSettingsService.Selection("qwen",null,"server"));rejected(()->service.retry(7,"old",new RetryTaskDTO(UUID.randomUUID().toString())),HttpStatus.BAD_REQUEST);}
}
