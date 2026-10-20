package cn.paperflow.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import cn.paperflow.common.Result;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

@Configuration
public class SecurityConfiguration {
    @Bean
    PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }

    @Bean
    HttpSessionSecurityContextRepository securityContexts() { return new HttpSessionSecurityContextRepository(); }

    @Bean
    HttpSessionCsrfTokenRepository csrfTokens() { return new HttpSessionCsrfTokenRepository(); }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, ObjectMapper json,
        HttpSessionSecurityContextRepository contexts, HttpSessionCsrfTokenRepository csrfTokens) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/csrf", "/api/auth/register", "/api/auth/login", "/api/health", "/error").permitAll()
                .anyRequest().authenticated())
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .securityContext(context -> context.securityContextRepository(contexts).requireExplicitSave(true))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) -> writeError(json, response, 401, "请先登录"))
                .accessDeniedHandler((request, response, exception) -> writeError(json, response, 403, "请求被拒绝，请刷新安全令牌后重试")))
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .requestCache(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable);
        return http.build();
    }

    private static void writeError(ObjectMapper json, HttpServletResponse response, int status, String detail) throws IOException {
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json");
        json.writeValue(response.getOutputStream(), Result.error(detail));
    }
}
