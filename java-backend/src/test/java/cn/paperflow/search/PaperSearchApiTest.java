package cn.paperflow.search;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @AutoConfigureMockMvc @ActiveProfiles("test")
class PaperSearchApiTest {
    static final String TOKEN="paper-search-internal-token-at-least-32";
    static final ObjectMapper wire=new ObjectMapper();
    static volatile int upstreamStatus=200;
    static volatile boolean empty,invalid,warnings,crossrefResponse;
    static volatile String receivedQuery,receivedAuth;
    static final HttpServer upstream=startUpstream();
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    static HttpServer startUpstream() {
        try {
            var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/internal/v1/papers/search",exchange -> {
                receivedQuery=exchange.getRequestURI().getRawQuery();
                receivedAuth=exchange.getRequestHeaders().getFirst("Authorization");
                Map<String,String> params=new HashMap<>();
                for(String pair:receivedQuery.split("&")) {
                    String[] parts=pair.split("=",2);
                    params.put(parts[0],java.net.URLDecoder.decode(parts[1],StandardCharsets.UTF_8));
                }
                if(!params.containsKey("query") && params.containsKey("keywords")){
                    var terms=wire.readTree(params.get("keywords"));
                    var names=new ArrayList<String>();terms.forEach(term -> names.add(term.path("text").asText()));
                    params.put("query",String.join(" / ",names));
                }
                var paper=new HashMap<String,Object>(Map.of("source","arxiv","paper_id","2401.12345", "title","Evidence grounded agents",
                    "abstract","An abstract returned by the controlled API boundary.","authors",List.of("Reader"),"categories",List.of("cs.AI"),"page_url","https://arxiv.org/abs/2401.12345"));
                if(invalid)paper.put("page_url","javascript:alert(1)");
                if(crossrefResponse){paper.put("source","crossref");paper.put("paper_id","10.1234/study");paper.put("cited_by_count",321);}
                var response=new HashMap<String,Object>(Map.of("contract_version",1,"query",params.get("query"),
                    "requested_source",params.get("source"),"used_source","arxiv","papers",empty ? List.of() : List.of(paper),
                    "warnings",warnings ? List.of(Map.of("source","openalex","code","rate_limited","message","raw-secret-stack-never-show")) : List.of()));
                if(crossrefResponse){
                    response.put("used_source","crossref");
                    response.put("warnings",List.of(Map.of("source","crossref","code","broad_search","message","raw-secret-stack-never-show")));
                }
                if(params.containsKey("keywords"))response.put("keywords",wire.readTree(params.get("keywords")));
                if(params.containsKey("page")){
                    response.put("page",Integer.parseInt(params.get("page")));response.put("page_size",Integer.parseInt(params.get("limit")));
                    response.put("total",35);response.put("has_next",true);response.put("sort",params.get("sort"));
                }
                byte[] body=wire.writeValueAsBytes(upstreamStatus==200 ? response : Map.of("detail","raw-secret-stack-never-show"));
                exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(upstreamStatus,body.length);
                try(var output=exchange.getResponseBody()){output.write(body);}
            });
            server.start(); return server;
        }catch(IOException ex){throw new RuntimeException(ex);}
    }
    @DynamicPropertySource static void configure(DynamicPropertyRegistry p) {
        p.add("paperflow.worker.base-url",()->"http://127.0.0.1:"+upstream.getAddress().getPort());
        p.add("paperflow.worker.token",()->TOKEN);
        p.add("paperflow.worker.scheduling-enabled",()->"false");
    }
    @BeforeEach void reset(){upstreamStatus=200;empty=false;invalid=false;warnings=false;crossrefResponse=false;receivedQuery=null;receivedAuth=null;}
    @AfterAll static void stop(){upstream.stop(0);}
    @Test void structuredTermsDoNotNeedDuplicatedDisplayQuery() throws Exception {
        String terms=json.writeValueAsString(List.of(Map.of("text","中".repeat(500),"match_mode","fuzzy")));
        mvc.perform(get("/api/papers/search").session(user()).param("source","arxiv").param("keywords",terms))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.query").value("中".repeat(500)));
        assertThat(receivedQuery).doesNotContain("query=");
    }
    @Test void structuredKeywordsPreserveModesAndRejectInvalidOrDuplicateTerms() throws Exception {
        var user=user();String terms="[{\"text\":\"multimodal learning\",\"match_mode\":\"exact\"},{\"text\":\"retrieval\",\"match_mode\":\"fuzzy\"}]";
        mvc.perform(get("/api/papers/search").session(user).param("query","multimodal learning / retrieval")
            .param("source","arxiv").param("page","1").param("keywords",terms))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.keywords[0].match_mode").value("exact"))
            .andExpect(jsonPath("$.data.keywords[1].text").value("retrieval"));
        assertThat(receivedQuery).contains("keywords=%5B").doesNotContain("multimodal learning");
        for(String bad:List.of("[]","not-json","[null]","[{\"text\":\"a\",\"match_mode\":\"regex\"}]",
            "[{\"text\":123,\"match_mode\":\"fuzzy\"}]","[{\"text\":\"a\",\"match_mode\":\"fuzzy\",\"raw_query\":true}]",
            "[{\"text\":\"a\\nb\",\"match_mode\":\"fuzzy\"}]",
            "[{\"text\":\"RAG\",\"match_mode\":\"exact\"},{\"text\":\"rag\",\"match_mode\":\"fuzzy\"}]")){
            mvc.perform(get("/api/papers/search").session(user).param("query","x").param("keywords",bad))
                .andExpect(status().isBadRequest());
        }
    }
    @Test void crossrefCitationsRemainDistinctAndExactIsNotSilentlyRelaxed() throws Exception {
        crossrefResponse=true;
        var user=user();
        mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("source","crossref")
            .param("page","1").param("sort","citations").param("keywords","[{\"text\":\"agents\",\"match_mode\":\"fuzzy\"}]"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.used_source").value("crossref"))
            .andExpect(jsonPath("$.data.papers[0].cited_by_count").value(321))
            .andExpect(jsonPath("$.data.warnings[0].code").value("broad_search"))
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("raw-secret"))));
        mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("source","crossref")
            .param("page","1").param("keywords","[{\"text\":\"agents\",\"match_mode\":\"exact\"}]"))
            .andExpect(status().isBadRequest());
    }
    @Test void pagingForwardsProviderSortAndRejectsUnsupportedCombinations() throws Exception {
        var user=user();
        mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("source","arxiv")
            .param("page","2").param("limit","10").param("sort","relevance"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.page").value(2))
            .andExpect(jsonPath("$.data.total").value(35)).andExpect(jsonPath("$.data.has_next").value(true));
        assertThat(receivedQuery).contains("page=2","sort=relevance");
        mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("source","auto").param("page","2"))
            .andExpect(status().isBadRequest());
        mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("source","arxiv").param("page","1").param("sort","citations"))
            .andExpect(status().isBadRequest());
    }
    @Test void searchRequiresLoginAndValidBoundedParameters() throws Exception {
        mvc.perform(get("/api/papers/search").param("query","agents")).andExpect(status().isUnauthorized());
        var user=user();
        for(String query:List.of(" ","x".repeat(501))) mvc.perform(get("/api/papers/search").session(user).param("query",query)).andExpect(status().isBadRequest());
        mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("source","https://evil.test")).andExpect(status().isBadRequest());
        for(String limit:List.of("0","21","abc")) mvc.perform(get("/api/papers/search").session(user).param("query","agents").param("limit",limit)).andExpect(status().isBadRequest());
        assertThat(receivedQuery).isNull();
    }
    @Test void authenticatedSearchEncodesQueryUsesServiceIdentityAndReturnsMetadata() throws Exception {
        var user=user();
        mvc.perform(get("/api/papers/search").session(user).param("query","  RAG & 证据  ").param("source","arxiv").param("limit","5"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.code").value(1))
            .andExpect(jsonPath("$.data.query").value("RAG & 证据"))
            .andExpect(jsonPath("$.data.papers[0].paper_id").value("2401.12345"))
            .andExpect(jsonPath("$.data.papers[0].abstract").isNotEmpty());
        assertThat(receivedAuth).isEqualTo("Bearer "+TOKEN);
        assertThat(receivedQuery).contains("source=arxiv","limit=5").doesNotContain("证据");
    }
    @Test void emptySearchIsSuccessfulButUnsafeUpstreamMetadataIsRejected() throws Exception {
        var user=user();empty=true;
        mvc.perform(get("/api/papers/search").session(user).param("query","no-match")).andExpect(status().isOk()).andExpect(jsonPath("$.data.papers").isEmpty());
        empty=false;invalid=true;
        mvc.perform(get("/api/papers/search").session(user).param("query","agents")).andExpect(status().isBadGateway())
            .andExpect(jsonPath("$.code").value(0));
    }
    @Test void remoteFailureAndTimeoutReturnSafeErrors() throws Exception {
        var user=user();
        for(int remote:List.of(502,504,429)) {
            upstreamStatus=remote;
            var result=mvc.perform(get("/api/papers/search").session(user).param("query","agents"))
                .andExpect(status().is(remote)).andExpect(jsonPath("$.code").value(0)).andReturn();
            assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8)).doesNotContain("raw-secret",TOKEN);
        }
    }
    @Test void emptyResultsRetainSafeSourceWarnings() throws Exception {
        empty=true;warnings=true;
        var result=mvc.perform(get("/api/papers/search").session(user()).param("query","multimodal"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.papers").isEmpty())
            .andExpect(jsonPath("$.data.warnings[0].source").value("openalex"))
            .andExpect(jsonPath("$.data.warnings[0].code").value("rate_limited")).andReturn();
        assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8)).doesNotContain("raw-secret");
    }
    private MockHttpSession user() throws Exception {
        String name="search_"+UUID.randomUUID().toString().replace("-","");
        var result=mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json").content(json.writeValueAsBytes(
            Map.of("username",name,"email",name+"@example.test","password","test-password-123"))))
            .andExpect(status().isCreated()).andReturn();
        return (MockHttpSession)result.getRequest().getSession(false);
    }
}
