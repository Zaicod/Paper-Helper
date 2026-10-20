package cn.paperflow.settings;
import com.fasterxml.jackson.databind.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
@SpringBootTest(properties={"paperflow.model-settings.key-file=target/test-settings/master.key","paperflow.worker.scheduling-enabled=false"}) @AutoConfigureMockMvc @ActiveProfiles("test")
class ModelSettingsApiTest {
 @Autowired MockMvc mvc; @Autowired ObjectMapper json; @Autowired JdbcTemplate jdbc;
 record Login(MockHttpSession session,String header,String token) {}
 Login account() throws Exception {
  var r=mvc.perform(get("/api/auth/csrf")).andReturn(); var d=json.readTree(r.getResponse().getContentAsString()).path("data");
  String id=UUID.randomUUID().toString().replace("-","");
  r=mvc.perform(post("/api/auth/register").session((MockHttpSession)r.getRequest().getSession()).header(d.path("header_name").asText(),d.path("token").asText()).contentType("application/json").content(json.writeValueAsString(Map.of("username","user"+id,"email",id+"@example.com","password","good-password")))).andExpect(status().isCreated()).andReturn();
  var s=(MockHttpSession)r.getRequest().getSession(); r=mvc.perform(get("/api/auth/csrf").session(s)).andReturn();d=json.readTree(r.getResponse().getContentAsString()).path("data");return new Login(s,d.path("header_name").asText(),d.path("token").asText());
 }
 void save(Login a,String body) throws Exception {mvc.perform(put("/api/model-settings/qwen").session(a.session).header(a.header,a.token).contentType("application/json").content(body)).andExpect(status().isOk());}
 @Test void savesEncryptedMasksPreservesEmptyAndScopesAccounts() throws Exception {
  var a=account();var b=account();save(a,"{\"model\":\"qwen3.8-flash\",\"api_key\":\"test-secret-account-123456\"}");
  var body=mvc.perform(get("/api/model-settings").session(a.session)).andExpect(status().isOk()).andExpect(jsonPath("$.data.providers[0].configured").value(true)).andReturn().getResponse().getContentAsString();
  assertThat(body).doesNotContain("test-secret-account"); assertThat(jdbc.queryForList("select key_ciphertext from pf_model_settings",String.class)).noneMatch(x->x!=null && x.contains("test-secret-account"));
  save(a,"{\"model\":\"other-model\",\"api_key\":\"\"}");
  mvc.perform(get("/api/model-settings").session(a.session)).andExpect(jsonPath("$.data.providers[0].configured").value(true)).andExpect(jsonPath("$.data.providers[0].model").value("other-model"));
  mvc.perform(get("/api/model-settings").session(b.session)).andExpect(jsonPath("$.data.providers[0].configured").value(false));
 }
 @Test void defaultRequiresKeyDeletionKeepsPersonalMarkerAndCsrfApplies() throws Exception {
  var a=account(); mvc.perform(put("/api/model-settings/qwen").session(a.session).contentType("application/json").content("{}")).andExpect(status().isForbidden());
  mvc.perform(get("/api/model-settings")).andExpect(status().isUnauthorized());
  mvc.perform(put("/api/model-settings/default").session(a.session).header(a.header,a.token).contentType("application/json").content("{\"provider\":\"qwen\"}")).andExpect(status().isBadRequest());
  save(a,"{\"model\":\"qwen3.8-flash\",\"api_key\":\"test-secret-delete-123456\"}");
  mvc.perform(put("/api/model-settings/default").session(a.session).header(a.header,a.token).contentType("application/json").content("{\"provider\":\"qwen\"}")).andExpect(status().isOk());
  mvc.perform(delete("/api/model-settings/qwen/key").session(a.session).header(a.header,a.token)).andExpect(status().isOk());
  mvc.perform(get("/api/model-settings").session(a.session)).andExpect(jsonPath("$.data.default_provider").value("qwen")).andExpect(jsonPath("$.data.providers[0].configured").value(false));
 }
 @Test void shortKeysNeverReturnInFullAndConnectionErrorsAreSafe() throws Exception {
  var a=account();save(a,"{\"model\":\"qwen3.8-flash\",\"api_key\":\"abcd\"}");
  var body=mvc.perform(get("/api/model-settings").session(a.session)).andReturn().getResponse().getContentAsString();
  assertThat(body).doesNotContain("abcd");
  body=mvc.perform(post("/api/model-settings/qwen/test").session(a.session).header(a.header,a.token)).andExpect(status().isOk()).andExpect(jsonPath("$.data.success").value(false)).andReturn().getResponse().getContentAsString();
  assertThat(body).doesNotContain("abcd","Exception");
  mvc.perform(put("/api/model-settings/qwen").session(a.session).header(a.header,a.token).contentType("application/json").content("{\"model\":\"model\",\"api_key\":\"abcd\\n\"}")).andExpect(status().isBadRequest());
 }
}
