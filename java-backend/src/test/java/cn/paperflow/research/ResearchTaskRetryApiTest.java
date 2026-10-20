package cn.paperflow.research;

import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"paperflow.model-settings.key-file=target/test-settings/master.key","paperflow.worker.scheduling-enabled=false","paperflow.worker.base-url=http://127.0.0.1:19999","paperflow.worker.token=retry-test-worker-token-32-characters"})
@AutoConfigureMockMvc @ActiveProfiles("test")
class ResearchTaskRetryApiTest {
 @Autowired MockMvc mvc; @Autowired ObjectMapper json; @Autowired JdbcTemplate jdbc;
 record Login(MockHttpSession session,String header,String token,long owner) {}
 Login account() throws Exception {
  var r=mvc.perform(get("/api/auth/csrf")).andReturn(); var d=json.readTree(r.getResponse().getContentAsString()).path("data");
  String id=UUID.randomUUID().toString().replace("-","");
  r=mvc.perform(post("/api/auth/register").session((MockHttpSession)r.getRequest().getSession()).header(d.path("header_name").asText(),d.path("token").asText()).contentType("application/json").content(json.writeValueAsString(Map.of("username","user"+id,"email",id+"@example.com","password","good-password")))).andExpect(status().isCreated()).andReturn();
  var s=(MockHttpSession)r.getRequest().getSession(); r=mvc.perform(get("/api/auth/csrf").session(s)).andReturn();d=json.readTree(r.getResponse().getContentAsString()).path("data");
  return new Login(s,d.path("header_name").asText(),d.path("token").asText(),jdbc.queryForObject("select id from pf_users where username=?",Long.class,"user"+id));
 }
 String seed(Login a,String status,String paperId) throws Exception {
  String id=UUID.randomUUID().toString();
  var payload=new LinkedHashMap<String,Object>();payload.put("contract_version",1);payload.put("topic","Snapshot topic");payload.put("limit",1);payload.put("task_type",paperId==null?"research":"study_report");payload.put("index_namespace","java-user:wrong");payload.put("learning_goal","Goal snapshot");payload.put("reflection","Reflection snapshot");payload.put("notes",Map.of("paper","Saved note"));payload.put("collection_note","Saved collection note");
  payload.put("options",Map.of("mode","live","rag","abstract","provider","qwen","model","stale-model","credential_source","server","api_key","old-secret"));
  payload.put("runtime_credentials",Map.of("api_key","old-secret"));
  payload.put("papers",paperId==null?null:List.of(Map.of("source","manual","paper_id",paperId,"title","Original title","pdf_url","https://example.test/p.pdf")));
  jdbc.update("insert into pf_research_tasks(task_id,owner_id,idempotency_key,request_hash,topic,status,payload_json,events_json,error_code,error_message,created_at,updated_at,deadline_at,version) values(?,?,?,?,?,?,?,'[{\"message\":\"old\"}]','old-error','Original failure',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,?,0)",id,a.owner,UUID.randomUUID().toString(),"old-hash","Snapshot topic",status,json.writeValueAsString(payload),java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(120)));
  return id;
 }
 org.springframework.test.web.servlet.ResultActions retry(Login a,String id,String key) throws Exception { return mvc.perform(post("/api/research/tasks/"+id+"/retry").session(a.session).header(a.header,a.token).contentType("application/json").content(json.writeValueAsString(Map.of("idempotency_key",key)))); }
 String accepted(Login a,String id,String key) throws Exception {return json.readTree(retry(a,id,key).andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString()).path("data").path("task_id").asText();}
 String payload(String id) {return jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,id);}
 void personal(Login a,String model) throws Exception {
  mvc.perform(put("/api/model-settings/openai").session(a.session).header(a.header,a.token).contentType("application/json").content(json.writeValueAsString(Map.of("model",model,"api_key","retry-test-secret")))).andExpect(status().isOk());
  mvc.perform(put("/api/model-settings/default").session(a.session).header(a.header,a.token).contentType("application/json").content("{\"provider\":\"openai\"}")).andExpect(status().isOk());
 }
 void paper(Login a,String external) {
  String name=UUID.randomUUID().toString();
  jdbc.update("insert into pf_collections(owner_id,name,name_normalized,description,overall_note,created_at) values(?,?,?,'','',CURRENT_TIMESTAMP)",a.owner,name,name);
  long collection=jdbc.queryForObject("select id from pf_collections where owner_id=? and name=?",Long.class,a.owner,name);
  if(jdbc.queryForObject("select count(*) from pf_papers where source='manual' and external_id=?",Long.class,external)==0) jdbc.update("insert into pf_papers(source,external_id,title,abstract_text,authors_json,categories_json,page_url,created_at) values('manual',?,'Current title','','[]','[]','https://example.test',CURRENT_TIMESTAMP)",external);
  long p=jdbc.queryForObject("select id from pf_papers where source='manual' and external_id=?",Long.class,external);
  jdbc.update("insert into pf_collection_papers(collection_id,paper_id,note,added_at) values(?,?,'Changed note',CURRENT_TIMESTAMP)",collection,p);
 }
 @Test void authenticatesChecksCsrfOwnerAndUuid() throws Exception {
  var a=account();var b=account();String id=seed(a,"failed",null),key=UUID.randomUUID().toString();
  mvc.perform(post("/api/research/tasks/"+id+"/retry").contentType("application/json").content("{}")).andExpect(status().isForbidden());
  mvc.perform(post("/api/research/tasks/"+id+"/retry").session(a.session).contentType("application/json").content("{}")).andExpect(status().isForbidden());
  var anonymous=mvc.perform(get("/api/auth/csrf")).andReturn();var csrf=json.readTree(anonymous.getResponse().getContentAsString()).path("data");
  mvc.perform(post("/api/research/tasks/"+id+"/retry").session((MockHttpSession)anonymous.getRequest().getSession()).header(csrf.path("header_name").asText(),csrf.path("token").asText()).contentType("application/json").content(json.writeValueAsString(Map.of("idempotency_key",key)))).andExpect(status().isUnauthorized());
  retry(b,id,key).andExpect(status().isNotFound());retry(a,id,"not-a-uuid").andExpect(status().isBadRequest());
 }
 @Test void onlyFailedAndInterruptedCanRetry() throws Exception {
  var a=account();for(String status:List.of("queued","running","completed")) retry(a,seed(a,status,null),UUID.randomUUID().toString()).andExpect(status().isConflict());
  assertThat(accepted(a,seed(a,"interrupted",null),UUID.randomUUID().toString())).isNotBlank();
 }
 @Test void clonesSnapshotUsesCurrentDefaultsAndPreservesOriginal() throws Exception {
  var a=account();String p=UUID.randomUUID().toString();paper(a,p);String id=seed(a,"failed",p),before=payload(id);personal(a,"current-retry-model");
  String next=accepted(a,id,UUID.randomUUID().toString());assertThat(next).isNotBlank().isNotEqualTo(id);
  JsonNode original=json.readTree(before),copy=json.readTree(payload(next));
  for(String field:List.of("topic","limit","papers","notes","collection_note","learning_goal","reflection","task_type"))assertThat(copy.path(field)).isEqualTo(original.path(field));
  assertThat(copy.path("options").path("provider").asText()).isEqualTo("openai");assertThat(copy.path("options").path("model").asText()).isEqualTo("current-retry-model");assertThat(copy.path("options").path("credential_source").asText()).isEqualTo("personal");assertThat(copy.path("index_namespace").asText()).isEqualTo("java-user:"+a.owner);
  assertThat(payload(next)).doesNotContain("secret","runtime_credentials","stale-model");assertThat(payload(id)).isEqualTo(before);
  var row=jdbc.queryForMap("select * from pf_research_tasks where task_id=?",next);assertThat(row.get("status")).isEqualTo("queued");assertThat(row.get("events_json").toString()).isEqualTo("[]");assertThat(row.get("error_code")).isNull();assertThat(row.get("report_json")).isNull();assertThat(jdbc.queryForObject("select count(*) from pf_research_tasks where task_id=? and deadline_at>CURRENT_TIMESTAMP",Long.class,next)).isEqualTo(1);
  assertThat(jdbc.queryForObject("select status from pf_research_tasks where task_id=?",String.class,id)).isEqualTo("failed");
  mvc.perform(delete("/api/model-settings/openai/key").session(a.session).header(a.header,a.token)).andExpect(status().isOk());
  String missing=accepted(a,id,UUID.randomUUID().toString());
  assertThat(json.readTree(payload(missing)).path("options").path("credential_source").asText()).isEqualTo("personal");
 }
 @Test void rejectsRemovedOrForeignPaperButAcceptsAnyOwnedCollection() throws Exception {
  var a=account();var b=account();String p=UUID.randomUUID().toString();paper(b,p);String id=seed(a,"failed",p);
  retry(a,id,UUID.randomUUID().toString()).andExpect(status().isBadRequest()).andExpect(jsonPath("$.msg").value(org.hamcrest.Matchers.containsString("重新选择")));
  paper(a,p);assertThat(accepted(a,id,UUID.randomUUID().toString())).isNotBlank();
  jdbc.update("delete from pf_collection_papers where collection_id in (select id from pf_collections where owner_id=?)",a.owner);
  retry(a,id,UUID.randomUUID().toString()).andExpect(status().isBadRequest());
 }
 @Test void replayReturnsSameTaskBeforeRevalidatingPapersOrSettingsAndRejectsOtherOriginal() throws Exception {
  var a=account();String p=UUID.randomUUID().toString();paper(a,p);String id=seed(a,"failed",p),key=UUID.randomUUID().toString();personal(a,"first-model");String next=accepted(a,id,key),snapshot=payload(next);
  personal(a,"changed-model");jdbc.update("delete from pf_collection_papers where collection_id in (select id from pf_collections where owner_id=?)",a.owner);
  assertThat(accepted(a,id,key)).isEqualTo(next);assertThat(payload(next)).isEqualTo(snapshot);retry(a,seed(a,"failed",null),key).andExpect(status().isConflict());
 }
}
