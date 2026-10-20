package cn.paperflow.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

/** Local and test profiles use servlet memory sessions and require no Redis server. */
@Configuration
@Profile("mysql")
@EnableRedisHttpSession(redisNamespace = "paperflow:java:session", maxInactiveIntervalInSeconds = 604800)
public class RedisSessionConfiguration {
    @Bean
    CookieSerializer sessionCookieSerializer(@Value("${server.servlet.session.cookie.secure:false}") boolean secure) {
        DefaultCookieSerializer cookie = new DefaultCookieSerializer();
        cookie.setCookieName("paperflow_java_session");
        cookie.setCookiePath("/");
        cookie.setUseHttpOnlyCookie(true);
        cookie.setSameSite("Lax");
        cookie.setUseSecureCookie(secure);
        return cookie;
    }
}
