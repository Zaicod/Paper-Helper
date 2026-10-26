package cn.paperflow.research;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
class CitationTrackingApiTest extends ResearchTaskRetryApiTest {
 long collection(Login a) {return jdbc.queryForObject("select max(id) from pf_collections where owner_id=?",Long.class,a.owner());}
 long paperId(String external) {return jdbc.queryForObject("select id from pf_papers where source='manual' and external_id=?",Long.class,external);}
 Map<String,Object> request(Login a,String ext) {
  var b=new LinkedHashMap<String,Object>();b.put("idempotency_key",UUID.randomUUID().toString());b.put("topic","");b.put("task_type","citation_trace");b.put("citation_direction","both");b.put("mode","live");b.put("rag","none");b.put("limit",20);b.put("collection_id",collection(a));b.put("paper_ids",List.of(paperId(ext)));return b;
 }
 org.springframework.test.web.servlet.ResultActions submit(Login a,Map<String,Object>b)throws Exception{return mvc.perform(post("/api/research/tasks").session(a.session()).header(a.header(),a.token()).contentType("application/json").content(json.writeValueAsString(b)));}
 String created(Login a,Map<String,Object>b)throws Exception{return json.readTree(submit(a,b).andExpect(status().isAccepted()).andReturn().getResponse().getContentAsString()).path("data").path("task_id").asText();}
 @Test void createsOwnedSeedSnapshotWithoutPdfAndPreservesIndependentLimit()throws Exception {
  var a=account();personal(a,"trace-model");String ext="trace-"+UUID.randomUUID();paper(a,ext);var b=request(a,ext);String id=created(a,b);var p=json.readTree(payload(id));
  assertThat(p.path("task_type").asText()).isEqualTo("citation_trace");assertThat(p.path("citation_direction").asText()).isEqualTo("both");assertThat(p.path("limit").asInt()).isEqualTo(20);
  assertThat(p.path("topic").asText()).contains("追踪");assertThat(p.path("papers").size()).isEqualTo(1);assertThat(p.path("papers").get(0).path("pdf_url").isNull()).isTrue();
  assertThat(p.path("library_selection").path("collection_id").asLong()).isEqualTo(collection(a));assertThat(p.has("prepared_documents")).isFalse();
  assertThat(p.path("options").path("credential_source").asText()).isEqualTo("personal");assertThat(payload(id)).doesNotContain("retry-test-secret");assertThat(created(a,b)).isEqualTo(id);
  var changed=new LinkedHashMap<>(b);changed.put("citation_direction","references");submit(a,changed).andExpect(status().isConflict());
 }
 @Test void defaultDirectionAndRetryKeepOriginalSeedsAndCurrentModel()throws Exception {
  var a=account();personal(a,"first-model");String ext="trace-"+UUID.randomUUID();paper(a,ext);var b=request(a,ext);b.remove("citation_direction");String id=created(a,b);var initial=json.readTree(payload(id));
  assertThat(initial.path("citation_direction").asText()).isEqualTo("both");jdbc.update("update pf_research_tasks set status='failed' where task_id=?",id);jdbc.update("update pf_papers set title='Changed later' where id=?",paperId(ext));personal(a,"new-model");
  String retried=accepted(a,id,UUID.randomUUID().toString());var r=json.readTree(payload(retried));assertThat(r.path("papers")).isEqualTo(initial.path("papers"));assertThat(r.path("library_selection")).isEqualTo(initial.path("library_selection"));assertThat(r.path("citation_direction").asText()).isEqualTo("both");assertThat(r.path("options").path("model").asText()).isEqualTo("new-model");
 }
 @Test void rejectsInvalidDirectionModesOverridesAndUnrelatedDirection()throws Exception {
  var a=account();personal(a,"model");String ext="trace-"+UUID.randomUUID();paper(a,ext);
  for(var entry:Map.<String,Object>of("citation_direction","recursive","mode","demo","rag","abstract","provider","openai","model","override").entrySet()){var b=request(a,ext);b.put(entry.getKey(),entry.getValue());submit(a,b).andExpect(status().isBadRequest());}
  var b=request(a,ext);b.put("task_type","research");submit(a,b).andExpect(status().isBadRequest());
  b=request(a,ext);b.remove("paper_ids");submit(a,b).andExpect(status().isBadRequest());
 }
 @Test void rejectsForeignCollectionAndMoreThanFiveSeeds()throws Exception {
  var a=account();var other=account();personal(a,"model");String ext="trace-"+UUID.randomUUID();paper(other,ext);var foreign=request(other,ext);submit(a,foreign).andExpect(status().isNotFound());
  paper(a,"own-"+ext);var b=request(a,"own-"+ext);b.put("paper_ids",List.of(1,2,3,4,5,6));submit(a,b).andExpect(status().isBadRequest());
 }
 @Test void citationAndSearchShareActiveQuotaAndRequirePersonalDefault()throws Exception {
  var a=account();String ext="trace-"+UUID.randomUUID();paper(a,ext);submit(a,request(a,ext)).andExpect(status().isBadRequest());personal(a,"model");String first=created(a,request(a,ext));
  var search=new LinkedHashMap<String,Object>();search.put("idempotency_key",UUID.randomUUID().toString());search.put("task_type","search");search.put("topic","emotion");search.put("mode","live");search.put("rag","none");search.put("limit",10);created(a,search);
  submit(a,request(a,ext)).andExpect(status().isTooManyRequests());jdbc.update("update pf_research_tasks set status='failed' where task_id=?",first);created(a,request(a,ext));retry(a,first,UUID.randomUUID().toString()).andExpect(status().isTooManyRequests());
 }
 @Test void legacyDtoSerializationDoesNotAddDirectionToOldRequestHash()throws Exception {
  var legacy=new cn.paperflow.dto.ResearchTaskDTO(UUID.randomUUID().toString(),"legacy","demo",3,"none",null,null,null,null);
  assertThat(json.valueToTree(legacy).has("citation_direction")).isFalse();
 }
}
