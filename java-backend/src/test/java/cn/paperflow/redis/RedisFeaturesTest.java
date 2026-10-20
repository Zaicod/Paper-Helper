package cn.paperflow.redis;

import cn.paperflow.service.impl.RedisPaperSearchCacheService;
import cn.paperflow.service.impl.RedisUserRateLimitService;
import cn.paperflow.vo.PaperSearchVO;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.RedisConnectionFailureException;
import java.time.Duration;
import java.util.List;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class RedisFeaturesTest {
    final StringRedisTemplate redis=mock(StringRedisTemplate.class);
    @SuppressWarnings("unchecked") final ValueOperations<String,String> values=mock(ValueOperations.class);
    final ObjectMapper json=new ObjectMapper().findAndRegisterModules();
    RedisPaperSearchCacheService cache(boolean enabled) {
        when(redis.opsForValue()).thenReturn(values);
        return new RedisPaperSearchCacheService(redis,json,enabled,600,30,60);
    }
    PaperSearchVO response(List<PaperSearchVO.SourceWarning> warnings) {
        return new PaperSearchVO(1,"Agent","auto","arxiv",List.of(),warnings,1,10,0L,false,"relevance",null);
    }
    @Test void cacheRoundTripsPublicResponseAndUsesShortExpiryForEmptyResults() throws Exception {
        var cache=cache(true);var result=response(List.of());
        cache.put("paperflow:search:v1:hash",result);
        verify(values).set(eq("paperflow:search:v1:hash"),eq(json.writeValueAsString(result)),eq(Duration.ofSeconds(30)));
        when(values.get("key")).thenReturn(json.writeValueAsString(result));
        assertThat(cache.get("key")).contains(result);
    }
    @Test void cacheKeySeparatesEverySearchDimensionWithoutExposingKeywords() {
        var cache=cache(false);
        String first=cache.key("Agent","auto",10,1,"relevance",null);
        assertThat(first).startsWith("paperflow:search:v1:").doesNotContain("Agent");
        assertThat(List.of(
            cache.key("Agent","arxiv",10,1,"relevance",null),
            cache.key("Agent","auto",20,1,"relevance",null),
            cache.key("Agent","auto",10,null,"relevance",null),
            cache.key("Agent","auto",10,2,"relevance",null),
            cache.key("Agent","auto",10,1,"latest",null),
            cache.key("Other","auto",10,1,"relevance",null),
            cache.key("Agent","auto",10,1,"relevance",List.of(new cn.paperflow.dto.SearchKeywordDTO("Agent","exact"))),
            cache.key("Agent","auto",10,1,"relevance",List.of(new cn.paperflow.dto.SearchKeywordDTO("Agent","fuzzy")))
        )).doesNotContain(first).doesNotHaveDuplicates();
        assertThat(cache.key("Agent","auto",10,1,"relevance",null)).isEqualTo(first);
        assertThat(cache.get(first)).isEmpty();cache.put(first,response(List.of()));
        verifyNoInteractions(values);
    }
    @Test void ignoresCorruptedCacheAndRedisReadWriteFailures() {
        var cache=cache(true);
        when(values.get("broken")).thenReturn("not-json");
        assertThat(cache.get("broken")).isEmpty();verify(redis).delete("broken");
        when(values.get("offline")).thenThrow(new RedisConnectionFailureException("sensitive-details"));
        assertThat(cache.get("offline")).isEmpty();
        doThrow(new RedisConnectionFailureException("sensitive-details")).when(values).set(anyString(),anyString(),any(Duration.class));
        assertThatCode(()->cache.put("offline",response(List.of()))).doesNotThrowAnyException();
    }
    @Test void disabledLimiterNeverConnectsToRedis() {
        var limiter=new RedisUserRateLimitService(redis,false,30,5,60);
        limiter.search(1);limiter.generation(1);verifyNoInteractions(redis);
    }
    @Test void normalAndDegradedResultsHaveDifferentExpiryAndBroadSearchIsInformational() {
        var cache=cache(true);
        var paper=new cn.paperflow.vo.PaperSearchItemVO("arxiv","id","Title","Abstract",List.of(),List.of(),null,"https://arxiv.org/abs/id",null,null);
        for(String code:List.of("normal","broad_search","timeout")) {
            var warnings=code.equals("normal") ? List.<PaperSearchVO.SourceWarning>of() : List.of(new PaperSearchVO.SourceWarning("crossref",code,"notice"));
            var result=new PaperSearchVO(1,"Agent","auto","arxiv",List.of(paper),warnings,1,10,1L,false,"relevance",null);
            cache.put(code,result);
            verify(values).set(eq(code),anyString(),eq(Duration.ofSeconds(code.equals("timeout")?60:600)));
        }
    }
    @Test void enabledLimiterFailsOpenWhenRedisIsOffline() {
        var limiter=new RedisUserRateLimitService(redis,true,30,5,60);
        doThrow(new RedisConnectionFailureException("private-connection-string")).when(redis)
            .execute(any(org.springframework.data.redis.core.script.RedisScript.class),anyList(),any(),any());
        assertThatCode(()->limiter.search(1)).doesNotThrowAnyException();
        assertThatCode(()->limiter.generation(1)).doesNotThrowAnyException();
    }
}
