package cn.paperflow.research;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ResearchApiTest {
    static final String TOKEN = "integration-service-token-at-least-32-characters";
    static final Map<String, JsonNode> submitted = new ConcurrentHashMap<>();
    static final AtomicInteger submissions = new AtomicInteger();
    static volatile int remoteStatus = 202;
    static volatile String remoteState = "running";
    static volatile boolean invalidReport;
    static volatile String remoteErrorCode;
    static volatile String remoteErrorMessage;
    static final ObjectMapper wire = new ObjectMapper();
    static final HttpServer remote = startRemote();
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired JdbcTemplate jdbc;
    @Autowired ApplicationContext context;

    static HttpServer startRemote() {
        try {
            HttpServer server = HttpServer.create(new java.net.InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/internal/v1/tasks/", exchange -> {
                String id = exchange.getRequestURI().getPath().substring("/internal/v1/tasks/".length());
                int code;
                Map<String,Object> result = new LinkedHashMap<>();
                if (!("Bearer " + TOKEN).equals(exchange.getRequestHeaders().getFirst("Authorization"))) code = 401;
                else if (exchange.getRequestMethod().equals("POST")) {
                    JsonNode input = wire.readTree(exchange.getRequestBody());
                    submitted.putIfAbsent(id, input); submissions.incrementAndGet(); code = remoteStatus;
                } else code = submitted.containsKey(id) ? 200 : 404;
                result.put("contract_version", 1); result.put("task_id", id);
                result.put("status", remoteState); result.put("events", List.of());
                result.put("error_code", remoteErrorCode); result.put("error_message", remoteErrorMessage);
                result.put("report", "completed".equals(remoteState) && !invalidReport ? Map.of(
                    "topic", "Agent", "generated_at", "2026-10-18T00:00:00Z", "papers", List.of(),
                    "analyses", List.of(), "synthesis", Map.of("overview", "test"),
                    "idea_portfolio", Map.of("ideas", List.of()), "analysis_failures", List.of(), "context_audits", List.of()) : null);
                byte[] data = wire.writeValueAsBytes(result);
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(code, data.length);
                try (var output = exchange.getResponseBody()) { output.write(data); }
            });
            server.start(); return server;
        } catch (IOException exception) { throw new RuntimeException(exception); }
    }
    @DynamicPropertySource static void properties(DynamicPropertyRegistry props) {
        props.add("paperflow.worker.base-url", () -> "http://127.0.0.1:" + remote.getAddress().getPort());
        props.add("paperflow.worker.token", () -> TOKEN);
        props.add("paperflow.worker.scheduling-enabled", () -> "false");
    }
    @BeforeEach void reset() { remoteStatus = 202; remoteState = "running"; invalidReport = false; remoteErrorCode=null;remoteErrorMessage=null; }
    @AfterAll static void stopRemote() { remote.stop(0); }

    @Test void submissionIsDurableIdempotentAndBoundToUser() throws Exception {
        var a = user(); var b = user(); var input = input();
        JsonNode first = submit(a, input, 202);
        String id = first.get("task_id").asText();
        assertThat(first.get("status").asText()).isEqualTo("queued");
        assertThat(submit(a, input, 202).get("task_id").asText()).isEqualTo(id);
        var changed = new HashMap<>(input); changed.put("topic", "different");
        submit(a, changed, 409);
        assertThat(submit(b, input, 202).get("task_id").asText()).isNotEqualTo(id);
        mvc.perform(get("/api/research/tasks/{id}", id).session(b)).andExpect(status().isNotFound());
        mvc.perform(get("/api/research/tasks").session(a)).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.total").value(1)).andExpect(jsonPath("$.data.tasks[0].task_id").value(id));
        assertThat(jdbc.queryForObject("select count(*) from pf_research_tasks where task_id=?", Long.class, id)).isEqualTo(1);
    }
    @Test void indexNamespaceIsStablePerAccountAndDistinctBetweenAccounts() throws Exception {
        var a=user();var b=user();
        String first=submit(a,input(),202).path("task_id").asText();
        String second=submit(a,input(),202).path("task_id").asText();
        String other=submit(b,input(),202).path("task_id").asText();
        tick();
        long owner=jdbc.queryForObject("select owner_id from pf_research_tasks where task_id=?",Long.class,first);
        String namespace=submitted.get(first).path("index_namespace").asText();
        assertThat(namespace).isEqualTo("java-user:"+owner);
        assertThat(submitted.get(second).path("index_namespace").asText()).isEqualTo(namespace);
        assertThat(submitted.get(other).path("index_namespace").asText()).isNotEmpty().isNotEqualTo(namespace);
        mvc.perform(get("/api/research/tasks/{id}",first).session(a)).andExpect(jsonPath("$.data.index_namespace").doesNotExist());
    }
    @Test void browserCannotOverrideTrustedIndexNamespaceOrChangeItsIdempotency() throws Exception {
        var a=user();var body=input();body.put("index_namespace","java-user:someone-else");
        String id=submit(a,body,202).path("task_id").asText();
        body.put("index_namespace","another-spoofed-namespace");
        assertThat(submit(a,body,202).path("task_id").asText()).isEqualTo(id);
        tick();
        long owner=jdbc.queryForObject("select owner_id from pf_research_tasks where task_id=?",Long.class,id);
        assertThat(submitted.get(id).path("index_namespace").asText()).isEqualTo("java-user:"+owner);
        String snapshot=jdbc.queryForObject("select payload_json from pf_research_tasks where task_id=?",String.class,id);
        assertThat(json.readTree(snapshot).path("index_namespace").asText()).isEqualTo("java-user:"+owner);
    }
    @Test void studyRequiresExplicitOwnedSelectionAndSnapshotsLearningInputs() throws Exception {
        var a=user(); var body=input(); body.put("task_type","study_report"); body.put("mode","live");
        submit(a,body,400);
        long collection=postJson(a,"/api/library/collections",Map.of("name","Study"),201).path("id").asLong();
        String externalId="study-paper-"+UUID.randomUUID();
        long paper=postJson(a,"/api/library/collections/"+collection+"/papers",Map.of(
            "source","manual","paper_id",externalId,"title","Selected PDF",
            "abstract","Evidence","page_url","https://example.test/study","pdf_url","https://example.test/study.pdf"),201).path("id").asLong();
        mvc.perform(put("/api/library/collections/{collection}/paper-note",collection).session(a).with(csrf())
            .contentType("application/json").content(json.writeValueAsBytes(Map.of("source","manual","paper_id",externalId,"content","My original notes"))))
            .andExpect(status().isOk());
        body.put("collection_id",collection); submit(a,body,400);
        body.put("paper_ids",List.of(paper)); body.put("learning_goal","Understand modules"); body.put("reflection","Need help with ablation");
        var demo=new HashMap<>(body);demo.put("mode","demo");submit(a,demo,400);
        var stranger=user();submit(stranger,body,404);
        var created=submit(a,body,202); String id=created.path("task_id").asText();
        assertThat(created.path("task_type").asText()).isEqualTo("study_report");
        mvc.perform(delete("/api/library/collections/{id}",collection).session(a).with(csrf())).andExpect(status().isNoContent());
        tick(); var payload=submitted.get(id);
        assertThat(payload.path("task_type").asText()).isEqualTo("study_report");
        assertThat(payload.path("learning_goal").asText()).isEqualTo("Understand modules");
        assertThat(payload.path("reflection").asText()).isEqualTo("Need help with ablation");
        assertThat(payload.path("notes").isObject()).isTrue();
        assertThat(payload.path("notes").elements().next().asText()).isEqualTo("My original notes");
        mvc.perform(get("/api/research/tasks").session(a)).andExpect(jsonPath("$.data.tasks[0].task_type").value("study_report"));
    }
    @Test void documentDownloadRequiresOwnedCompletedStudyReportAndUsesStoredSnapshot() throws Exception {
        var a=user(); var b=user(); String id=submit(a,input(),202).path("task_id").asText();
        mvc.perform(get("/api/research/tasks/{id}/document",id)).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/research/tasks/{id}/document",id).session(b)).andExpect(status().isNotFound());
        mvc.perform(get("/api/research/tasks/{id}/document",id).session(a)).andExpect(status().isConflict());
        jdbc.update("update pf_research_tasks set status='completed', report_json=? where task_id=?", "{\"topic\":\"ordinary research\"}",id);
        mvc.perform(get("/api/research/tasks/{id}/document",id).session(a)).andExpect(status().isConflict());
        remote.createContext("/internal/v1/study-reports/document", exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst("Authorization")).isEqualTo("Bearer "+TOKEN);
            assertThat(wire.readTree(exchange.getRequestBody()).path("topic").asText()).isEqualTo("saved study snapshot");
            byte[] bytes=new byte[]{80,75,3,4,42};
            exchange.getResponseHeaders().set("Content-Type","application/vnd.openxmlformats-officedocument.wordprocessingml.document");
            exchange.sendResponseHeaders(200,bytes.length);try(var output=exchange.getResponseBody()){output.write(bytes);}
        });
        try {
            jdbc.update("update pf_research_tasks set report_json=? where task_id=?","{\"report_type\":\"study_report\",\"topic\":\"saved study snapshot\"}",id);
            mvc.perform(get("/api/research/tasks/{id}/document",id).session(a)).andExpect(status().isOk())
                .andExpect(content().contentType("application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
                .andExpect(header().string("Content-Disposition","attachment; filename=\"paperflow-study-report.docx\""))
                .andExpect(content().bytes(new byte[]{80,75,3,4,42}));
        } finally { remote.removeContext("/internal/v1/study-reports/document"); }
    }
    @Test void documentUpstreamErrorsRemainSafe() throws Exception {
        var a=user();String id=submit(a,input(),202).path("task_id").asText();
        jdbc.update("update pf_research_tasks set status='completed',report_json=? where task_id=?",
            "{\"report_type\":\"study_report\",\"topic\":\"stored\"}",id);
        remote.createContext("/internal/v1/study-reports/document",exchange -> {
            byte[] bytes="secret-upstream-token-and-path".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(500,bytes.length);try(var out=exchange.getResponseBody()){out.write(bytes);}
        });
        try {
            var result=mvc.perform(get("/api/research/tasks/{id}/document",id).session(a)).andExpect(status().isBadGateway()).andReturn();
            assertThat(result.getResponse().getContentAsString(StandardCharsets.UTF_8)).doesNotContain("secret-upstream");
        } finally { remote.removeContext("/internal/v1/study-reports/document"); }
    }
    @Test void studyFailureShowsSafeEvidenceReasonWhileResearchFailureStaysSanitized() throws Exception {
        var a=user();
        long collection=postJson(a,"/api/library/collections",Map.of("name","Missing PDF"),201).path("id").asLong();
        long paper=postJson(a,"/api/library/collections/"+collection+"/papers",Map.of(
            "source","manual","paper_id",UUID.randomUUID().toString(),"title","Paper without PDF",
            "abstract","Evidence","page_url","https://example.test/paper"),201).path("id").asLong();
        var body=input();body.put("task_type","study_report");body.put("mode","live");body.put("collection_id",collection);body.put("paper_ids",List.of(paper));
        String study=submit(a,body,202).path("task_id").asText();
        String research=submit(a,input(),202).path("task_id").asText();
        remoteState="failed";remoteErrorCode="study_report_failed";
        remoteErrorMessage="无法获取论文 Paper without PDF 的正文，请补充可公开访问的 PDF 链接后重试。";tick();
        mvc.perform(get("/api/research/tasks/{id}",study).session(a))
            .andExpect(jsonPath("$.data.error_code").value("study_report_failed"))
            .andExpect(jsonPath("$.data.error_message").value(remoteErrorMessage));
        mvc.perform(get("/api/research/tasks/{id}",research).session(a))
            .andExpect(jsonPath("$.data.error_code").value("research_failed"))
            .andExpect(jsonPath("$.data.error_message").value("研究执行失败，请检查 Python 服务配置与执行记录"));
    }
    @Test void simultaneousRetriesReturnSameTaskInsteadOfAConflict() throws Exception {
        var session = user(); var body = input();
        var ready = new java.util.concurrent.CountDownLatch(8);
        var start = new java.util.concurrent.CountDownLatch(1);
        try (var pool = java.util.concurrent.Executors.newFixedThreadPool(8)) {
            var jobs = new ArrayList<java.util.concurrent.Future<String>>();
            for (int i=0;i<8;i++) jobs.add(pool.submit(() -> {
                ready.countDown(); start.await();
                return submit(session,body,202).path("task_id").asText();
            }));
            assertThat(ready.await(5,java.util.concurrent.TimeUnit.SECONDS)).isTrue(); start.countDown();
            var ids = new HashSet<String>();
            for (var job:jobs) ids.add(job.get(10,java.util.concurrent.TimeUnit.SECONDS));
            assertThat(ids).hasSize(1);
            assertThat(jdbc.queryForObject("select count(*) from pf_research_tasks where idempotency_key=?",Long.class,body.get("idempotency_key"))).isEqualTo(1);
        }
    }
    @Test void anonymousCsrfAndInvalidInputsAreRejected() throws Exception {
        mvc.perform(get("/api/research/tasks")).andExpect(status().isUnauthorized());
        var a = user();
        mvc.perform(post("/api/research/tasks").session(a).contentType("application/json").content(json.writeValueAsBytes(input())))
            .andExpect(status().isForbidden());
        for (var patch : List.of(Map.of("topic", " "), Map.of("limit", 21), Map.of("mode", "pretend"),
                Map.of("idempotency_key", "bad"), Map.of("paper_ids", List.of(1)), Map.of("mode", ""))) {
            var invalid = new HashMap<>(input()); invalid.putAll(patch); submit(a, invalid, 400);
        }
        mvc.perform(get("/api/research/tasks").session(a).param("size", "101")).andExpect(status().isBadRequest());
    }
    @Test void selectedPapersComeFromOwnedCollectionAndSnapshotSurvivesDeletion() throws Exception {
        var a = user(); var b = user();
        long collection = postJson(a, "/api/library/collections", Map.of("name", "Research"), 201).get("id").asLong();
        long paper = postJson(a, "/api/library/collections/" + collection + "/papers", Map.of(
            "source", "manual", "paper_id", UUID.randomUUID().toString(), "title", "Trusted stored title",
            "abstract", "Evidence text", "page_url", "https://example.test/paper"), 201).get("id").asLong();
        var input = input(); input.put("collection_id", collection); input.put("paper_ids", List.of(paper));
        submit(b, input, 404);
        var wrong = new HashMap<>(input); wrong.put("paper_ids", List.of(paper + 9999)); submit(a, wrong, 400);
        var duplicate = new HashMap<>(input); duplicate.put("paper_ids", List.of(paper, paper)); submit(a, duplicate, 400);
        String id = submit(a, input, 202).get("task_id").asText();
        mvc.perform(delete("/api/library/collections/{id}", collection).session(a).with(csrf())).andExpect(status().isNoContent());
        assertThat(submit(a, input, 202).get("task_id").asText()).isEqualTo(id);
        tick();
        assertThat(submitted.get(id).path("papers").get(0).path("title").asText()).isEqualTo("Trusted stored title");
        assertThat(submitted.get(id).path("papers").get(0).has("note")).isFalse();
    }
    @Test void synchronizationUsesStableIdAndPersistsCompletedReport() throws Exception {
        var a = user(); String id = submit(a, input(), 202).get("task_id").asText();
        tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("running"));
        assertThat(submitted.get(id).path("options").path("mode").asText()).isEqualTo("demo");
        int count = submissions.get(); remoteState = "completed"; tick(); tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("completed"))
            .andExpect(jsonPath("$.data.report.synthesis.overview").value("test"));
        assertThat(submissions.get()).isEqualTo(count);
    }
    @Test void researchKeepsPersonalPaperSnapshotEvenAfterFurtherLibraryEdits() throws Exception {
        var a=user();
        long ca=postJson(a,"/api/library/collections",Map.of("name","Edited collection"),201).get("id").asLong();
        long cb=postJson(a,"/api/library/collections",Map.of("name","Original collection"),201).get("id").asLong();
        var metadata=new HashMap<String,Object>(Map.of("source","manual","paper_id",UUID.randomUUID().toString(),
            "title","Original shared paper","abstract","Stored evidence","page_url","https://example.test/paper"));
        long paper=postJson(a,"/api/library/collections/"+ca+"/papers",metadata,201).get("id").asLong();
        postJson(a,"/api/library/collections/"+cb+"/papers",metadata,201);
        metadata.put("title","Private title at submission");
        mvc.perform(put("/api/library/collections/{collection}/papers/{paper}",ca,paper).session(a).with(csrf())
            .contentType("application/json").content(json.writeValueAsBytes(metadata))).andExpect(status().isOk());
        var request=input();request.put("collection_id",ca);
        String edited=submit(a,request,202).get("task_id").asText();
        metadata.put("title","Later edit must not change submitted snapshot");
        mvc.perform(put("/api/library/collections/{collection}/papers/{paper}",ca,paper).session(a).with(csrf())
            .contentType("application/json").content(json.writeValueAsBytes(metadata))).andExpect(status().isOk());
        var second=input();second.put("collection_id",cb);
        String original=submit(a,second,202).get("task_id").asText();
        tick();
        assertThat(submitted.get(edited).path("papers").get(0).path("title").asText()).isEqualTo("Private title at submission");
        assertThat(submitted.get(original).path("papers").get(0).path("title").asText()).isEqualTo("Original shared paper");
    }
    @Test void lostSubmissionResponseRetriesSameTaskAndRemoteErrorsStaySafe() throws Exception {
        var a = user(); String id = submit(a, input(), 202).get("task_id").asText();
        remoteStatus = 503; tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("queued"))
            .andExpect(jsonPath("$.data.sync_error").isNotEmpty());
        remoteStatus = 202; tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("running"));
        assertThat(submitted.containsKey(id)).isTrue();
        remoteState = "interrupted"; tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("interrupted"));
    }
    @Test void malformedCompletedResultDoesNotClaimSuccessAndDeadlineEndsSynchronization() throws Exception {
        var a = user(); String id = submit(a, input(), 202).get("task_id").asText();
        invalidReport = true; remoteState = "completed"; tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("queued"))
            .andExpect(jsonPath("$.data.sync_error").isNotEmpty());
        jdbc.update("update pf_research_tasks set deadline_at=? where task_id=?", java.sql.Timestamp.from(java.time.Instant.now().minusSeconds(5)), id);
        tick();
        mvc.perform(get("/api/research/tasks/{id}", id).session(a)).andExpect(jsonPath("$.data.status").value("interrupted"))
            .andExpect(jsonPath("$.data.error_code").value("sync_deadline_exceeded"));
    }
    private void tick() { ReflectionTestUtils.invokeMethod(context.getBean("researchSynchronizer"), "tick"); }
    private HashMap<String,Object> input() {
        return new HashMap<>(Map.of("idempotency_key", UUID.randomUUID().toString(), "topic", "Agent", "mode", "demo", "limit", 2));
    }
    private JsonNode submit(MockHttpSession session, Map<String,?> input, int expected) throws Exception {
        return postJson(session, "/api/research/tasks", input, expected);
    }
    private JsonNode postJson(MockHttpSession session, String path, Object input, int expected) throws Exception {
        var result = mvc.perform(post(path).session(session).with(csrf()).contentType("application/json").content(json.writeValueAsBytes(input)))
            .andExpect(status().is(expected)).andReturn();
        return json.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8)).path("data");
    }
    private MockHttpSession user() throws Exception {
        String name = "u" + UUID.randomUUID().toString().replace("-", "");
        var result = mvc.perform(post("/api/auth/register").with(csrf()).contentType("application/json").content(json.writeValueAsBytes(
            Map.of("username", name, "email", name + "@example.test", "password", "testing-pass-123"))))
            .andExpect(status().isCreated()).andReturn();
        return (MockHttpSession) result.getRequest().getSession(false);
    }
}
