package cn.paperflow.redis;

import cn.paperflow.service.PaperSearchCacheService;
import cn.paperflow.service.impl.RedisUserRateLimitService;
import cn.paperflow.common.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Opt-in: uses a dedicated Redis port, never FLUSHDB or the developer's Redis data. */
@SpringBootTest(properties={"paperflow.redis.enabled=true","paperflow.redis.search-limit=3","paperflow.redis.generation-limit=1","paperflow.worker.scheduling-enabled=false"})
@AutoConfigureMockMvc @ActiveProfiles("test")
@EnabledIfEnvironmentVariable(named="PAPERFLOW_TEST_REDIS_PORT",matches="\\d+")
class RedisWorkflowApiTest {
    static final AtomicInteger calls=new AtomicInteger();
    static volatile int upstreamCode=200;
    static final ObjectMapper wire=new ObjectMapper();
    static final HttpServer upstream=start();
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired StringRedisTemplate redis;
    @Autowired PaperSearchCacheService cache;
    static HttpServer start() {
        try {
            var server=HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/internal/v1/papers/search",exchange->{
                calls.incrementAndGet();var params=new HashMap<String,String>();
                for(String pair:exchange.getRequestURI().getRawQuery().split("&")) {
                    var parts=pair.split("=",2);params.put(parts[0],java.net.URLDecoder.decode(parts[1],StandardCharsets.UTF_8));
                }
                var paper=Map.of("source","arxiv","paper_id","2401.12345","title","Controlled paper","abstract","Evidence", "authors",List.of("Reader"),"categories",List.of("cs.AI"),"page_url","https://arxiv.org/abs/2401.12345");
                var result=new HashMap<String,Object>(Map.of("contract_version",1,"query",params.get("query"),"requested_source",params.get("source"),"used_source","arxiv","papers",List.of(paper),"warnings",List.of()));
                if(params.containsKey("page")) {
                    result.put("page",Integer.parseInt(params.get("page")));result.put("page_size",Integer.parseInt(params.get("limit")));
                    result.put("sort",params.get("sort"));result.put("total",1);result.put("has_next",false);
                }
                byte[] bytes=wire.writeValueAsBytes(result);exchange.getResponseHeaders().set("Content-Type","application/json");
                exchange.sendResponseHeaders(upstreamCode,bytes.length);try(var out=exchange.getResponseBody()){out.write(bytes);}
            });server.start();return server;
        }catch(Exception ex){throw new RuntimeException(ex);}
    }
    @DynamicPropertySource static void config(DynamicPropertyRegistry p) {
        p.add("spring.data.redis.host",()->"127.0.0.1");
        p.add("spring.data.redis.port",()->System.getenv("PAPERFLOW_TEST_REDIS_PORT"));
        p.add("paperflow.worker.base-url",()->"http://127.0.0.1:"+upstream.getAddress().getPort());
        p.add("paperflow.worker.token",()->"redis-test-internal-token-at-least-32-characters");
    }
    @AfterAll static void stop(){upstream.stop(0);}
    @AfterEach void reset(){upstreamCode=200;}
    MockHttpSession account() throws Exception {
        String name="r"+UUID.randomUUID().toString().replace("-", "");
        var result=mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json")
            .content(json.writeValueAsBytes(Map.of("username",name,"email",name+"@example.test","password","testing-pass-123"))))
            .andExpect(status().isCreated()).andReturn();
        return (MockHttpSession)result.getRequest().getSession(false);
    }
    @Test void cacheSkipsWorkerAndLimitsSearchPerAccountIncludingCacheHits() throws Exception {
        var a=account();var b=account();String query="Redis-"+UUID.randomUUID();int before=calls.get();
        for(int i=0;i<3;i++) mvc.perform(get("/api/papers/search").session(a).param("query",query)).andExpect(status().isOk());
        assertThat(calls.get()-before).isEqualTo(1);
        mvc.perform(get("/api/papers/search").session(a).param("query",query)).andExpect(status().isTooManyRequests())
            .andExpect(jsonPath("$.msg").value("搜索过于频繁，请稍后重试"));
        mvc.perform(get("/api/papers/search").session(b).param("query",query)).andExpect(status().isOk());
        assertThat(calls.get()-before).isEqualTo(1);
        String key=cache.key(query,"auto",10,null,"relevance",null);
        assertThat(redis.getExpire(key)).isBetween(590L,600L);redis.delete(key);
    }
    @Test void taskIdempotencyDoesNotSpendQuotaAndRetrySharesNewTaskQuota() throws Exception {
        var a=account();var b=account();
        var body=new HashMap<String,Object>(Map.of("idempotency_key",UUID.randomUUID().toString(),"topic","Redis tasks","mode","demo"));
        var first=mvc.perform(post("/api/research/tasks").session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body)))
            .andExpect(status().isAccepted()).andReturn();
        String id=json.readTree(first.getResponse().getContentAsByteArray()).path("data").path("task_id").asText();
        mvc.perform(post("/api/research/tasks").session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body)))
            .andExpect(status().isAccepted()).andExpect(jsonPath("$.data.task_id").value(id));
        body.put("idempotency_key",UUID.randomUUID().toString());
        mvc.perform(post("/api/research/tasks").session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body)))
            .andExpect(status().isTooManyRequests());
        mvc.perform(post("/api/research/tasks").session(b).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body)))
            .andExpect(status().isAccepted());
        jdbc.update("UPDATE pf_research_tasks SET status='failed' WHERE task_id=?",id);
        mvc.perform(post("/api/research/tasks/{id}/retry",id).session(a).with(csrf()).contentType("application/json")
            .content(json.writeValueAsBytes(Map.of("idempotency_key",UUID.randomUUID().toString())))).andExpect(status().isTooManyRequests());
        long owner=jdbc.queryForObject("SELECT owner_id FROM pf_research_tasks WHERE task_id=?",Long.class,id);
        String rateKey="paperflow:rate:v1:generation:"+owner;
        redis.delete(rateKey); // Simulate the next window for this test account only.
        byte[] retry=json.writeValueAsBytes(Map.of("idempotency_key",UUID.randomUUID().toString()));
        String retried=null;
        for(int i=0;i<2;i++) {
            var result=mvc.perform(post("/api/research/tasks/{id}/retry",id).session(a).with(csrf()).contentType("application/json").content(retry))
                .andExpect(status().isAccepted()).andReturn();
            String returned=json.readTree(result.getResponse().getContentAsByteArray()).path("data").path("task_id").asText();
            if(retried!=null)assertThat(returned).isEqualTo(retried);
            retried=returned;
        }
        assertThat(redis.opsForValue().get(rateKey)).isEqualTo("1");
    }
    @Test void realLuaIsAtomicUnderConcurrencyAndExpires() throws Exception {
        long owner=Math.abs(UUID.randomUUID().getMostSignificantBits());
        var limiter=new RedisUserRateLimitService(redis,true,4,1,1);
        var accepted=new AtomicInteger();
        try(var pool=Executors.newFixedThreadPool(12)) {
            var futures=new ArrayList<Future<?>>();
            for(int i=0;i<12;i++) futures.add(pool.submit(()->{try{limiter.search(owner);accepted.incrementAndGet();}catch(ApiException expected){}}));
            for(var future:futures)future.get(5,TimeUnit.SECONDS);
        }
        assertThat(accepted.get()).isEqualTo(4);
        String key="paperflow:rate:v1:search:"+owner;
        assertThat(redis.getExpire(key,TimeUnit.MILLISECONDS)).isBetween(1L,1000L);
        Thread.sleep(1100);
        assertThatCode(()->limiter.search(owner)).doesNotThrowAnyException();redis.delete(key);
    }
    @Test void failedSearchIsNotCachedAndInvalidInputNeverReachesWorker() throws Exception {
        var a=account();String query="failure-"+UUID.randomUUID();int before=calls.get();
        mvc.perform(get("/api/papers/search").session(a).param("query"," ")).andExpect(status().isBadRequest());
        assertThat(calls.get()).isEqualTo(before);
        upstreamCode=502;
        for(int i=0;i<2;i++) mvc.perform(get("/api/papers/search").session(a).param("query",query)).andExpect(status().isBadGateway());
        assertThat(calls.get()-before).isEqualTo(2);
        assertThat(cache.get(cache.key(query,"auto",10,null,"relevance",null))).isEmpty();
    }
    @Test void invalidTaskDoesNotSpendGenerationQuota() throws Exception {
        var a=account();
        var body=new HashMap<String,Object>(Map.of("idempotency_key",UUID.randomUUID().toString(),"topic","Invalid collection","mode","demo","collection_id",99999999));
        mvc.perform(post("/api/research/tasks").session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body)))
            .andExpect(status().isNotFound());
        body.remove("collection_id");
        mvc.perform(post("/api/research/tasks").session(a).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(body)))
            .andExpect(status().isAccepted());
    }
    @Test void semanticallyBrokenCacheIsRemovedAndReloadedInsteadOfReturned() throws Exception {
        for(String corruption:List.of("null-paper","missing-page","wrong-query")) {
            var a=account();String query="corrupt-"+UUID.randomUUID();
            mvc.perform(get("/api/papers/search").session(a).param("query",query).param("page","1")).andExpect(status().isOk());
            String key=cache.key(query,"auto",10,1,"relevance",null);
            var stored=(com.fasterxml.jackson.databind.node.ObjectNode)json.readTree(redis.opsForValue().get(key));
            if(corruption.equals("null-paper"))stored.putArray("papers").addNull();
            if(corruption.equals("missing-page"))stored.remove("page");
            if(corruption.equals("wrong-query"))stored.put("query","another query");
            redis.opsForValue().set(key,json.writeValueAsString(stored));int before=calls.get();
            mvc.perform(get("/api/papers/search").session(a).param("query",query).param("page","1"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.query").value(query))
                .andExpect(jsonPath("$.data.page").value(1)).andExpect(jsonPath("$.data.papers[0].title").value("Controlled paper"));
            assertThat(calls.get()-before).isEqualTo(1);redis.delete(key);
        }
    }
}
