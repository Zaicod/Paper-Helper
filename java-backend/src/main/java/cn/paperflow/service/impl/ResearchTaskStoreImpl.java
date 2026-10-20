package cn.paperflow.service.impl;

import cn.paperflow.mapper.ResearchTaskMapper;
import cn.paperflow.entity.ResearchTask;
import cn.paperflow.service.ResearchTaskStore;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;
import java.util.Set;

@Service
public class ResearchTaskStoreImpl implements ResearchTaskStore {
    private final ResearchTaskMapper tasks;
    private final ObjectMapper json;
    private static final Set<String> ACTIVE=Set.of("queued","running");
    public ResearchTaskStoreImpl(ResearchTaskMapper tasks,ObjectMapper json) { this.tasks=tasks; this.json=json; }
    @Transactional(readOnly=true)
    public List<Pending> pending() {
        return tasks.pending().stream().map(t -> new Pending(t.getTaskId(),t.getStatus(),t.getPayloadJson(),t.getDeadlineAt(),t.getOwnerId())).toList();
    }
    @Transactional
    public void apply(String id,JsonNode snapshot) {
        ResearchTask task=tasks.findById(id);
        if (task==null || !ACTIVE.contains(task.getStatus())) return;
        String status=snapshot.path("status").asText();
        if (task.getStatus().equals("running") && status.equals("queued")) {
            task.setSyncError("执行状态暂未同步，将继续查询");
        } else {
            task.setStatus(status); task.setEventsJson(snapshot.path("events").toString());
            task.setReportJson(status.equals("completed") ? snapshot.path("report").toString() : null);
            task.setSyncError(null);
            if (status.equals("failed") || status.equals("interrupted")) {
                task.setErrorCode(status.equals("interrupted") ? "worker_interrupted" : "research_failed");
                task.setErrorMessage(status.equals("interrupted") ? "Python 执行已中断，请查看记录后重新提交" : "研究执行失败，请检查 Python 服务配置与执行记录");
                if(status.equals("failed") && studyFailure(task,snapshot)) {
                    task.setErrorCode("study_report_failed");
                    task.setErrorMessage(snapshot.path("error_message").asText());
                }
            }
        }
        task.setUpdatedAt(Instant.now()); tasks.update(task);
    }
    private boolean studyFailure(ResearchTask task,JsonNode snapshot) {
        String message=snapshot.path("error_message").asText("");
        if(!"study_report_failed".equals(snapshot.path("error_code").asText())
            || !snapshot.path("error_message").isTextual() || message.isBlank() || message.length()>1000
            || message.codePoints().anyMatch(Character::isISOControl)) return false;
        try { return "study_report".equals(json.readTree(task.getPayloadJson()).path("task_type").asText()); }
        catch(java.io.IOException ex) { return false; }
    }
    @Transactional
    public void problem(String id,String code) {
        ResearchTask task=tasks.findById(id);
        if (task==null || !ACTIVE.contains(task.getStatus())) return;
        if(code.equals("model_credentials_missing")) {
            task.setStatus("failed");task.setErrorCode(code);task.setErrorMessage("个人模型 API Key 已删除或不可用，请在模型设置中重新保存后创建任务");task.setSyncError(null);
        } else if (code.equals("sync_deadline_exceeded") || code.equals("execution_lost")) {
            task.setStatus("interrupted"); task.setErrorCode(code);
            task.setErrorMessage(code.equals("execution_lost") ? "Python 执行记录已丢失，请检查服务数据目录" : "同步已超过期限，远端可能仍在执行，请检查后再决定是否重新提交");
            task.setSyncError(null);
        } else task.setSyncError("暂时无法同步 Python 执行状态，将使用同一任务 ID 重试");
        task.setUpdatedAt(Instant.now()); tasks.update(task);
    }
}
