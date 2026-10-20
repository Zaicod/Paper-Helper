package cn.paperflow.service.impl;

import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import cn.paperflow.dto.PaperDTO;
import cn.paperflow.dto.SearchKeywordDTO;
import com.fasterxml.jackson.core.type.TypeReference;
import cn.paperflow.service.PaperSearchService;
import cn.paperflow.vo.PaperSearchVO;
import cn.paperflow.vo.PaperSearchItemVO;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Validator;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.util.ArrayList;
import java.util.Set;
import java.util.List;
import java.util.HashSet;
import java.util.Locale;
import java.util.stream.Collectors;

/** Public literature search has no database transaction and never accepts a remote endpoint from the caller. */
@Service
public class PaperSearchServiceImpl implements PaperSearchService {
    private final WorkerClient worker;
    private final ObjectMapper json;
    private final Validator validator;
    private final cn.paperflow.service.PaperSearchCacheService cache;
    public PaperSearchServiceImpl(WorkerClient worker,ObjectMapper json,Validator validator,cn.paperflow.service.PaperSearchCacheService cache){
        this.worker=worker;this.json=json;this.validator=validator;this.cache=cache;
    }
    public PaperSearchVO search(String query,String source,int limit){
        return search(query,source,limit,null,"relevance");
    }
    public PaperSearchVO search(String query,String source,int limit,Integer page,String sort){
        return search(query,source,limit,page,sort,null);
    }
    public PaperSearchVO search(String query,String source,int limit,Integer page,String sort,String keywordJson){
        List<SearchKeywordDTO> keywords=null;
        if(keywordJson!=null){
            keywords=readKeywords(keywordJson);
            query=keywords.stream().map(SearchKeywordDTO::text).collect(Collectors.joining(" / "));
            if(page==null)page=1;
        }
        boolean exact=keywords!=null && keywords.stream().anyMatch(k->"exact".equals(k.matchMode()));
        query=query==null ? "" : query.strip();
        if(query.isEmpty() || query.length()>500 || source==null || !Set.of("auto","arxiv","openalex","crossref").contains(source) || limit<1 || limit>20)
            throw new ApiException(HttpStatus.BAD_REQUEST,"请填写 1 至 500 字符关键词，选择有效来源和 1 至 20 条结果");
        if(sort==null || !Set.of("relevance","latest","citations").contains(sort)
            || (page!=null && (page<1 || (long)page*limit>10000 || (page>1 && source.equals("auto"))
                || (source.equals("arxiv") && sort.equals("citations")))))
            throw new ApiException(HttpStatus.BAD_REQUEST,"分页或排序参数无效：翻页请固定实际来源，引用排序请选择 OpenAlex 或 Crossref");
        if(exact && source.equals("crossref"))throw new ApiException(HttpStatus.BAD_REQUEST,"Crossref 不支持当前精准匹配，请改用模糊匹配或切换来源");
        if(!worker.configured())throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"尚未配置 Python 论文检索服务");
        String cacheKey=cache.key(query,source,limit,page,sort,keywords);
        var cached=cache.get(cacheKey);
        if(cached.isPresent()) {
            try { return validatedResult(json.valueToTree(cached.get()),query,source,limit,page,sort,keywords); }
            catch(IOException | IllegalArgumentException ex) { cache.evict(cacheKey); }
        }
        try {
            var result=worker.search(query,source,limit,page,sort,keywords==null ? null : json.writeValueAsString(keywords));
            var response=validatedResult(result,query,source,limit,page,sort,keywords);
            cache.put(cacheKey,response);
            return response;
        } catch(WorkerClient.SearchFailure ex){
            if(ex.status()==504)throw timedOut();
            if(ex.status()==429)throw new ApiException(HttpStatus.TOO_MANY_REQUESTS,"论文来源请求受到限流，请稍后重试或切换来源");
            throw unavailable();
        } catch(HttpTimeoutException ex){throw timedOut();}
        catch(IOException | IllegalArgumentException ex){throw unavailable();}
        catch(InterruptedException ex){Thread.currentThread().interrupt();throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"论文检索已中断，请重试");}
    }
    // Cached and upstream data share the same contract and metadata checks.
    private PaperSearchVO validatedResult(com.fasterxml.jackson.databind.JsonNode result,String query,String source,int limit,
        Integer page,String sort,List<SearchKeywordDTO> keywords) throws IOException {
        boolean exact=keywords!=null && keywords.stream().anyMatch(k->"exact".equals(k.matchMode()));
        String used=result.path("used_source").isNull() ? null : result.path("used_source").asText();
        var papers=result.path("papers");
        if(result.path("contract_version").asInt()!=1 || !query.equals(result.path("query").asText())
            || !source.equals(result.path("requested_source").asText()) || !papers.isArray() || papers.size()>limit
            || (used!=null && !Set.of("arxiv","openalex","crossref").contains(used))
            || (used==null && !papers.isEmpty()) || (used!=null && !source.equals("auto") && !source.equals(used)))
            throw new IOException("search_contract_invalid");
        if(exact && "crossref".equals(used))throw new IOException("search_match_relaxed");
        if(keywords!=null && !keywords.equals(json.convertValue(result.path("keywords"),new TypeReference<List<SearchKeywordDTO>>(){})))
            throw new IOException("search_keywords_changed");
        Long total=null;Boolean hasNext=null;
        if(page!=null){
            var count=result.path("total");
            if(!result.path("page").isIntegralNumber() || result.path("page").asInt()!=page
                || result.path("page_size").asInt()!=limit || !sort.equals(result.path("sort").asText())
                || !count.isIntegralNumber() || !count.canConvertToLong() || count.asLong()<0
                || !result.path("has_next").isBoolean())throw new IOException("search_page_invalid");
            total=count.asLong();hasNext=result.path("has_next").asBoolean();
            if(hasNext!=((long)page*limit<Math.min(total,10000L)))throw new IOException("search_page_invalid");
            if(sort.equals("citations") && !Set.of("openalex","crossref").contains(used))throw new IOException("search_sort_invalid");
        }
        var records=new ArrayList<PaperSearchItemVO>();
        for(var node:papers){
            PaperDTO paper=json.treeToValue(node,PaperDTO.class);
            if(!validator.validate(paper).isEmpty() || !paper.source().equals(used) || !httpUrl(paper.pageUrl())
                || (paper.pdfUrl()!=null && !httpUrl(paper.pdfUrl())))throw new IOException("search_metadata_invalid");
            var cited=node.path("cited_by_count");Long citations=null;
            if(!cited.isMissingNode() && !cited.isNull()){
                if(!cited.isIntegralNumber() || !cited.canConvertToLong() || cited.asLong()<0)throw new IOException("search_citations_invalid");
                citations=cited.asLong();
            }
            records.add(PaperSearchItemVO.from(paper,citations));
        }
        var warnings=new ArrayList<PaperSearchVO.SourceWarning>();
        var remoteWarnings=result.path("warnings");
        if(!remoteWarnings.isMissingNode() && !remoteWarnings.isNull()){
            if(!remoteWarnings.isArray() || remoteWarnings.size()>3)throw new IOException("search_warnings_invalid");
            for(var warning:remoteWarnings){
                String provider=warning.path("source").asText(),code=warning.path("code").asText();
                if(!Set.of("arxiv","openalex","crossref").contains(provider)
                    || !Set.of("unavailable","rate_limited","timeout","metadata","broad_search").contains(code)
                    || (code.equals("broad_search") && !provider.equals("crossref")))
                    throw new IOException("search_warnings_invalid");
                String label=provider.equals("arxiv") ? "arXiv" : provider.equals("crossref") ? "Crossref" : "OpenAlex";
                if(code.equals("broad_search")){
                    warnings.add(new PaperSearchVO.SourceWarning(provider,code,
                        "Crossref 使用宽泛相关检索，不保证全部关键词同时命中；引用次数仅统计其收录 DOI，部分论文没有摘要或开放 PDF。"));
                    continue;
                }
                String description=switch(code){
                    case "rate_limited" -> "请求受到限流";
                    case "timeout" -> "响应超时";
                    case "metadata" -> "返回资料超出当前保存范围";
                    default -> "暂时不可用";
                };
                warnings.add(new PaperSearchVO.SourceWarning(provider,code,
                    label+" "+description+"，本次未完成该来源检索，请稍后重试或切换来源。"));
            }
        }
        return new PaperSearchVO(1,query,source,used,records,warnings,page,page==null ? null : limit,total,hasNext,page==null ? null : sort,keywords);
    }
    private List<SearchKeywordDTO> readKeywords(String raw){
        try{
            if(raw.length()>10000)throw new IllegalArgumentException();
            var nodes=json.readTree(raw);
            if(nodes==null || !nodes.isArray() || nodes.isEmpty() || nodes.size()>10)throw new IllegalArgumentException();
            for(var node:nodes){
                if(!node.isObject() || node.size()!=2 || !node.path("text").isTextual() || !node.path("match_mode").isTextual()
                    || node.path("text").asText().strip().chars().anyMatch(character -> character<32))throw new IllegalArgumentException();
            }
            List<SearchKeywordDTO> terms=json.readValue(raw,new TypeReference<List<SearchKeywordDTO>>(){});
            if(terms==null || terms.isEmpty() || terms.size()>10)throw new IllegalArgumentException();
            Set<String> seen=new HashSet<>();int length=0;
            for(var term:terms){
                if(term==null || !validator.validate(term).isEmpty() || !seen.add(term.text().toLowerCase(Locale.ROOT)))
                    throw new IllegalArgumentException();
                length+=term.text().length();
            }
            if(length+3*(terms.size()-1)>500)throw new IllegalArgumentException();
            return List.copyOf(terms);
        }catch(IOException | IllegalArgumentException ex){
            throw new ApiException(HttpStatus.BAD_REQUEST,"请选择 1 至 10 个不重复的关键词，总长度最多 500 字符，匹配方式为精准或模糊");
        }
    }
    private static boolean httpUrl(String value){
        try{
            URI url=URI.create(value);
            return ("http".equalsIgnoreCase(url.getScheme()) || "https".equalsIgnoreCase(url.getScheme()))
                && url.getHost()!=null && url.getUserInfo()==null;
        }catch(RuntimeException ex){return false;}
    }
    private static ApiException unavailable(){return new ApiException(HttpStatus.BAD_GATEWAY,"论文来源暂不可用或返回资料不完整，请更换来源或稍后重试");}
    private static ApiException timedOut(){return new ApiException(HttpStatus.GATEWAY_TIMEOUT,"论文检索超时，请更换来源或稍后重试");}
}
