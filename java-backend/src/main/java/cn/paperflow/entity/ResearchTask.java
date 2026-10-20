package cn.paperflow.entity;

import java.time.Instant;

/** 数据库任务记录，与接口 DTO/VO 分开。 */
public class ResearchTask {
    private String taskId;
    private long ownerId;
    private String idempotencyKey;
    private String requestHash;
    private String topic;
    private String status;
    private String payloadJson;
    private String eventsJson;
    private String reportJson;
    private String errorCode;
    private String errorMessage;
    private String syncError;
    private Instant createdAt;
    private Instant updatedAt;
    private Instant deadlineAt;
    private long version;
    public String getTaskId() { return taskId; }
    public void setTaskId(String value) { this.taskId = value; }
    public long getOwnerId() { return ownerId; }
    public void setOwnerId(long value) { this.ownerId = value; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String value) { this.idempotencyKey = value; }
    public String getRequestHash() { return requestHash; }
    public void setRequestHash(String value) { this.requestHash = value; }
    public String getTopic() { return topic; }
    public void setTopic(String value) { this.topic = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { this.status = value; }
    public String getPayloadJson() { return payloadJson; }
    public void setPayloadJson(String value) { this.payloadJson = value; }
    public String getEventsJson() { return eventsJson; }
    public void setEventsJson(String value) { this.eventsJson = value; }
    public String getReportJson() { return reportJson; }
    public void setReportJson(String value) { this.reportJson = value; }
    public String getErrorCode() { return errorCode; }
    public void setErrorCode(String value) { this.errorCode = value; }
    public String getErrorMessage() { return errorMessage; }
    public void setErrorMessage(String value) { this.errorMessage = value; }
    public String getSyncError() { return syncError; }
    public void setSyncError(String value) { this.syncError = value; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { this.createdAt = value; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { this.updatedAt = value; }
    public Instant getDeadlineAt() { return deadlineAt; }
    public void setDeadlineAt(Instant value) { this.deadlineAt = value; }
    public long getVersion() { return version; }
    public void setVersion(long value) { this.version = value; }
}
