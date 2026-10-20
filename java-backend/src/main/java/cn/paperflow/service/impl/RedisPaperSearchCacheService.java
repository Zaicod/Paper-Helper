package cn.paperflow.service.impl;

import cn.paperflow.dto.SearchKeywordDTO;
import cn.paperflow.service.PaperSearchCacheService;
import cn.paperflow.vo.PaperSearchVO;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;

/** Cache only validated public literature metadata; no personal notes or credentials. */
@Service
public class RedisPaperSearchCacheService implements PaperSearchCacheService {
    private static final Logger log=LoggerFactory.getLogger(RedisPaperSearchCacheService.class);
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    private final boolean enabled;
    private final long normalTtl,emptyTtl,degradedTtl;
    public RedisPaperSearchCacheService(StringRedisTemplate redis,ObjectMapper json,
        @Value("${paperflow.redis.enabled:false}") boolean enabled,
        @Value("${paperflow.redis.search-ttl-seconds:600}") long normalTtl,
        @Value("${paperflow.redis.empty-ttl-seconds:30}") long emptyTtl,
        @Value("${paperflow.redis.degraded-ttl-seconds:60}") long degradedTtl) {
        if(normalTtl<1 || emptyTtl<1 || degradedTtl<1) throw new IllegalArgumentException("Redis cache TTL must be positive");
        this.redis=redis;this.json=json;this.enabled=enabled;
        this.normalTtl=normalTtl;this.emptyTtl=emptyTtl;this.degradedTtl=degradedTtl;
    }
    public String key(String query,String source,int limit,Integer page,String sort,List<SearchKeywordDTO> keywords) {
        try {
            String request=json.writeValueAsString(Arrays.asList(query,source,limit,page,sort,keywords));
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(request.getBytes(StandardCharsets.UTF_8));
            return "paperflow:search:v1:"+HexFormat.of().formatHex(digest);
        } catch(JsonProcessingException | NoSuchAlgorithmException ex) { throw new IllegalStateException("Cannot encode search identity",ex); }
    }
    public Optional<PaperSearchVO> get(String key) {
        if(!enabled) return Optional.empty();
        try {
            String stored=redis.opsForValue().get(key);
            if(stored==null) return Optional.empty();
            try {
                var value=json.readValue(stored,PaperSearchVO.class);
                if(value!=null && value.contractVersion()==1 && value.query()!=null && value.requestedSource()!=null
                    && value.papers()!=null && value.warnings()!=null) return Optional.of(value);
            } catch(JsonProcessingException ignored) { /* Drop obsolete or malformed cache records. */ }
            redis.delete(key);
        } catch(RuntimeException ex) { log.warn("Redis search cache read bypassed: {}",ex.getClass().getSimpleName()); }
        return Optional.empty();
    }
    public void put(String key,PaperSearchVO result) {
        if(!enabled) return;
        long ttl=result.papers().isEmpty() ? emptyTtl : result.warnings().stream()
            .anyMatch(w->!"broad_search".equals(w.code())) ? degradedTtl : normalTtl;
        try { redis.opsForValue().set(key,json.writeValueAsString(result),Duration.ofSeconds(ttl)); }
        catch(JsonProcessingException | RuntimeException ex) { log.warn("Redis search cache write bypassed: {}",ex.getClass().getSimpleName()); }
    }
    public void evict(String key) {
        if(!enabled) return;
        try { redis.delete(key); }
        catch(RuntimeException ex) { log.warn("Redis invalid search cache removal bypassed: {}",ex.getClass().getSimpleName()); }
    }
}
