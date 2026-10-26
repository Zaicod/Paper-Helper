package cn.paperflow.client;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.net.URI;
import java.time.OffsetDateTime;
import java.text.Normalizer;
import java.util.*;

/** Validates the worker boundary before a search report reaches storage or the browser. */
final class SearchReportValidator {
    private static final Set<String> SOURCES=Set.of("arxiv","openalex","crossref");
    private SearchReportValidator() {}
    static void validate(JsonNode report) throws IOException {
        fields(report,"report_type","topic","generated_at","plan","results","searches","warnings","gaps","rounds");
        require("search_report".equals(report.path("report_type").asText()));
        text(report.path("topic"),500);text(report.path("generated_at"),100);
        try { OffsetDateTime.parse(report.path("generated_at").asText()); } catch(RuntimeException ex) { invalid(); }
        int rounds=integer(report.path("rounds"),1,2);
        var plan=report.path("plan");
        fields(plan,"summary","concepts","entities","entity_relation","constraints","queries");
        text(plan.path("summary"),2000);strings(plan.path("concepts"),1,12,500);
        strings(plan.path("constraints"),0,10,500);oneOf(plan.path("entity_relation"),Set.of("any","all"));
        array(plan.path("entities"),0,10);Map<String,List<String>> entities=new HashMap<>();
        for(var entity:plan.path("entities")) {
            fields(entity,"name","aliases");text(entity.path("name"),100);strings(entity.path("aliases"),0,8,100);
            String name=entity.path("name").asText();var aliases=new ArrayList<String>();aliases.add(name);
            entity.path("aliases").forEach(a -> aliases.add(a.asText()));require(entities.put(name,aliases)==null);
        }
        array(plan.path("queries"),1,6);
        for(var query:plan.path("queries")) {
            fields(query,"source","keywords","purpose");oneOf(query.path("source"),SOURCES);text(query.path("purpose"),500);
            array(query.path("keywords"),1,10);var words=new HashSet<String>();int length=0;
            for(var keyword:query.path("keywords")) {
                fields(keyword,"text","match_mode");text(keyword.path("text"),500);
                oneOf(keyword.path("match_mode"),Set.of("exact","fuzzy"));
                require(!"crossref".equals(query.path("source").asText()) || !"exact".equals(keyword.path("match_mode").asText()));
                String value=keyword.path("text").asText();require(words.add(value.toLowerCase(Locale.ROOT)));length+=value.length();
            }
            require(length+3*(words.size()-1)<=500);
        }
        array(report.path("results"),0,20);Set<String> ids=new HashSet<>();
        for(var result:report.path("results")) {
            fields(result,"candidate_id","paper","relevance","reason","evidence","matched_entities","modality","provenance");
            text(result.path("candidate_id"),64);require(ids.add(result.path("candidate_id").asText()));
            oneOf(result.path("relevance"),Set.of("match","uncertain","background"));text(result.path("reason"),2000);
            oneOf(result.path("modality"),Set.of("multimodal","unimodal","unknown"));
            var paper=result.path("paper");paper(paper);
            strings(result.path("evidence"),0,6,2000);strings(result.path("matched_entities"),0,10,100);
            String title=paper.path("title").asText(),abstractText=paper.path("abstract").asText();
            for(var evidence:result.path("evidence")) require(title.contains(evidence.asText()) || abstractText.contains(evidence.asText()));
            Set<String> matchedNames=new HashSet<>();
            for(var matched:result.path("matched_entities")) {
                require(matchedNames.add(matched.asText()));
                var aliases=entities.get(matched.asText());require(aliases!=null);
                boolean grounded=false;
                for(var evidence:result.path("evidence")) for(String alias:aliases)
                    if(containsAlias(evidence.asText(),alias)) grounded=true;
                require(grounded);
            }
            if("match".equals(result.path("relevance").asText())) {
                require(!result.path("evidence").isEmpty());
                if(!entities.isEmpty()) {
                    if("all".equals(plan.path("entity_relation").asText())) require(matchedNames.containsAll(entities.keySet()));
                    else require(!matchedNames.isEmpty());
                }
            }
            array(result.path("provenance"),1,6);
            for(var provenance:result.path("provenance")) {
                fields(provenance,"source","query");oneOf(provenance.path("source"),SOURCES);text(provenance.path("query"),500);
            }
        }
        array(report.path("searches"),0,6);
        for(var trace:report.path("searches")) {
            fields(trace,"round","source","query","count","status");integer(trace.path("round"),1,rounds);
            oneOf(trace.path("source"),SOURCES);text(trace.path("query"),500);integer(trace.path("count"),0,20);
            oneOf(trace.path("status"),Set.of("ok","empty","unavailable","timeout","rate_limited"));
        }
        strings(report.path("warnings"),0,20,500);strings(report.path("gaps"),0,10,500);
    }
    private static void paper(JsonNode p) throws IOException {
        require(p.isObject());
        var allowed=Set.of("source","paper_id","title","abstract","authors","categories","published","page_url","pdf_url","cited_by_count");
        for(var it=p.fieldNames();it.hasNext();) require(allowed.contains(it.next()));
        for(String key:List.of("source","paper_id","title","abstract","authors","categories","published","page_url","pdf_url")) require(p.has(key));
        if(p.hasNonNull("cited_by_count")) require(p.path("cited_by_count").isIntegralNumber() && p.path("cited_by_count").canConvertToLong() && p.path("cited_by_count").asLong()>=0);
        oneOf(p.path("source"),SOURCES);text(p.path("paper_id"),255);text(p.path("title"),1024);
        require(p.path("abstract").isTextual() && p.path("abstract").asText().length()<=10000);
        strings(p.path("authors"),0,50,128);strings(p.path("categories"),0,50,64);
        if(!p.path("published").isNull()) text(p.path("published"),64);
        url(p.path("page_url"));if(!p.path("pdf_url").isNull()) url(p.path("pdf_url"));
    }
    private static void url(JsonNode node) throws IOException {
        text(node,2048);String value=node.asText();
        require(value.codePoints().noneMatch(c -> Character.isWhitespace(c) || Character.isISOControl(c)) && !value.contains("\\"));
        try {var uri=URI.create(value);require(Set.of("http","https").contains(uri.getScheme()) && uri.getHost()!=null && uri.getUserInfo()==null);}
        catch(IllegalArgumentException ex){invalid();}
    }
    private static boolean containsAlias(String text,String alias) {
        var pattern=java.util.regex.Pattern.compile("\\w+",java.util.regex.Pattern.UNICODE_CHARACTER_CLASS);
        var matcher=pattern.matcher(normalize(alias));var terms=new ArrayList<String>();
        while(matcher.find()) terms.add(java.util.regex.Pattern.quote(matcher.group()));
        if(terms.isEmpty()) return false;
        return java.util.regex.Pattern.compile("(?<!\\w)"+String.join("[\\s_\\-‐‑–—]*",terms)+"(?!\\w)",java.util.regex.Pattern.UNICODE_CHARACTER_CLASS)
            .matcher(normalize(text)).find();
    }
    private static String normalize(String value) {
        return Normalizer.normalize(value,Normalizer.Form.NFKC).toLowerCase(Locale.ROOT);
    }
    private static void fields(JsonNode node,String... names) throws IOException {
        require(node.isObject());var allowed=Set.of(names);require(node.size()==allowed.size());
        for(String name:names) require(node.has(name));
    }
    private static void text(JsonNode node,int max) throws IOException {
        require(node.isTextual() && !node.asText().isBlank() && node.asText().length()<=max);
    }
    private static void strings(JsonNode node,int min,int max,int length) throws IOException {
        array(node,min,max);for(var item:node) text(item,length);
    }
    private static void array(JsonNode node,int min,int max) throws IOException {require(node.isArray() && node.size()>=min && node.size()<=max);}
    private static int integer(JsonNode node,int min,int max) throws IOException {
        require(node.isIntegralNumber() && node.canConvertToInt() && node.asInt()>=min && node.asInt()<=max);return node.asInt();
    }
    private static void oneOf(JsonNode node,Set<String> allowed) throws IOException {require(node.isTextual() && allowed.contains(node.asText()));}
    private static void require(boolean valid) throws IOException {if(!valid) invalid();}
    private static void invalid() throws IOException {throw new IOException("worker_invalid_search_report");}
}
