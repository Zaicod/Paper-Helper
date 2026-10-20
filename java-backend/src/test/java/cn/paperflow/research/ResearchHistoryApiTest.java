package cn.paperflow.research;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import java.util.Map;
import java.util.UUID;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties="paperflow.worker.scheduling-enabled=false")
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ResearchHistoryApiTest {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper json;
    record Account(MockHttpSession session, long id) {}
    Account account() throws Exception {
        String name="h"+UUID.randomUUID().toString().replace("-", "");
        var result=mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json")
            .content(json.writeValueAsBytes(Map.of("username",name,"email",name+"@example.test","password","testing-pass-123"))))
            .andExpect(status().isCreated()).andReturn();
        return new Account((MockHttpSession)result.getRequest().getSession(false),
            jdbc.queryForObject("SELECT id FROM pf_users WHERE username=?",Long.class,name));
    }
    void seed(Account a,String status,String topic) {
        jdbc.update("""
            INSERT INTO pf_research_tasks(task_id,owner_id,idempotency_key,request_hash,topic,status,payload_json,
            events_json,created_at,updated_at,deadline_at,version)
            VALUES(?,?,?,?,?,?,?, '[]', CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,0)
            """,UUID.randomUUID().toString(),a.id(),UUID.randomUUID().toString(),"hash",topic,status,"{}");
    }
    @Test void groupsCoverEveryStatusAndKeepAccountsPrivate() throws Exception {
        var a=account();var b=account();
        for(String s:new String[]{"queued","running","completed","failed","interrupted"}) seed(a,s,s);
        seed(b,"completed","private");
        mvc.perform(get("/api/research/tasks").session(a.session()).param("category","active"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(2))
            .andExpect(jsonPath("$.data.tasks[*].status",org.hamcrest.Matchers.containsInAnyOrder("queued","running")));
        mvc.perform(get("/api/research/tasks").session(a.session()).param("category","unfinished"))
            .andExpect(jsonPath("$.data.total").value(2))
            .andExpect(jsonPath("$.data.tasks[*].status",org.hamcrest.Matchers.containsInAnyOrder("failed","interrupted")));
        mvc.perform(get("/api/research/tasks").session(a.session()).param("category","history"))
            .andExpect(jsonPath("$.data.total").value(1)).andExpect(jsonPath("$.data.tasks[0].topic").value("completed"));
        mvc.perform(get("/api/research/tasks").session(a.session()))
            .andExpect(jsonPath("$.data.total").value(5));
    }
    @Test void filtersBeforeCountingAndPaginatesTenRowsWithoutOverlap() throws Exception {
        var a=account();
        for(int i=0;i<12;i++) seed(a,"completed","多模态 Agent "+i);
        seed(a,"failed","多模态 Agent failure");seed(a,"completed","other");
        var first=mvc.perform(get("/api/research/tasks").session(a.session()).param("category","history").param("keyword","  多模态 agent  "))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(12))
            .andExpect(jsonPath("$.data.size").value(10)).andExpect(jsonPath("$.data.tasks.length()").value(10)).andReturn();
        var second=mvc.perform(get("/api/research/tasks").session(a.session()).param("category","history").param("keyword","多模态 agent").param("page","1"))
            .andExpect(jsonPath("$.data.total").value(12)).andExpect(jsonPath("$.data.tasks.length()").value(2)).andReturn();
        var ids=new java.util.HashSet<String>();
        for(var r:java.util.List.of(first,second)) for(var row:json.readTree(r.getResponse().getContentAsByteArray()).path("data").path("tasks"))
            org.assertj.core.api.Assertions.assertThat(ids.add(row.path("task_id").asText())).isTrue();
    }
    @Test void searchTreatsWildcardAndEscapeCharactersLiterally() throws Exception {
        var a=account();seed(a,"completed","100%_! ' 研究");seed(a,"completed","100abcd 研究");
        for(String term:new String[]{"%","_","!","'","%_!"})
            mvc.perform(get("/api/research/tasks").session(a.session()).param("category","history").param("keyword",term))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(1));
    }
    @Test void rejectsBadFiltersAndPagination() throws Exception {
        var a=account();
        mvc.perform(get("/api/research/tasks").session(a.session()).param("category","wrong")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/research/tasks").session(a.session()).param("keyword","x".repeat(501))).andExpect(status().isBadRequest());
        mvc.perform(get("/api/research/tasks").session(a.session()).param("page","-1")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/research/tasks").session(a.session()).param("size","0")).andExpect(status().isBadRequest());
    }
}
