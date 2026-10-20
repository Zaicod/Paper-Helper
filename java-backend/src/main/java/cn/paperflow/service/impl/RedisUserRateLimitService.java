package cn.paperflow.service.impl;

import cn.paperflow.common.ApiException;
import cn.paperflow.service.UserRateLimitService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class RedisUserRateLimitService implements UserRateLimitService {
    private static final Logger log=LoggerFactory.getLogger(RedisUserRateLimitService.class);
    private static final DefaultRedisScript<Long> WINDOW=new DefaultRedisScript<>("""
        local count = redis.call('INCR', KEYS[1])
        if count == 1 or redis.call('PTTL', KEYS[1]) < 0 then
            redis.call('PEXPIRE', KEYS[1], ARGV[1])
        end
        if count > tonumber(ARGV[2]) then return 0 end
        return 1
        """,Long.class);
    private final StringRedisTemplate redis;
    private final boolean enabled;
    private final int searches,generations;
    private final long windowMillis;
    public RedisUserRateLimitService(StringRedisTemplate redis,
        @Value("${paperflow.redis.enabled:false}") boolean enabled,
        @Value("${paperflow.redis.search-limit:30}") int searches,
        @Value("${paperflow.redis.generation-limit:5}") int generations,
        @Value("${paperflow.redis.window-seconds:60}") long windowSeconds) {
        if(searches<1 || generations<1 || windowSeconds<1 || windowSeconds>86400)
            throw new IllegalArgumentException("Redis rate limits must be positive; window at most 86400 seconds");
        this.redis=redis;this.enabled=enabled;this.searches=searches;this.generations=generations;this.windowMillis=windowSeconds*1000;
    }
    public void search(long owner) { check(owner,"search",searches,"搜索过于频繁，请稍后重试"); }
    public void generation(long owner) { check(owner,"generation",generations,"研究任务创建过于频繁，请稍后重试"); }
    private void check(long owner,String operation,int limit,String message) {
        if(!enabled) return;
        Long allowed;
        try {
            allowed=redis.execute(WINDOW,List.of("paperflow:rate:v1:"+operation+":"+owner),String.valueOf(windowMillis),String.valueOf(limit));
        } catch(RuntimeException ex) {
            log.warn("Redis rate limit bypassed: {}",ex.getClass().getSimpleName());
            return;
        }
        if(Long.valueOf(0).equals(allowed)) throw new ApiException(HttpStatus.TOO_MANY_REQUESTS,message);
    }
}
