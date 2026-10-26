package cn.paperflow.vo;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
public record ResearchTaskSummaryVO(String taskId, String topic, String status, Instant createdAt, Instant updatedAt, String taskType) {}
