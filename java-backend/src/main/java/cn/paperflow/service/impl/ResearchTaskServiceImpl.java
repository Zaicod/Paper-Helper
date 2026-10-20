package cn.paperflow.service.impl;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.service.ResearchTaskService;
import cn.paperflow.dto.ResearchTaskDTO;
import cn.paperflow.vo.*;

import cn.paperflow.common.ApiException;
import cn.paperflow.service.LibraryService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;


import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;


@Service
public class ResearchTaskServiceImpl implements ResearchTaskService {
    private final ResearchTaskMapper tasks;
    private final LibraryService library;
    private final ObjectMapper json;
    private final WorkerClient worker;
    private final long timeout;
    private final cn.paperflow.service.ModelSettingsService settings;
    public ResearchTaskServiceImpl(ResearchTaskMapper tasks, LibraryService library, ObjectMapper json,
        WorkerClient worker, @Value("${paperflow.worker.task-timeout-seconds:1800}") long timeout) {
        this(tasks,library,json,worker,timeout,null);
    }
    @org.springframework.beans.factory.annotation.Autowired
    public ResearchTaskServiceImpl(ResearchTaskMapper tasks, LibraryService library, ObjectMapper json,
        WorkerClient worker, @Value("${paperflow.worker.task-timeout-seconds:1800}") long timeout,cn.paperflow.service.ModelSettingsService settings) {
        this.tasks=tasks; this.library=library; this.json=json; this.worker=worker; this.timeout=Math.max(1,timeout);this.settings=settings;
    }
    @Transactional
    public ResearchTaskVO submit(long owner, ResearchTaskDTO input) {
        boolean study="study_report".equals(input.taskType());
        if (study && (input.collectionId()==null || input.paperIds()==null || input.paperIds().isEmpty()))
            throw new ApiException(HttpStatus.BAD_REQUEST,"学习报告必须选择收藏夹中的 1 至 20 篇论文");
        if(study && !"live".equals(input.mode()))
            throw new ApiException(HttpStatus.BAD_REQUEST,"学习报告需使用真实模型并获取论文 PDF");
        if (input.paperIds()!=null && input.collectionId()==null)
            throw new ApiException(HttpStatus.BAD_REQUEST,"选定论文必须指定收藏夹");
        if (input.paperIds()!=null && new HashSet<>(input.paperIds()).size()!=input.paperIds().size())
            throw new ApiException(HttpStatus.BAD_REQUEST,"不能重复选择论文");
        String hash=hash(encode(input));
        // Serialize this user's short submit transaction so concurrent same-key retries see the first row.
        tasks.lockOwner(owner);
        var existing=tasks.findRequest(owner,input.idempotencyKey());
        if (existing!=null) {
            if (!existing.getRequestHash().equals(hash)) throw new ApiException(HttpStatus.CONFLICT,"该请求标识已用于不同研究参数");
            return view(existing);
        }
        if (!worker.configured()) throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"尚未配置 Python 研究服务");
        Map<String,Object> payload=new LinkedHashMap<>();
        payload.put("contract_version",1); payload.put("topic",input.topic()); payload.put("limit",input.limit());
        // Only the authenticated owner determines which persisted vector index this task can access.
        payload.put("index_namespace","java-user:"+owner);
        payload.put("task_type",input.taskType());
        if(study) {
            payload.put("learning_goal",input.learningGoal()); payload.put("reflection",input.reflection());
        }
        Map<String,Object> options=new LinkedHashMap<>();
        var selection=settings==null ? new cn.paperflow.service.ModelSettingsService.Selection(input.provider()==null?"qwen":input.provider(),input.model(),"server") : settings.resolve(owner,input.provider(),input.model(),"live".equals(input.mode()));
        options.put("mode",input.mode()); options.put("rag",input.rag()); options.put("provider",selection.provider());options.put("credential_source",selection.credentialSource());
        if (selection.model()!=null) options.put("model",selection.model());
        payload.put("options",options); payload.put("papers",null);
        if (input.collectionId()!=null) {
            var collection=library.detail(owner,input.collectionId());
            var stored=collection.papers();
            if (input.paperIds()!=null) {
                var wanted=new HashSet<>(input.paperIds());
                stored=stored.stream().filter(p -> wanted.contains(p.id())).toList();
                if (stored.size()!=wanted.size()) throw new ApiException(HttpStatus.BAD_REQUEST,"选定论文不在本人的收藏夹中");
            }
            if (stored.isEmpty() || stored.size()>20) throw new ApiException(HttpStatus.BAD_REQUEST,"请选择 1 至 20 篇收藏论文");
            if (stored.stream().map(p->p.paperId()).distinct().count()!=stored.size())
                throw new ApiException(HttpStatus.BAD_REQUEST,"论文外部 ID 重复，请缩小选择范围");
            if(study) {
                Map<String,String> notes=new LinkedHashMap<>();
                for(var paper:stored) notes.put(paper.paperId(),paper.note()==null ? "" : paper.note());
                payload.put("notes",notes);
                payload.put("collection_note",collection.overallNote()==null ? "" : collection.overallNote());
                payload.put("limit",stored.size());
            }
            payload.put("papers",stored.stream().map(p -> {
                Map<String,Object> paper=new LinkedHashMap<>();
                paper.put("source",p.source()); paper.put("paper_id",p.paperId()); paper.put("title",p.title());
                paper.put("abstract",p.abstractText()); paper.put("authors",p.authors()); paper.put("categories",p.categories());
                paper.put("published",p.published()); paper.put("page_url",p.pageUrl()); paper.put("pdf_url",p.pdfUrl());
                return paper;
            }).toList());
        }
        String payloadJson=encode(payload);
        if(payloadJson.getBytes(StandardCharsets.UTF_8).length>2*1024*1024)
            throw new ApiException(HttpStatus.BAD_REQUEST,"任务资料超过 2 MiB，请缩短笔记或减少所选论文后重试");
        ResearchTask task=new ResearchTask();
        task.setTaskId(UUID.randomUUID().toString()); task.setOwnerId(owner); task.setIdempotencyKey(input.idempotencyKey());
        task.setRequestHash(hash); task.setTopic(input.topic()); task.setPayloadJson(payloadJson);
        task.setStatus("queued"); task.setEventsJson("[]");
        task.setCreatedAt(java.time.Instant.now()); task.setUpdatedAt(task.getCreatedAt());
        task.setDeadlineAt(task.getCreatedAt().plusSeconds(timeout)); tasks.insert(task);
        return view(task);
    }
    @Transactional
    public ResearchTaskVO retry(long owner,String id,cn.paperflow.dto.RetryTaskDTO input) {
        tasks.lockOwner(owner);
        ResearchTask original=tasks.findOwned(id,owner);
        if(original==null) throw new ApiException(HttpStatus.NOT_FOUND,"研究任务不存在");
        String requestHash=hash("retry-task:"+id);
        ResearchTask existing=tasks.findRequest(owner,input.idempotencyKey());
        if(existing!=null) {
            if(!requestHash.equals(existing.getRequestHash()))
                throw new ApiException(HttpStatus.CONFLICT,"该请求标识已用于其他任务，请重新重试");
            return view(existing);
        }
        if(!Set.of("failed","interrupted").contains(original.getStatus()))
            throw new ApiException(HttpStatus.CONFLICT,"只有失败或中断的任务可以重试");
        if(!worker.configured()) throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"尚未配置 Python 研究服务");
        JsonNode snapshot=decode(original.getPayloadJson());
        JsonNode papers=snapshot.path("papers");
        if(papers.isArray()) for(JsonNode paper:papers) {
            if(tasks.countOwnedPaper(owner,paper.path("source").asText(),paper.path("paper_id").asText())==0)
                throw new ApiException(HttpStatus.BAD_REQUEST,"原任务中的论文已不在本人的收藏夹中，请重新选择论文后创建任务");
        }
        // Copy only the persisted, nonsecret input contract. Credentials are attached at dispatch.
        var payload=json.createObjectNode();
        for(String field:List.of("contract_version","topic","limit","task_type","learning_goal","reflection","notes","collection_note","papers")) {
            if(snapshot.has(field)) payload.set(field,snapshot.get(field).deepCopy());
        }
        payload.put("index_namespace","java-user:"+owner);
        JsonNode oldOptions=snapshot.path("options");
        boolean live="live".equals(oldOptions.path("mode").asText());
        var selection=settings==null ? new cn.paperflow.service.ModelSettingsService.Selection("qwen",null,"server")
            : settings.resolve(owner,null,null,live);
        var options=payload.putObject("options");
        options.put("mode",live?"live":"demo");
        if(oldOptions.has("rag")) options.set("rag",oldOptions.get("rag").deepCopy());
        options.put("provider",selection.provider());
        options.put("credential_source",selection.credentialSource());
        if(selection.model()!=null) options.put("model",selection.model());
        String payloadJson=encode(payload);
        if(payloadJson.getBytes(StandardCharsets.UTF_8).length>2*1024*1024)
            throw new ApiException(HttpStatus.BAD_REQUEST,"任务资料超过 2 MiB，请缩短笔记或减少所选论文后重试");
        ResearchTask task=new ResearchTask();
        task.setTaskId(UUID.randomUUID().toString());task.setOwnerId(owner);task.setIdempotencyKey(input.idempotencyKey());
        task.setRequestHash(requestHash);task.setTopic(original.getTopic());task.setPayloadJson(payloadJson);
        task.setStatus("queued");task.setEventsJson("[]");
        task.setCreatedAt(java.time.Instant.now());task.setUpdatedAt(task.getCreatedAt());
        task.setDeadlineAt(task.getCreatedAt().plusSeconds(timeout));tasks.insert(task);
        return view(task);
    }
    @Transactional(readOnly=true)
    public ResearchTaskVO detail(long owner,String id) {
        ResearchTask task=tasks.findOwned(id,owner);
        if(task==null) throw new ApiException(HttpStatus.NOT_FOUND,"研究任务不存在");
        return view(task);
    }
    @Transactional(readOnly=true)
    public ResearchTaskPageVO list(long owner,int page,int size,String category,String keyword) {
        if (page<0 || size<1 || size>100) throw new ApiException(HttpStatus.BAD_REQUEST,"分页参数无效");
        List<String> states=switch(category==null ? "" : category) {
            case "" -> null;
            case "active" -> List.of("queued","running");
            case "unfinished" -> List.of("failed","interrupted");
            case "history" -> List.of("completed");
            default -> throw new ApiException(HttpStatus.BAD_REQUEST,"研究任务分类无效");
        };
        String term=keyword==null ? "" : keyword.strip();
        if(term.length()>500) throw new ApiException(HttpStatus.BAD_REQUEST,"搜索关键词不能超过 500 个字符");
        String pattern=term.isEmpty() ? null : "%"+term.toLowerCase(Locale.ROOT)
            .replace("!","!!").replace("%","!%").replace("_","!_")+"%";
        var rows=tasks.listOwned(owner,(long)page*size,size,states,pattern);
        return new ResearchTaskPageVO(rows.stream().map(t -> new ResearchTaskSummaryVO(t.getTaskId(),t.getTopic(),t.getStatus(),t.getCreatedAt(),t.getUpdatedAt(),taskType(t))).toList(),tasks.countOwned(owner,states,pattern),page,size);
    }
    private ResearchTaskVO view(ResearchTask t) {
        return new ResearchTaskVO(t.getTaskId(),t.getTopic(),t.getStatus(),t.getCreatedAt(),t.getUpdatedAt(),decode(t.getEventsJson()),
            t.getReportJson()==null ? null : decode(t.getReportJson()),t.getErrorCode(),t.getErrorMessage(),t.getSyncError(),taskType(t));
    }
    private String taskType(ResearchTask t) { return decode(t.getPayloadJson()).path("task_type").asText("research"); }
    private String encode(Object value) {
        try { return json.writeValueAsString(value); }
        catch (JsonProcessingException ex) { throw new IllegalStateException("Research serialization failed",ex); }
    }
    private JsonNode decode(String value) {
        try { return json.readTree(value); }
        catch (JsonProcessingException ex) { throw new IllegalStateException("Research data unreadable",ex); }
    }
    private static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
    }
}
