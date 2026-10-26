package cn.paperflow.client;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.net.URI;
import java.time.OffsetDateTime;
import java.util.*;

/** Checks bounded, attributable graph results before they reach persistence or the browser. */
final class CitationReportValidator {
 private CitationReportValidator() {}
 static void validate(JsonNode r)throws IOException {
  fields(r,"report_type","topic","generated_at","direction","seeds","results","warnings","gaps","source_requests","depth");
  require("citation_report".equals(r.path("report_type").asText()));text(r.path("topic"),500);text(r.path("generated_at"),100);
  try{OffsetDateTime.parse(r.path("generated_at").asText());}catch(RuntimeException ex){invalid();}
  choice(r.path("direction"),Set.of("both","references","citations"));number(r.path("depth"),1,1);number(r.path("source_requests"),0,20);
  array(r.path("seeds"),1,5);Map<String,JsonNode> seeds=new HashMap<>();
  for(var seed:r.path("seeds")){paper(seed,false);require(seeds.put(seed.path("paper_id").asText(),seed)==null);}
  array(r.path("results"),0,20);Set<String> candidates=new HashSet<>(),paperIds=new HashSet<>();
  for(var result:r.path("results")) {
   fields(result,"candidate_id","paper","relevance","reason","evidence","paths");text(result.path("candidate_id"),64);require(candidates.add(result.path("candidate_id").asText()));
   var p=result.path("paper");paper(p,true);String paperId=p.path("paper_id").asText();require(paperIds.add(paperId));
   require(!seeds.containsKey(paperId));choice(result.path("relevance"),Set.of("match","uncertain","background"));text(result.path("reason"),2000);strings(result.path("evidence"),0,6,2000);
   for(var evidence:result.path("evidence"))require(p.path("title").asText().contains(evidence.asText())||p.path("abstract").asText().contains(evidence.asText()));
   if("match".equals(result.path("relevance").asText()))require(!result.path("evidence").isEmpty());
   array(result.path("paths"),1,10);Set<String> paths=new HashSet<>();
   for(var path:result.path("paths")) {
    fields(path,"seed_id","seed_title","direction","from_id","to_id");text(path.path("seed_id"),255);text(path.path("seed_title"),1024);choice(path.path("direction"),Set.of("references","citations"));
    var seed=seeds.get(path.path("seed_id").asText());require(seed!=null);require(seed.path("title").asText().equals(path.path("seed_title").asText()));
    String direction=path.path("direction").asText(),from=path.path("from_id").asText(),to=path.path("to_id").asText();workId(path.path("from_id"));workId(path.path("to_id"));require(!from.equals(to));
    require("both".equals(r.path("direction").asText())||direction.equals(r.path("direction").asText()));
    boolean outgoing="references".equals(direction);require(paperId.equals(outgoing?to:from));
    if("openalex".equals(seed.path("source").asText()) && seed.path("paper_id").asText().matches("W[1-9][0-9]*"))
     require(seed.path("paper_id").asText().equals(outgoing?from:to));
    require(paths.add(path.path("seed_id").asText()+":"+direction+":"+from+":"+to));
   }
  }
  strings(r.path("warnings"),0,30,500);strings(r.path("gaps"),0,10,500);
 }
 private static void paper(JsonNode p,boolean result)throws IOException {
  require(p.isObject());var allowed=Set.of("source","paper_id","title","abstract","authors","categories","published","page_url","pdf_url","cited_by_count");
  for(var it=p.fieldNames();it.hasNext();)require(allowed.contains(it.next()));
  for(String name:List.of("source","paper_id","title","abstract","authors","categories","published","page_url","pdf_url"))require(p.has(name));
  text(p.path("source"),64);text(p.path("paper_id"),255);text(p.path("title"),1024);if(result){require("openalex".equals(p.path("source").asText()));workId(p.path("paper_id"));}
  require(p.path("abstract").isTextual()&&p.path("abstract").asText().length()<=10000);strings(p.path("authors"),0,50,128);strings(p.path("categories"),0,50,128);
  if(!p.path("published").isNull())text(p.path("published"),128);url(p.path("page_url"));if(!p.path("pdf_url").isNull())url(p.path("pdf_url"));
  if(p.hasNonNull("cited_by_count"))require(p.path("cited_by_count").isIntegralNumber()&&p.path("cited_by_count").canConvertToLong()&&p.path("cited_by_count").asLong()>=0);
 }
 private static void url(JsonNode n)throws IOException {
  text(n,2048);String s=n.asText();require(!s.contains("\\")&&s.codePoints().noneMatch(c->Character.isWhitespace(c)||Character.isISOControl(c)));
  try{var u=URI.create(s);require(Set.of("http","https").contains(u.getScheme())&&u.getHost()!=null&&u.getUserInfo()==null);}catch(IllegalArgumentException ex){invalid();}
 }
 private static void workId(JsonNode n)throws IOException{text(n,32);require(n.asText().matches("W[1-9][0-9]*"));}
 private static void fields(JsonNode n,String...names)throws IOException{require(n.isObject()&&n.size()==names.length);for(String name:names)require(n.has(name));}
 private static void choice(JsonNode n,Set<String> allowed)throws IOException{require(n.isTextual()&&allowed.contains(n.asText()));}
 private static void text(JsonNode n,int max)throws IOException{require(n.isTextual()&&!n.asText().isBlank()&&n.asText().length()<=max);}
 private static void number(JsonNode n,int min,int max)throws IOException{require(n.isIntegralNumber()&&n.canConvertToInt()&&n.asInt()>=min&&n.asInt()<=max);}
 private static void array(JsonNode n,int min,int max)throws IOException{require(n.isArray()&&n.size()>=min&&n.size()<=max);}
 private static void strings(JsonNode n,int min,int max,int len)throws IOException{array(n,min,max);for(var item:n)text(item,len);}
 private static void require(boolean ok)throws IOException{if(!ok)invalid();}
 private static void invalid()throws IOException{throw new IOException("worker_invalid_citation_report");}
}
