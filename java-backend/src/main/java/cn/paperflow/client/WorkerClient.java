package cn.paperflow.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;

/** Only the configured service origin is contacted; redirects and browser URLs are never followed. */
@Component
public class WorkerClient {
    private final URI base;
    private final String token;
    private final ObjectMapper json;
    private final Duration timeout;
    private final HttpClient http;
    private static final Set<String> STATES=Set.of("queued","running","completed","failed","interrupted");
    public WorkerClient(ObjectMapper json,@Value("${paperflow.worker.base-url:}") String url,
        @Value("${paperflow.worker.token:}") String token,
        @Value("${paperflow.worker.request-timeout-seconds:5}") long seconds) {
        this.json=json; this.token=token; this.timeout=Duration.ofSeconds(Math.max(1,seconds));
        URI parsed=null;
        try {
            URI candidate=URI.create(url);
            if (Set.of("http","https").contains(candidate.getScheme()) && candidate.getHost()!=null
                && candidate.getUserInfo()==null && candidate.getQuery()==null && candidate.getFragment()==null
                && (candidate.getPath().isEmpty() || candidate.getPath().equals("/"))) parsed=candidate;
        } catch (RuntimeException ignored) { /* Unconfigured service leaves ordinary business APIs usable. */ }
        this.base=parsed;
        http=HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(timeout).followRedirects(HttpClient.Redirect.NEVER).build();
    }
    public boolean configured() { return base!=null && token.length()>=32 && !token.contains("\r") && !token.contains("\n"); }
    public cn.paperflow.vo.ModelTestVO testModel(String provider,String model,String key) throws IOException,InterruptedException {
        if(!configured())throw new IOException("worker_unconfigured");
        Duration deadline=Duration.ofSeconds(20);
        var request=HttpRequest.newBuilder(base.resolve("/internal/v1/models/test")).timeout(deadline)
            .header("Authorization","Bearer "+token).header("Content-Type","application/json")
            .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(java.util.Map.of("provider",provider,"model",model,"api_key",key)))).build();
        var response=sendBounded(request,deadline);if(response.statusCode()!=200)throw new IOException("worker_test_failed");
        var body=json.readTree(response.body());
        if(body==null || !body.path("success").isBoolean())throw new IOException("worker_invalid_test");
        boolean success=body.path("success").asBoolean();
        return new cn.paperflow.vo.ModelTestVO(success,success?"连接成功":"连接失败，请检查模型、API Key 和服务配置");
    }
    public byte[] studyDocument(JsonNode report) throws IOException,InterruptedException {
        if(!configured())throw new IOException("worker_unconfigured");
        Duration documentTimeout=Duration.ofSeconds(25);
        var request=HttpRequest.newBuilder(base.resolve("/internal/v1/study-reports/document"))
            .timeout(documentTimeout).header("Authorization","Bearer "+token)
            .header("Content-Type","application/json")
            .header("Accept","application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            .POST(HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(report))).build();
        var response=sendBounded(request,documentTimeout);
        if(response.statusCode()!=200 || !response.headers().firstValue("Content-Type").orElse("")
            .split(";",2)[0].strip().equalsIgnoreCase("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            || response.body().length<4 || response.body()[0]!='P' || response.body()[1]!='K')
            throw new IOException("worker_invalid_document");
        return response.body();
    }
    public JsonNode exchange(String id,String status,String payload) throws IOException,InterruptedException {
        if (!configured()) throw new IOException("worker_unconfigured");
        var builder=HttpRequest.newBuilder(base.resolve("/internal/v1/tasks/"+id)).timeout(timeout)
            .header("Authorization","Bearer "+token).header("Accept","application/json");
        if (status.equals("queued")) builder.header("Content-Type","application/json")
            .POST(HttpRequest.BodyPublishers.ofString(payload));
        else builder.GET();
        HttpResponse<byte[]> response=sendBounded(builder.build(),timeout);
        if (response.statusCode()==404 && status.equals("running")) throw new LostExecution();
        if (response.statusCode()!=200 && response.statusCode()!=202) throw new IOException("worker_unavailable");
        JsonNode body=json.readTree(response.body());
        if (body==null || body.path("contract_version").asInt()!=1 || !id.equals(body.path("task_id").asText())
            || !STATES.contains(body.path("status").asText()) || !body.path("events").isArray() || body.path("events").size()>200)
            throw new IOException("worker_invalid_response");
        for (JsonNode event:body.path("events")) {
            if (!Set.of("search","index","analyze","synthesize","ideate").contains(event.path("stage").asText())
                || !Set.of("started","completed","failed").contains(event.path("status").asText())
                || !event.path("message").isTextual() || event.path("message").asText().length()>2000)
                throw new IOException("worker_invalid_event");
        }
        if (body.path("status").asText().equals("completed")) {
            JsonNode report=body.path("report");
            if("study_report".equals(report.path("report_type").asText())) validateStudyReport(report);
            else if (!report.isObject() || !report.path("topic").isTextual() || !report.path("generated_at").isTextual()
                || !report.path("papers").isArray() || !report.path("analyses").isArray()
                || !report.path("synthesis").isObject() || !report.path("idea_portfolio").isObject())
                throw new IOException("worker_invalid_report");
        } else if (!body.path("report").isNull()) throw new IOException("worker_invalid_report");
        return body;
    }
    private static void validateStudyReport(JsonNode report) throws IOException {
        if(!report.isObject() || !text(report,"topic") || !text(report,"generated_at")
            || !"pdf".equals(report.path("evidence_mode").asText()) || !Set.of("live","demo").contains(report.path("mode").asText())
            || !report.path("papers").isArray() || report.path("papers").isEmpty() || report.path("papers").size()>20
            || !report.path("analyses").isArray() || report.path("analyses").size()!=report.path("papers").size()
            || !strings(report.path("synthesis")) || !strings(report.path("learning_plan"))) invalidStudy();
        Set<String> papers=new java.util.HashSet<>();
        for(var paper:report.path("papers")) if(!text(paper,"paper_id") || !papers.add(paper.path("paper_id").asText())) invalidStudy();
        Set<String> analyzed=new java.util.HashSet<>();
        for(var analysis:report.path("analyses")) {
            if(!papers.contains(analysis.path("paper_id").asText()) || !analyzed.add(analysis.path("paper_id").asText())
                || !text(analysis,"title") || !text(analysis,"overview") || !text(analysis,"background")
                || !strings(analysis.path("innovations")) || !strings(analysis.path("results")) || !strings(analysis.path("reflection"))
                || !analysis.path("methods").isArray() || analysis.path("methods").isEmpty() || analysis.path("methods").size()>50
                || !analysis.path("citations").isArray() || analysis.path("citations").isEmpty() || analysis.path("citations").size()>100) invalidStudy();
            for(var module:analysis.path("methods"))
                if(!text(module,"name") || !text(module,"purpose") || !text(module,"inputs") || !text(module,"outputs")) invalidStudy();
            for(var citation:analysis.path("citations"))
                if(!text(citation,"chunk_id") || !citation.path("page_number").isIntegralNumber()
                    || citation.path("page_number").asInt()<1 || !text(citation,"source_url")) invalidStudy();
        }
    }
    private static boolean text(JsonNode node,String key) {
        return node.path(key).isTextual() && !node.path(key).asText().isBlank() && node.path(key).asText().length()<=100000;
    }
    private static boolean strings(JsonNode node) {
        if(!node.isArray() || node.isEmpty() || node.size()>100)return false;
        for(var value:node) if(!value.isTextual() || value.asText().isBlank() || value.asText().length()>100000)return false;
        return true;
    }
    private static void invalidStudy() throws IOException { throw new IOException("worker_invalid_study_report"); }
    public JsonNode search(String query,String source,int limit) throws IOException,InterruptedException {
        return search(query,source,limit,null,"relevance");
    }
    public JsonNode search(String query,String source,int limit,Integer page,String sort) throws IOException,InterruptedException {
        return search(query,source,limit,page,sort,null);
    }
    public JsonNode search(String query,String source,int limit,Integer page,String sort,String keywords) throws IOException,InterruptedException {
        if (!configured()) throw new IOException("worker_unconfigured");
        Duration searchTimeout=Duration.ofSeconds(25);
        String parameters=(keywords==null ? "query="+java.net.URLEncoder.encode(query,java.nio.charset.StandardCharsets.UTF_8)+"&" : "")
            +"source="+source+"&limit="+limit;
        if(page!=null)parameters+="&page="+page+"&sort="+sort;
        if(keywords!=null)parameters+="&keywords="+java.net.URLEncoder.encode(keywords,java.nio.charset.StandardCharsets.UTF_8);
        var request=HttpRequest.newBuilder(base.resolve("/internal/v1/papers/search?"+parameters))
            .timeout(searchTimeout).header("Authorization","Bearer "+token).header("Accept","application/json").GET().build();
        var response=sendBounded(request,searchTimeout);
        if(response.statusCode()!=200)throw new SearchFailure(response.statusCode());
        JsonNode body=json.readTree(response.body());
        if(body==null || !body.isObject())throw new IOException("worker_invalid_search");
        return body;
    }
    private HttpResponse<byte[]> sendBounded(HttpRequest request,Duration totalTimeout) throws IOException,InterruptedException {
        // Include the complete response body in both the memory limit and the wall-clock deadline.
        var operation=http.sendAsync(request,info -> new LimitedBody(8*1024*1024));
        try { return operation.get(totalTimeout.toMillis(),java.util.concurrent.TimeUnit.MILLISECONDS); }
        catch(java.util.concurrent.TimeoutException ex) {
            operation.cancel(true); throw new HttpTimeoutException("worker_response_timeout");
        } catch(java.util.concurrent.ExecutionException ex) {
            if(ex.getCause() instanceof HttpTimeoutException timeoutFailure)throw timeoutFailure;
            throw new IOException("worker_request_failed",ex);
        } catch(InterruptedException ex) { operation.cancel(true); throw ex; }
    }
    public static class SearchFailure extends IOException {
        private final int status;
        SearchFailure(int status){this.status=status;}
        public int status(){return status;}
    }
    public static class LostExecution extends IOException {}
    /** Bounds memory before allocating an arbitrarily large remote response. */
    static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final HttpResponse.BodySubscriber<byte[]> delegate=HttpResponse.BodySubscribers.ofByteArray();
        private final long limit; private long received; private Flow.Subscription subscription;
        LimitedBody(long limit) { this.limit=limit; }
        public CompletionStage<byte[]> getBody() { return delegate.getBody(); }
        public void onSubscribe(Flow.Subscription subscription) { this.subscription=subscription; delegate.onSubscribe(subscription); }
        public void onNext(List<ByteBuffer> chunks) {
            for (ByteBuffer chunk:chunks) received+=chunk.remaining();
            if (received>limit) { subscription.cancel(); delegate.onError(new IOException("worker_response_too_large")); }
            else delegate.onNext(chunks);
        }
        public void onError(Throwable error) { delegate.onError(error); }
        public void onComplete() { delegate.onComplete(); }
    }
}
