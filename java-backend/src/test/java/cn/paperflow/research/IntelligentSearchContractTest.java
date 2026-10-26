package cn.paperflow.research;
import cn.paperflow.client.WorkerClient;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.io.IOException;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
class IntelligentSearchContractTest {
 final ObjectMapper json=new ObjectMapper();
 ObjectNode report() throws Exception {return (ObjectNode)json.readTree("""
 {"report_type":"search_report","topic":"emotion","generated_at":"2026-10-24T00:00:00Z","rounds":1,
 "plan":{"summary":"Find evidence","concepts":["emotion"],"entities":[{"name":"SEED-IV","aliases":["SEED-IV"]}],"entity_relation":"any","constraints":[],"queries":[{"source":"arxiv","keywords":[{"text":"SEED-IV","match_mode":"fuzzy"}],"purpose":"dataset"}]},
 "results":[{"candidate_id":"c1","paper":{"source":"arxiv","paper_id":"2401.12345","title":"SEED-IV emotion","abstract":"EEG and eye movement fusion","authors":[],"categories":[],"published":null,"page_url":"https://arxiv.org/abs/2401.12345","pdf_url":null},"relevance":"match","reason":"Metadata mentions dataset","evidence":["SEED-IV"],"matched_entities":["SEED-IV"],"modality":"multimodal","provenance":[{"source":"arxiv","query":"SEED-IV"}]}],
 "searches":[{"round":1,"source":"arxiv","query":"SEED-IV","count":1,"status":"ok"}],"warnings":[],"gaps":[]}
 """);}
 void exchange(JsonNode report,boolean valid) throws Exception {
  String id=UUID.randomUUID().toString();var body=json.createObjectNode();body.put("contract_version",1);body.put("task_id",id);body.put("status","completed");body.putArray("events");body.set("report",report);
  var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);server.createContext("/internal/v1/tasks/",ex->{byte[] bytes=json.writeValueAsBytes(body);ex.sendResponseHeaders(200,bytes.length);try(var out=ex.getResponseBody()){out.write(bytes);}});server.start();
  try{var client=new WorkerClient(json,"http://127.0.0.1:"+server.getAddress().getPort(),"test-token-with-at-least-32-characters",2);if(valid)assertThat(client.exchange(id,"running","{}").path("report")).isEqualTo(report);else assertThatThrownBy(()->client.exchange(id,"running","{}")).isInstanceOf(IOException.class);}finally{server.stop(0);}
 }
 @Test void acceptsGroundedSearchReportAndEmptyResults() throws Exception {exchange(report(),true);var r=report();r.putArray("results");exchange(r,true);}
 @Test void acceptsProviderCitationCountsAndPunctuationVariants() throws Exception {
  var r=report();((ObjectNode)r.path("results").get(0).path("paper")).put("cited_by_count",15).put("title","SEED IV emotion");((ObjectNode)r.path("results").get(0)).putArray("evidence").add("SEED IV");exchange(r,true);
 }
 @Test void rejectsUnsafeLinksFalseEvidenceFalseEntitiesAndDuplicateIds() throws Exception {
  var r=report();((ObjectNode)r.path("results").get(0).path("paper")).put("page_url","javascript:alert(1)");exchange(r,false);
  r=report();((ObjectNode)r.path("results").get(0)).putArray("evidence").add("invented");exchange(r,false);
  r=report();((ObjectNode)r.path("results").get(0)).putArray("matched_entities").add("SEED-VII");exchange(r,false);
  r=report();((ArrayNode)r.path("results")).add(r.path("results").get(0).deepCopy());exchange(r,false);
 }
 @Test void rejectsExcessiveRoundsAndTracesUnknownReportTypeAndBadDate() throws Exception {
  var r=report();r.put("rounds",3);exchange(r,false);r=report();for(int i=0;i<6;i++)((ArrayNode)r.path("searches")).add(r.path("searches").get(0).deepCopy());exchange(r,false);
  r=report();r.put("report_type","invented");r.putArray("papers");r.putArray("analyses");r.putObject("synthesis");r.putObject("idea_portfolio");exchange(r,false);
  r=report();r.put("generated_at","not-a-date");exchange(r,false);
 }
 @Test void rejectsDuplicateMatchedEntities() throws Exception {
  var r=report();((ArrayNode)r.path("results").get(0).path("matched_entities")).add("SEED-IV");exchange(r,false);
 }
 @Test void allRelationRequiresEvidenceForEveryDistinctEntity() throws Exception {
  var r=report();((ObjectNode)r.path("plan")).put("entity_relation","all");
  var entity=((ArrayNode)r.path("plan").path("entities")).addObject();entity.put("name","SEED-VII");entity.putArray("aliases").add("SEED-VII");
  exchange(r,false);
  var result=(ObjectNode)r.path("results").get(0);result.put("relevance","uncertain");exchange(r,true);
  result.put("relevance","match");((ObjectNode)result.path("paper")).put("title","SEED-IV and SEED-VII emotion");
  ((ArrayNode)result.path("evidence")).add("SEED-VII");((ArrayNode)result.path("matched_entities")).add("SEED-VII");exchange(r,true);
 }
 @Test void matchRequiresEvidenceAndRequestedEntityWhileUncertainMayHaveNone() throws Exception {
  var r=report();var result=(ObjectNode)r.path("results").get(0);result.putArray("matched_entities");exchange(r,false);
  result.putArray("evidence");exchange(r,false);result.put("relevance","uncertain");exchange(r,true);
  result.put("relevance","match");((ObjectNode)r.path("plan")).putArray("entities");exchange(r,false);
 }
}
