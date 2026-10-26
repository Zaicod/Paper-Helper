package cn.paperflow.research;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.concurrent.*;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
/** Uses the real H2 database and account locks; worker dispatch remains disabled. */
class IntelligentSearchApiTest extends ResearchTaskRetryApiTest {
 Map<String,Object> search(String key){return Map.of("idempotency_key",key,"topic","多模态情绪识别 seediv seedvii","mode","live","limit",10,"rag","none","task_type","search");}
 org.springframework.test.web.servlet.ResultActions submitSearch(Login a,String key) throws Exception{return mvc.perform(post("/api/research/tasks").session(a.session()).header(a.header(),a.token()).contentType("application/json").content(json.writeValueAsString(search(key))));}
 String create(Login a,String key) throws Exception{return json.readTree(submitSearch(a,key).andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString()).path("data").path("task_id").asText();}
 @Test void searchQuotaReplayRetryAndAccountSeparation() throws Exception {
  var a=account();var b=account();personal(a,"search-model");personal(b,"other-model");String key=UUID.randomUUID().toString();String first=create(a,key);String second=create(a,UUID.randomUUID().toString());submitSearch(a,UUID.randomUUID().toString()).andExpect(status().isTooManyRequests());
  assertThat(create(a,key)).isEqualTo(first);assertThat(create(b,UUID.randomUUID().toString())).isNotEqualTo(first);
  mvc.perform(get("/api/research/tasks/"+first).session(b.session())).andExpect(status().isNotFound());
  assertThat(payload(first)).contains("search-model","java-user:"+a.owner()).doesNotContain("retry-test-secret","api_key","runtime_credentials");
  jdbc.update("update pf_research_tasks set status='failed' where task_id=?",first);personal(a,"updated-model");String retried=accepted(a,first,UUID.randomUUID().toString());assertThat(payload(retried)).contains("updated-model");retry(a,first,UUID.randomUUID().toString()).andExpect(status().isTooManyRequests());
  assertThat(jdbc.queryForObject("select status from pf_research_tasks where task_id=?",String.class,first)).isEqualTo("failed");
  assertThat(second).isNotBlank();
 }
 @Test void concurrentDistinctSubmissionsCannotOverrunTwoSearchQuota() throws Exception {
  var a=account();personal(a,"concurrent-model");var start=new CountDownLatch(1);var ready=new CountDownLatch(4);var futures=new ArrayList<Future<Integer>>();
  try(var pool=Executors.newFixedThreadPool(4)){for(int i=0;i<4;i++)futures.add(pool.submit(()->{ready.countDown();start.await();return submitSearch(a,UUID.randomUUID().toString()).andReturn().getResponse().getStatus();}));assertThat(ready.await(10,TimeUnit.SECONDS)).isTrue();start.countDown();var statuses=new ArrayList<Integer>();for(var f:futures)statuses.add(f.get(20,TimeUnit.SECONDS));assertThat(statuses).containsExactlyInAnyOrder(202,202,429,429);}
 }
 @Test void missingDefaultAndInvalidSearchModeHaveClearClientErrors() throws Exception {
  var a=account();submitSearch(a,UUID.randomUUID().toString()).andExpect(status().isBadRequest());personal(a,"model");var body=new HashMap<>(search(UUID.randomUUID().toString()));body.put("mode","demo");mvc.perform(post("/api/research/tasks").session(a.session()).header(a.header(),a.token()).contentType("application/json").content(json.writeValueAsString(body))).andExpect(status().isBadRequest());
 }
}
