package cn.paperflow.research;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import org.junit.jupiter.api.Test;
class CitationReportContractTest {
 final ObjectMapper json=new ObjectMapper();
 ObjectNode report()throws Exception{return (ObjectNode)json.readTree("""
 {"report_type":"citation_report","topic":"emotion","generated_at":"2026-10-26T00:00:00Z","direction":"both","depth":1,"source_requests":3,
 "seeds":[{"source":"manual","paper_id":"seed","title":"Seed paper","abstract":"","authors":[],"categories":[],"published":null,"page_url":"https://doi.org/10.1000/seed","pdf_url":null}],
 "results":[{"candidate_id":"c1","paper":{"source":"openalex","paper_id":"W2","title":"Emotion study","abstract":"EEG fusion","authors":[],"categories":[],"published":null,"page_url":"https://openalex.org/W2","pdf_url":null},"relevance":"match","reason":"Related topic","evidence":["EEG fusion"],"paths":[{"seed_id":"seed","seed_title":"Seed paper","direction":"references","from_id":"W1","to_id":"W2"}]}],"warnings":[],"gaps":[]}
 """);}
 void exchange(JsonNode r,boolean valid)throws Exception{new IntelligentSearchContractTest().exchange(r,valid);}
 @Test void acceptsCitationReportIncludingEmptyResults()throws Exception{exchange(report(),true);var r=report();r.putArray("results");exchange(r,true);}
 @Test void acceptsOpenAlexArxivSeedMappedByDoiButStillChecksCanonicalWorkSeeds()throws Exception {
  var r=report();var seed=(ObjectNode)r.path("seeds").get(0);seed.put("source","openalex");seed.put("paper_id","2401.00001");seed.put("page_url","https://doi.org/10.48550/arxiv.2401.00001");
  ((ObjectNode)r.path("results").get(0).path("paths").get(0)).put("seed_id","2401.00001");exchange(r,true);
  seed.put("paper_id","W9");((ObjectNode)r.path("results").get(0).path("paths").get(0)).put("seed_id","W9");exchange(r,false);
 }
 @Test void rejectsFalseEvidenceForeignSeedsAndInvalidEdges()throws Exception{
  var r=report();((ObjectNode)r.path("results").get(0)).putArray("evidence").add("invented");exchange(r,false);
  r=report();((ObjectNode)r.path("results").get(0).path("paths").get(0)).put("seed_id","foreign");exchange(r,false);
  r=report();((ObjectNode)r.path("results").get(0).path("paths").get(0)).put("from_id","https://evil.test/W1");exchange(r,false);
  r=report();r.put("direction","citations");exchange(r,false);
  r=report();((ObjectNode)r.path("results").get(0).path("paths").get(0)).put("to_id","W3");exchange(r,false);
  r=report();r.put("source_requests",21);exchange(r,false);r=report();r.put("depth",2);exchange(r,false);
 }
}
