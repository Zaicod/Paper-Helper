package cn.paperflow.vo;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
public record ResearchTaskPageVO(List<ResearchTaskSummaryVO> tasks, long total, int page, int size) {}
