package cn.paperflow.research;
import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.service.impl.ResearchTaskStoreImpl;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class IntelligentSearchFailureTest {
 @Test void keepsSafeSearchReasonOnlyForSearchTasks() throws Exception {
  var json=new ObjectMapper();for(String type:java.util.List.of("search","research")) {
   var mapper=mock(ResearchTaskMapper.class);var task=new ResearchTask();task.setStatus("running");task.setPayloadJson(json.writeValueAsString(Map.of("task_type",type)));when(mapper.findById("id")).thenReturn(task);
   new ResearchTaskStoreImpl(mapper,json).apply("id",json.readTree("{\"status\":\"failed\",\"events\":[],\"error_code\":\"search_failed\",\"error_message\":\"文献来源暂不可用，请稍后重试\"}"));
   assertThat(task.getErrorCode()).isEqualTo(type.equals("search")?"search_failed":"research_failed");if(type.equals("search"))assertThat(task.getErrorMessage()).isEqualTo("文献来源暂不可用，请稍后重试");
  }
 }
 @Test void rejectsControlCharactersInPublicReason() throws Exception {
  var json=new ObjectMapper();var mapper=mock(ResearchTaskMapper.class);var task=new ResearchTask();task.setStatus("running");task.setPayloadJson("{\"task_type\":\"search\"}");when(mapper.findById("id")).thenReturn(task);
  var snapshot=json.createObjectNode().put("status","failed").put("error_code","search_failed").put("error_message","secret\nheader");snapshot.putArray("events");new ResearchTaskStoreImpl(mapper,json).apply("id",snapshot);assertThat(task.getErrorMessage()).doesNotContain("secret");
 }
}
