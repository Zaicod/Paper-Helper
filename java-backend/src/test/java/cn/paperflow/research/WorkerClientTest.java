package cn.paperflow.research;

import cn.paperflow.client.WorkerClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.time.Duration;
import static org.assertj.core.api.Assertions.*;

class WorkerClientTest {
    @Test void acceptsStrictStudyCompletionAndRejectsMalformedModules() throws Exception {
        var json=new ObjectMapper();
        String id=java.util.UUID.randomUUID().toString();
        var report=json.readTree("""
            {"report_type":"study_report","topic":"Study","generated_at":"2026-10-19T00:00:00Z",
             "papers":[{"paper_id":"p1"}],"analyses":[{"paper_id":"p1","title":"Paper","overview":"Overview",
             "background":"Problem","methods":[{"name":"Encoder","purpose":"Representation","inputs":"Tokens","outputs":"Vectors"}],
             "innovations":["Contribution"],"results":["Result"],"reflection":["Review modules"],
             "citations":[{"chunk_id":"p1:1","page_number":1,"source_url":"https://example.test/paper.pdf"}]}],
             "synthesis":["Summary"],"learning_plan":["Read"],"evidence_mode":"pdf","mode":"live"}
            """);
        var body=json.createObjectNode(); body.put("contract_version",1);body.put("task_id",id);body.put("status","completed");
        body.putArray("events");body.set("report",report);
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/internal/v1/tasks/",exchange -> {
            byte[] bytes=json.writeValueAsBytes(body);exchange.sendResponseHeaders(200,bytes.length);
            try(var out=exchange.getResponseBody()){out.write(bytes);}
        });server.start();
        try {
            var client=new WorkerClient(json,"http://127.0.0.1:"+server.getAddress().getPort(),"test-token-with-at-least-32-characters",2);
            assertThat(client.exchange(id,"running","{}").path("report").path("report_type").asText()).isEqualTo("study_report");
            ((com.fasterxml.jackson.databind.node.ObjectNode)report.path("analyses").get(0).path("methods").get(0)).remove("purpose");
            assertThatThrownBy(()->client.exchange(id,"running","{}")).isInstanceOf(IOException.class);
        }finally{server.stop(0);}
    }
    @Test void usesHttp11WithoutAnUnsupportedH2cUpgradeRequest() throws Exception {
        var upgrade=new java.util.concurrent.atomic.AtomicReference<String>();
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/internal/v1/papers/search",exchange -> {
            upgrade.set(exchange.getRequestHeaders().getFirst("Upgrade"));
            byte[] body="{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200,body.length);
            try(var out=exchange.getResponseBody()){out.write(body);}
        });
        server.start();
        try {
            var client=new WorkerClient(new ObjectMapper(),"http://127.0.0.1:"+server.getAddress().getPort(),"test-token-with-at-least-32-characters",2);
            client.search("multimodal","arxiv",1);
            assertThat(upgrade.get()).isNull();
        }finally{server.stop(0);}
    }
    @Test void overallTimeoutIncludesBodyAfterHeadersWereReceived() throws Exception {
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/internal/v1/tasks/",exchange -> {
            exchange.sendResponseHeaders(200,100);
            try (var output=exchange.getResponseBody()) {
                output.write('{'); output.flush();
                try { Thread.sleep(3000); } catch (InterruptedException exception) { Thread.currentThread().interrupt(); }
                output.write(" ".repeat(98).getBytes(java.nio.charset.StandardCharsets.UTF_8)); output.write('}');
            } catch (IOException ignored) { /* Client should cancel this partial response. */ }
        });
        server.start();
        try {
            var client=new WorkerClient(new ObjectMapper(),"http://127.0.0.1:"+server.getAddress().getPort(),"test-token-with-at-least-32-characters",1);
            var started=System.nanoTime();
            assertThatThrownBy(() -> client.exchange(java.util.UUID.randomUUID().toString(),"queued","{}"))
                .isInstanceOf(IOException.class);
            assertThat(Duration.ofNanos(System.nanoTime()-started)).isLessThan(Duration.ofMillis(2200));
        } finally { server.stop(0); }
    }
}
