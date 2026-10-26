package cn.paperflow.research;
import com.fasterxml.jackson.databind.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.*;
import org.springframework.test.context.*;
import org.springframework.test.web.servlet.MockMvc;
import java.util.*;
import java.nio.charset.StandardCharsets;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@SpringBootTest @AutoConfigureMockMvc @ActiveProfiles("test")
class PaperDocumentApiTest {
 static final ObjectMapper wire=new ObjectMapper(); static final String token="document-test-token-of-at-least-32-characters";
 static volatile String resultState="ready"; static volatile JsonNode preparedInput; static volatile byte[] uploaded;
 static final HttpServer server=start();
 static HttpServer start(){try{var s=HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
 s.createContext("/internal/v1/documents",x->{
  assertThat(x.getRequestHeaders().getFirst("Authorization")).isEqualTo("Bearer "+token);
  assertThat(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
  byte[] response; String path=x.getRequestURI().getPath();
  if(path.endsWith("/upload")){uploaded=x.getRequestBody().readAllBytes(); assertThat(x.getRequestHeaders().getFirst("Content-Type")).isEqualTo("application/pdf");response=wire.writeValueAsBytes(Map.of("upload_id",UUID.randomUUID().toString()));}
  else if(path.endsWith("/prepare")){preparedInput=wire.readTree(x.getRequestBody());var r=new LinkedHashMap<String,Object>();r.put("document_id","ready".equals(resultState)?UUID.randomUUID().toString():null);r.put("status",resultState);r.put("message","ready".equals(resultState)?"正文已准备":"没有公开 PDF");r.put("filename","paper.pdf");r.put("sha256","a".repeat(64));r.put("source_kind",preparedInput.has("upload_id")?"uploaded":"remote");r.put("page_count",4);r.put("prepared_at","2026-10-24T00:00:00Z");response=wire.writeValueAsBytes(r);}
  else{response="%PDF-controlled".getBytes(StandardCharsets.UTF_8);x.getResponseHeaders().set("Content-Type","application/pdf");}
  x.sendResponseHeaders(200,response.length);try(var out=x.getResponseBody()){out.write(response);}
 });s.start();return s;}catch(Exception e){throw new RuntimeException(e);}}
 @DynamicPropertySource static void properties(DynamicPropertyRegistry p){p.add("paperflow.worker.base-url",()->"http://127.0.0.1:"+server.getAddress().getPort());p.add("paperflow.worker.token",()->token);p.add("paperflow.worker.scheduling-enabled",()->false);}
 @Autowired MockMvc mvc; @Autowired ObjectMapper json; @Autowired JdbcTemplate jdbc;
 @BeforeEach void reset(){resultState="ready";uploaded=null;}
 @AfterAll static void stop(){server.stop(0);}
 @Test void studyRejectsUnpreparedBeforeInsertThenSnapshotsReadyAndDefault() throws Exception {
  var a=user();var s=selection(a);var input=study(s);long before=jdbc.queryForObject("select count(*) from pf_research_tasks",Long.class);
  postJson(a,"/api/research/tasks",input,409);assertThat(jdbc.queryForObject("select count(*) from pf_research_tasks",Long.class)).isEqualTo(before);
  assertThat(getStatus(a,s).path("status").asText()).isEqualTo("not_prepared");
  var ready=postJson(a,path(s)+"/prepare",Map.of(),200);assertThat(ready.path("status").asText()).isEqualTo("ready");
  input.put("topic", " ");var task=postJson(a,"/api/research/tasks",input,202);String id=task.path("task_id").asText();
  var snapshot=json.readTree(jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,id));
  assertThat(snapshot.path("prepared_documents").path("paper-x").asText()).isEqualTo(ready.path("document_id").asText());
  assertThat(snapshot.path("library_selection").path("collection_id").asLong()).isEqualTo(s[0]);
  assertThat(snapshot.path("topic").asText()).contains("核心创新点");
  assertThat(postJson(a,"/api/research/tasks",input,202).path("task_id").asText()).isEqualTo(id);
 }
 @Test void uploadIsPrivateAndMetadataChangesInvalidateWhileOldDocumentStillDownloads() throws Exception {
  var a=user();var b=user();var s=selection(a);var file=new MockMultipartFile("file","paper.pdf","application/pdf","%PDF-controlled".getBytes(StandardCharsets.UTF_8));
  var response=mvc.perform(multipart(path(s)).file(file).session(a).with(csrf())).andExpect(status().isOk()).andReturn();
  var ready=json.readTree(response.getResponse().getContentAsString(StandardCharsets.UTF_8)).path("data");String id=ready.path("document_id").asText();assertThat(uploaded).isEqualTo(file.getBytes());assertThat(preparedInput.has("upload_id")).isTrue();
  mvc.perform(get("/api/library/documents/{id}/file",id).session(b)).andExpect(status().isNotFound());
  mvc.perform(post(path(s)+"/prepare").session(b).with(csrf())).andExpect(status().isNotFound());
  mvc.perform(put("/api/library/collections/{c}/papers/{p}",s[0],s[1]).session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(paper("Changed")))).andExpect(status().isOk());
  assertThat(getStatus(a,s).path("status").asText()).isEqualTo("not_prepared");
  mvc.perform(delete("/api/library/collections/{c}/papers/{p}",s[0],s[1]).session(a).with(csrf())).andExpect(status().isNoContent());
  mvc.perform(get("/api/library/documents/{id}/file",id).session(a)).andExpect(status().isOk()).andExpect(content().contentType("application/pdf"));
 }
 @Test void categorizedPreparationFailureDoesNotAllowStudy() throws Exception {
  var a=user();var s=selection(a);resultState="missing";assertThat(postJson(a,path(s)+"/prepare",Map.of(),200).path("status").asText()).isEqualTo("missing");postJson(a,"/api/research/tasks",study(s),409);
 }
 @Test void repairUsesCurrentMetadataAndPreparedDocumentWithoutChangingHistoryAndRetryKeepsSnapshot() throws Exception {
  var a=user();var s=selection(a);var oldDoc=postJson(a,path(s)+"/prepare",Map.of(),200);var task=postJson(a,"/api/research/tasks",study(s),202);String id=task.path("task_id").asText();
  jdbc.update("update pf_research_tasks set status='failed', error_message='old failure' where task_id=?",id);
  String old=jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,id);
  mvc.perform(put("/api/library/collections/{c}/papers/{p}",s[0],s[1]).session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(paper("Repaired title")))).andExpect(status().isOk());
  mvc.perform(put("/api/library/collections/{c}/note",s[0]).session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(Map.of("content","New collection context")))).andExpect(status().isOk());
  var request=Map.of("idempotency_key",UUID.randomUUID().toString());postJson(a,"/api/research/tasks/"+id+"/repair",request,409);
  var newDoc=postJson(a,path(s)+"/prepare",Map.of(),200);var repaired=postJson(a,"/api/research/tasks/"+id+"/repair",request,202);String repairedId=repaired.path("task_id").asText();
  assertThat(repairedId).isNotEqualTo(id);assertThat(postJson(a,"/api/research/tasks/"+id+"/repair",request,202).path("task_id").asText()).isEqualTo(repairedId);
  var snap=json.readTree(jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,repairedId));assertThat(snap.path("collection_note").asText()).isEqualTo("New collection context");assertThat(snap.path("papers").get(0).path("title").asText()).isEqualTo("Repaired title");assertThat(snap.path("prepared_documents").path("paper-x").asText()).isEqualTo(newDoc.path("document_id").asText());
  assertThat(jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,id)).isEqualTo(old);
  String retry=postJson(a,"/api/research/tasks/"+id+"/retry",Map.of("idempotency_key",UUID.randomUUID().toString()),202).path("task_id").asText();
  assertThat(json.readTree(jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,retry)).path("prepared_documents").path("paper-x").asText()).isEqualTo(oldDoc.path("document_id").asText());
 }
 @Test void legacyRepairFindsOwnedCurrentPaperDropsOldCredentialsAndUsesCurrentDefaultModel() throws Exception {
  var a=user();var b=user();var s=selection(a);var other=selection(b);
  postJson(a,path(s)+"/prepare",Map.of(),200);
  String id=postJson(a,"/api/research/tasks",study(s),202).path("task_id").asText();
  var legacy=(com.fasterxml.jackson.databind.node.ObjectNode)json.readTree(jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,id));
  legacy.remove("prepared_documents");legacy.remove("library_selection");legacy.putObject("runtime_credentials").put("api_key","stale-legacy-secret");legacy.putObject("arbitrary_legacy_field").put("api_key","stale-legacy-secret");
  jdbc.update("update pf_research_tasks set status='failed',payload_json=? where task_id=?",json.writeValueAsString(legacy),id);
  mvc.perform(put("/api/model-settings/openai").session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(Map.of("model","current-repair-model","api_key","controlled-test-secret")))).andExpect(status().isOk());
  mvc.perform(put("/api/model-settings/default").session(a).with(csrf()).contentType("application/json").content("{\"provider\":\"openai\"}")).andExpect(status().isOk());
  postJson(b,"/api/research/tasks/"+id+"/repair",Map.of("idempotency_key",UUID.randomUUID().toString()),404);
  String next=postJson(a,"/api/research/tasks/"+id+"/repair",Map.of("idempotency_key",UUID.randomUUID().toString()),202).path("task_id").asText();
  String text=jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,next);var copy=json.readTree(text);
  assertThat(copy.path("options").path("model").asText()).isEqualTo("current-repair-model");assertThat(copy.path("options").path("credential_source").asText()).isEqualTo("personal");
  assertThat(copy.path("library_selection").path("collection_id").asLong()).isEqualTo(s[0]);assertThat(text).doesNotContain("secret","runtime_credentials","arbitrary_legacy_field");
 }
 Map<String,Object> study(long[] s){var m=new HashMap<String,Object>();m.put("idempotency_key",UUID.randomUUID().toString());m.put("topic","Study");m.put("mode","live");m.put("task_type","study_report");m.put("collection_id",s[0]);m.put("paper_ids",List.of(s[1]));return m;}
 String path(long[] s){return "/api/library/collections/"+s[0]+"/papers/"+s[1]+"/document";}
 JsonNode getStatus(MockHttpSession a,long[] s)throws Exception {return json.readTree(mvc.perform(get(path(s)).session(a)).andExpect(status().isOk()).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8)).path("data");}
 Map<String,Object> paper(String title){return Map.of("source","manual","paper_id","paper-x","title",title,"abstract","Evidence","page_url","https://example.test/p","pdf_url","https://example.test/p.pdf");}
 long[] selection(MockHttpSession a)throws Exception {long c=postJson(a,"/api/library/collections",Map.of("name","Docs"),201).path("id").asLong();long p=postJson(a,"/api/library/collections/"+c+"/papers",paper("Paper"),201).path("id").asLong();return new long[]{c,p};}
 JsonNode postJson(MockHttpSession a,String path,Object body,int status)throws Exception{return json.readTree(mvc.perform(post(path).session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body))).andExpect(status().is(status)).andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8)).path("data");}
 MockHttpSession user()throws Exception{String name="u"+UUID.randomUUID().toString().replace("-","");return (MockHttpSession)mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json").content(json.writeValueAsBytes(Map.of("username",name,"email",name+"@example.test","password","testing-pass-123")))).andExpect(status().isCreated()).andReturn().getRequest().getSession(false);}
}
