package cn.paperflow.service.impl;

import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import cn.paperflow.service.ResearchTaskService;
import cn.paperflow.service.StudyDocumentService;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import java.io.IOException;

@Service
public class StudyDocumentServiceImpl implements StudyDocumentService {
    private final ResearchTaskService tasks;
    private final WorkerClient worker;
    public StudyDocumentServiceImpl(ResearchTaskService tasks,WorkerClient worker) {
        this.tasks=tasks; this.worker=worker;
    }
    public byte[] download(long owner,String taskId) {
        var task=tasks.detail(owner,taskId);
        if(!"completed".equals(task.status()) || task.report()==null
            || !"study_report".equals(task.report().path("report_type").asText()))
            throw new ApiException(HttpStatus.CONFLICT,"只有已完成的学习报告可以下载 Word 文档");
        if(!worker.configured()) throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"尚未配置 Python 文档服务");
        try { return worker.studyDocument(task.report()); }
        catch(java.net.http.HttpTimeoutException ex) { throw new ApiException(HttpStatus.GATEWAY_TIMEOUT,"学习报告文档导出超时，请稍后重试"); }
        catch(InterruptedException ex) { Thread.currentThread().interrupt(); throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"学习报告文档导出已中断"); }
        catch(IOException ex) { throw new ApiException(HttpStatus.BAD_GATEWAY,"学习报告文档暂时无法导出，请稍后重试"); }
    }
}
