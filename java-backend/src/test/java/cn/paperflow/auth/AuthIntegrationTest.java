package cn.paperflow.auth;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;
import java.io.ByteArrayOutputStream;
import java.io.ObjectOutputStream;
import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    private String suffix;

    @BeforeEach void uniqueAccount() { suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 12); }

    @Test void registerAuthenticatesSessionAndNeverExposesPassword() throws Exception {
        SessionToken csrf = csrf(null);
        MvcResult result = register(csrf, "Reader" + suffix, suffix + "@Example.com", "good-password")
            .andExpect(status().isCreated()).andExpect(jsonPath("$.data.username").value("Reader" + suffix))
            .andExpect(jsonPath("$.data.password_hash").doesNotExist()).andReturn();
        MockHttpSession session = (MockHttpSession) result.getRequest().getSession(false);
        mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.email").value(suffix + "@Example.com"))
            .andExpect(jsonPath("$.data.id").isNumber());
        String hash = jdbc.queryForObject("select password_hash from pf_users where username_normalized = ?", String.class,
            "reader" + suffix);
        assertThat(hash).startsWith("$2").isNotEqualTo("good-password");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(session.getAttribute("SPRING_SECURITY_CONTEXT"));
        }
        assertThat(bytes.toString(StandardCharsets.ISO_8859_1)).doesNotContain("good-password", hash);
    }

    @Test void registrationRejectsNormalizedDuplicateUsernameAndEmail() throws Exception {
        register(csrf(null), "Reader" + suffix, suffix + "@Example.com", "good-password").andExpect(status().isCreated());
        register(csrf(null), "  READER" + suffix + "  ", "other" + suffix + "@example.com", "good-password")
            .andExpect(status().isConflict());
        register(csrf(null), "other" + suffix, "  " + suffix + "@EXAMPLE.COM  ", "good-password")
            .andExpect(status().isConflict());
    }

    @Test void loginAcceptsCaseInsensitiveUsernameAndEmail() throws Exception {
        register(csrf(null), "Reader" + suffix, suffix + "@Example.com", "good-password").andExpect(status().isCreated());
        for (String identifier : new String[]{"  READER" + suffix + " ", suffix + "@EXAMPLE.COM"}) {
            SessionToken token = csrf(null);
            MvcResult result = login(token, identifier, "good-password").andExpect(status().isOk()).andReturn();
            mvc.perform(get("/api/auth/me").session((MockHttpSession) result.getRequest().getSession(false)))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.username").value("Reader" + suffix));
        }
    }

    @Test void badCredentialsReturnSameSafeResponse() throws Exception {
        register(csrf(null), "Reader" + suffix, suffix + "@example.com", "good-password").andExpect(status().isCreated());
        String wrong = login(csrf(null), "Reader" + suffix, "wrong-password").andExpect(status().isUnauthorized())
            .andReturn().getResponse().getContentAsString();
        String missing = login(csrf(null), "missing" + suffix, "wrong-password").andExpect(status().isUnauthorized())
            .andReturn().getResponse().getContentAsString();
        assertThat(wrong).isEqualTo(missing).contains("msg").doesNotContain("Exception", "password_hash");
    }

    @Test void anonymousProfileReturnsJsonUnauthorized() throws Exception {
        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized()).andExpect(jsonPath("$.msg").isString());
    }

    @Test void everyUnsafeAuthenticationEndpointRequiresCsrf() throws Exception {
        for (String endpoint : new String[]{"register", "login", "logout"}) {
            mvc.perform(post("/api/auth/" + endpoint).contentType("application/json").content("{}"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.msg").isString());
        }
    }

    @Test void successfulLoginRotatesSessionAndInvalidatesOldCsrfToken() throws Exception {
        register(csrf(null), "Reader" + suffix, suffix + "@example.com", "good-password").andExpect(status().isCreated());
        SessionToken before = csrf(null);
        String oldId = before.session().getId();
        MvcResult loggedIn = login(before, "Reader" + suffix, "good-password").andExpect(status().isOk()).andReturn();
        MockHttpSession current = (MockHttpSession) loggedIn.getRequest().getSession(false);
        assertThat(current.getId()).isNotEqualTo(oldId);
        mvc.perform(post("/api/auth/logout").session(current).header(before.header(), before.token()))
            .andExpect(status().isForbidden());
        SessionToken fresh = csrf(current);
        mvc.perform(post("/api/auth/logout").session(current).header(fresh.header(), fresh.token()))
            .andExpect(status().isNoContent());
        assertThat(current.isInvalid()).isTrue();
        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    }

    @Test void registrationRotatesSessionAndInvalidatesOldCsrfToken() throws Exception {
        SessionToken before = csrf(null);
        String oldId = before.session().getId();
        MvcResult result = register(before, "Reader" + suffix, suffix + "@example.com", "good-password")
            .andExpect(status().isCreated()).andReturn();
        MockHttpSession session = (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session.getId()).isNotEqualTo(oldId);
        mvc.perform(post("/api/auth/logout").session(session).header(before.header(), before.token()))
            .andExpect(status().isForbidden());
    }

    @Test void passwordValidationAccountsForBcryptUtf8ByteLimit() throws Exception {
        for (String password : new String[]{"short", "a".repeat(73), "密".repeat(25)}) {
            register(csrf(null), "Reader" + suffix, suffix + "@example.com", password)
                .andExpect(status().isBadRequest());
        }
        register(csrf(null), "Reader" + suffix, suffix + "@example.com", "密".repeat(24))
            .andExpect(status().isCreated());
    }

    @Test void invalidRegistrationDataReturnsBadRequest() throws Exception {
        register(csrf(null), "  ", "not-an-email", "good-password").andExpect(status().isBadRequest());
        register(csrf(null), "ambiguous@example.com", suffix + "@example.com", "good-password")
            .andExpect(status().isBadRequest());
    }

    @Test void usernameMustHaveAtLeastThreeCharacters() throws Exception {
        register(csrf(null), "ab", suffix + "@example.com", "good-password")
            .andExpect(status().isBadRequest());
    }

    @Test void logoutExpiresBrowserSessionCookie() throws Exception {
        MvcResult registered = register(csrf(null), "Reader" + suffix, suffix + "@example.com", "good-password")
            .andExpect(status().isCreated()).andReturn();
        SessionToken fresh = csrf((MockHttpSession) registered.getRequest().getSession(false));
        mvc.perform(post("/api/auth/logout").session(fresh.session()).header(fresh.header(), fresh.token()))
            .andExpect(status().isNoContent())
            .andExpect(cookie().maxAge("paperflow_java_session", 0))
            .andExpect(cookie().httpOnly("paperflow_java_session", true))
            .andExpect(cookie().path("paperflow_java_session", "/"));
    }

    private SessionToken csrf(MockHttpSession existing) throws Exception {
        var request = get("/api/auth/csrf");
        if (existing != null) request.session(existing);
        MvcResult result = mvc.perform(request).andExpect(status().isOk()).andReturn();
        JsonNode body = json.readTree(result.getResponse().getContentAsString()).get("data");
        return new SessionToken((MockHttpSession) result.getRequest().getSession(false),
            body.get("header_name").asText(), body.get("token").asText());
    }

    private org.springframework.test.web.servlet.ResultActions register(SessionToken csrf, String username, String email, String password) throws Exception {
        return mvc.perform(post("/api/auth/register").session(csrf.session()).header(csrf.header(), csrf.token())
            .contentType("application/json").content(json.writeValueAsString(Map.of("username", username, "email", email, "password", password))));
    }

    private org.springframework.test.web.servlet.ResultActions login(SessionToken csrf, String identifier, String password) throws Exception {
        return mvc.perform(post("/api/auth/login").session(csrf.session()).header(csrf.header(), csrf.token())
            .contentType("application/json").content(json.writeValueAsString(Map.of("identifier", identifier, "password", password))));
    }

    private record SessionToken(MockHttpSession session, String header, String token) {}
}
