package cn.paperflow.vo;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
public record ResearchTaskVO(String taskId, String topic, String status, Instant createdAt, Instant updatedAt,
        JsonNode events, JsonNode report, String errorCode, String errorMessage, String syncError, String taskType) {}
