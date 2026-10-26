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
    private final cn.paperflow.service.UserRateLimitService limits;
    private final cn.paperflow.service.PaperDocumentService documents;
    public ResearchTaskServiceImpl(ResearchTaskMapper tasks, LibraryService library, ObjectMapper json,
        WorkerClient worker, @Value("${paperflow.worker.task-timeout-seconds:1800}") long timeout) {
        this(tasks,library,json,worker,timeout,null);
    }
    public ResearchTaskServiceImpl(ResearchTaskMapper tasks, LibraryService library, ObjectMapper json,
        WorkerClient worker, @Value("${paperflow.worker.task-timeout-seconds:1800}") long timeout,cn.paperflow.service.ModelSettingsService settings) {
        this(tasks,library,json,worker,timeout,settings,null);
    }
    public ResearchTaskServiceImpl(ResearchTaskMapper tasks, LibraryService library, ObjectMapper json,
        WorkerClient worker,@Value("${paperflow.worker.task-timeout-seconds:1800}") long timeout,
        cn.paperflow.service.ModelSettingsService settings,cn.paperflow.service.UserRateLimitService limits) {
        this(tasks,library,json,worker,timeout,settings,limits,null);
    }
    @org.springframework.beans.factory.annotation.Autowired
    public ResearchTaskServiceImpl(ResearchTaskMapper tasks,LibraryService library,ObjectMapper json,WorkerClient worker,
        @Value("${paperflow.worker.task-timeout-seconds:1800}") long timeout,cn.paperflow.service.ModelSettingsService settings,
        cn.paperflow.service.UserRateLimitService limits,cn.paperflow.service.PaperDocumentService documents){
        this.tasks=tasks;this.library=library;this.json=json;this.worker=worker;this.timeout=Math.max(1,timeout);this.settings=settings;this.limits=limits;this.documents=documents;
    }
    @Transactional
    public ResearchTaskVO submit(long owner, ResearchTaskDTO input) {
        boolean study="study_report".equals(input.taskType());
        boolean search="search".equals(input.taskType());
        boolean citation="citation_trace".equals(input.taskType());
        if(!citation && input.citationDirection()!=null)
            throw new ApiException(HttpStatus.BAD_REQUEST,"引用追踪方向仅适用于引用追踪任务");
        if(citation && (!"live".equals(input.mode()) || !"none".equals(input.rag())
                || input.provider()!=null || input.model()!=null || input.collectionId()==null
                || input.paperIds()==null || input.paperIds().isEmpty() || input.paperIds().size()>5
                || !Set.of("references","citations","both").contains(input.citationDirection())))
            throw new ApiException(HttpStatus.BAD_REQUEST,"引用追踪需使用个人默认模型、live 模式、rag none，并选择本人收藏夹中的 1 至 5 篇种子论文");
        if(search && (!"live".equals(input.mode()) || !"none".equals(input.rag())
            || input.collectionId()!=null || input.paperIds()!=null || input.provider()!=null || input.model()!=null))
            throw new ApiException(HttpStatus.BAD_REQUEST,"智能搜索需使用个人默认模型、live 模式和 rag none，不能选择收藏论文或指定模型");
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
        if(search || citation) checkSearchQuota(owner);
        if (!worker.configured()) throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"尚未配置 Python 研究服务");
        Map<String,Object> payload=new LinkedHashMap<>();
        payload.put("contract_version",1); payload.put("topic",input.topic()); payload.put("limit",input.limit());
        // Only the authenticated owner determines which persisted vector index this task can access.
        payload.put("index_namespace","java-user:"+owner);
        payload.put("task_type",input.taskType());
        if(citation) payload.put("citation_direction",input.citationDirection());
        if(study) {
            payload.put("learning_goal",input.learningGoal()); payload.put("reflection",input.reflection());
        }
        Map<String,Object> options=new LinkedHashMap<>();
        var selection=settings==null ? new cn.paperflow.service.ModelSettingsService.Selection(input.provider()==null?"qwen":input.provider(),input.model(),"server") : settings.resolve(owner,input.provider(),input.model(),"live".equals(input.mode()));
        if(search || citation) requirePersonal(selection);
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
            if(citation && stored.size()>5) throw new ApiException(HttpStatus.BAD_REQUEST,"引用追踪最多选择 5 篇种子论文");
            if(citation) payload.put("library_selection",Map.of("collection_id",input.collectionId(),"paper_ids",stored.stream().map(PaperVO::id).toList()));
            if (stored.stream().map(p->p.paperId()).distinct().count()!=stored.size())
                throw new ApiException(HttpStatus.BAD_REQUEST,"论文外部 ID 重复，请缩小选择范围");
            if(study) {
                if(documents==null)throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"正文准备服务尚未配置");
                payload.put("prepared_documents",documents.requireReady(owner,input.collectionId(),stored));
                payload.put("library_selection",Map.of("collection_id",input.collectionId(),"paper_ids",stored.stream().map(PaperVO::id).toList()));
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
        if(limits!=null) limits.generation(owner);
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
        boolean search=Set.of("search","citation_trace").contains(snapshot.path("task_type").asText());
        if(search) checkSearchQuota(owner);
        JsonNode papers=snapshot.path("papers");
        if(papers.isArray()) for(JsonNode paper:papers) {
            if(tasks.countOwnedPaper(owner,paper.path("source").asText(),paper.path("paper_id").asText())==0)
                throw new ApiException(HttpStatus.BAD_REQUEST,"原任务中的论文已不在本人的收藏夹中，请重新选择论文后创建任务");
        }
        // Copy only the persisted, nonsecret input contract. Credentials are attached at dispatch.
        var payload=json.createObjectNode();
        for(String field:List.of("contract_version","topic","limit","task_type","learning_goal","reflection","notes","collection_note","papers","prepared_documents","library_selection","citation_direction")) {
            if(snapshot.has(field)) payload.set(field,snapshot.get(field).deepCopy());
        }
        payload.put("index_namespace","java-user:"+owner);
        JsonNode oldOptions=snapshot.path("options");
        boolean live="live".equals(oldOptions.path("mode").asText());
        var selection=settings==null ? new cn.paperflow.service.ModelSettingsService.Selection("qwen",null,"server")
            : settings.resolve(owner,null,null,live);
        if(search) requirePersonal(selection);
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
        if(limits!=null) limits.generation(owner);
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
    @Transactional
    public ResearchTaskVO repair(long owner,String id,cn.paperflow.dto.RetryTaskDTO input){
        tasks.lockOwner(owner);var original=tasks.findOwned(id,owner);
        if(original==null)throw new ApiException(HttpStatus.NOT_FOUND,"研究任务不存在");
        String requestHash=hash("repair-study:"+id);var existing=tasks.findRequest(owner,input.idempotencyKey());
        if(existing!=null){if(!requestHash.equals(existing.getRequestHash()))throw new ApiException(HttpStatus.CONFLICT,"该请求标识已用于不同操作");return view(existing);}
        var old=decode(original.getPayloadJson());
        if(!"study_report".equals(old.path("task_type").asText())||!Set.of("failed","interrupted").contains(original.getStatus()))throw new ApiException(HttpStatus.CONFLICT,"仅失败或中断的学习报告可以修复后重新创建");
        if(!worker.configured()||documents==null)throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"正文服务尚未配置");
        // Legacy snapshots may contain runtime credentials; copy only the approved input fields.
        var payload=json.createObjectNode();
        for(String field:List.of("contract_version","topic","task_type","learning_goal","reflection"))
            if(old.has(field))payload.set(field,old.get(field).deepCopy());
        var updated=new ArrayList<Map<String,Object>>();var prepared=new LinkedHashMap<String,String>();var notes=new LinkedHashMap<String,String>();
        var currentCollections=new LinkedHashMap<Long,String>();var currentPaperIds=new ArrayList<Long>();
        for(var previous:old.path("papers")){
            var location=tasks.findOwnedPaperLocation(owner,previous.path("source").asText(),previous.path("paper_id").asText());
            if(location==null)throw new ApiException(HttpStatus.BAD_REQUEST,"原论文已不在本人收藏夹，请重新选择论文");
            long collection=location.collectionId();
            if(old.path("library_selection").path("collection_id").canConvertToLong())collection=old.path("library_selection").path("collection_id").asLong();
            var current=library.paper(owner,collection,location.paperId());
            currentCollections.computeIfAbsent(collection,c->library.detail(owner,c).overallNote());currentPaperIds.add(current.id());
            updated.add(cn.paperflow.service.PaperDocumentService.snapshot(current));
            prepared.putAll(documents.requireReady(owner,collection,List.of(current)));notes.put(current.paperId(),current.note()==null?"":current.note());
        }
        if(updated.isEmpty())throw new ApiException(HttpStatus.BAD_REQUEST,"原任务没有可修复的论文");
        if(currentCollections.size()==1)payload.set("library_selection",json.valueToTree(Map.of("collection_id",currentCollections.keySet().iterator().next(),"paper_ids",currentPaperIds)));
        else payload.remove("library_selection");
        payload.put("collection_note",currentCollections.values().stream().filter(Objects::nonNull).collect(java.util.stream.Collectors.joining("\n\n")));
        payload.put("limit",updated.size());
        payload.set("papers",json.valueToTree(updated));payload.set("prepared_documents",json.valueToTree(prepared));payload.set("notes",json.valueToTree(notes));payload.put("index_namespace","java-user:"+owner);
        var selection=settings==null?new cn.paperflow.service.ModelSettingsService.Selection("qwen",null,"server"):settings.resolve(owner,null,null,true);
        var options=payload.putObject("options");options.put("mode","live");options.put("rag","abstract");options.put("provider",selection.provider());options.put("credential_source",selection.credentialSource());if(selection.model()!=null)options.put("model",selection.model());
        String encoded=encode(payload);if(encoded.getBytes(StandardCharsets.UTF_8).length>2*1024*1024)throw new ApiException(HttpStatus.BAD_REQUEST,"任务资料过大，请减少笔记");
        if(limits!=null)limits.generation(owner);
        var task=new ResearchTask();task.setTaskId(UUID.randomUUID().toString());task.setOwnerId(owner);task.setIdempotencyKey(input.idempotencyKey());task.setRequestHash(requestHash);task.setTopic(original.getTopic());task.setPayloadJson(encoded);task.setStatus("queued");task.setEventsJson("[]");task.setCreatedAt(java.time.Instant.now());task.setUpdatedAt(task.getCreatedAt());task.setDeadlineAt(task.getCreatedAt().plusSeconds(timeout));tasks.insert(task);return view(task);
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
    private void checkSearchQuota(long owner) {
        long active=tasks.listOwned(owner,0,Integer.MAX_VALUE,List.of("queued","running"),null).stream()
            .filter(t -> Set.of("search","citation_trace").contains(taskType(t))).count();
        if(active>=2) throw new ApiException(HttpStatus.TOO_MANY_REQUESTS,"最多同时执行 2 个智能搜索或引用追踪任务，请等待已有任务结束");
    }
    private static void requirePersonal(cn.paperflow.service.ModelSettingsService.Selection selection) {
        if(!"personal".equals(selection.credentialSource()))
            throw new ApiException(HttpStatus.BAD_REQUEST,"请先在模型设置中保存 API Key 并选择个人默认模型，再使用智能搜索或引用追踪");
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
