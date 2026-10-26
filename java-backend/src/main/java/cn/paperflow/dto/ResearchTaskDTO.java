package cn.paperflow.dto;
import jakarta.validation.constraints.*;
import java.util.List;
public record ResearchTaskDTO(
        @NotBlank @Pattern(regexp="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}") String idempotencyKey,
        @NotBlank @Size(max=500) String topic,
        @NotNull @Pattern(regexp="demo|live") String mode,
        @Min(1) @Max(20) Integer limit,
        @Pattern(regexp="none|abstract") String rag,
        @Pattern(regexp="qwen|openai") String provider,
        @Size(min=1,max=128) String model,
        @Positive Long collectionId,
        @Size(min=1,max=20) List<@NotNull @Positive Long> paperIds,
        @Pattern(regexp="research|study_report|search|citation_trace") String taskType,
        @Size(max=2000) String learningGoal,
        @Size(max=50000) String reflection,
        @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
        @Pattern(regexp="references|citations|both") String citationDirection) {
        public static final String DEFAULT_CITATION_TOPIC="围绕所选论文的研究主题，追踪相关参考文献及后续研究，并说明相关性与发现路径。";
        public ResearchTaskDTO(String idempotencyKey,String topic,String mode,Integer limit,String rag,String provider,
            String model,Long collectionId,List<Long> paperIds,String taskType,String learningGoal,String reflection) {
            this(idempotencyKey,topic,mode,limit,rag,provider,model,collectionId,paperIds,taskType,learningGoal,reflection,null);
        }
        @AssertTrue(message="引用追踪方向仅适用于引用追踪任务")
        @com.fasterxml.jackson.annotation.JsonIgnore
        public boolean isCitationDirectionValid() { return citationDirection==null || "citation_trace".equals(taskType); }
        public static final String DEFAULT_PAPER_TOPIC="请基于所选论文，分析研究背景与解决的问题、核心创新点、模型总体架构及各模块作用、实验设置与主要结果、局限性，以及可改进的方向。对正文未提供的信息明确标注，不补造细节。";
        public ResearchTaskDTO(String idempotencyKey,String topic,String mode,Integer limit,String rag,String provider,
            String model,Long collectionId,List<Long> paperIds) {
            this(idempotencyKey,topic,mode,limit,rag,provider,model,collectionId,paperIds,"research","","");
        }
        public ResearchTaskDTO {
            topic = topic == null ? null : topic.strip();
            idempotencyKey = idempotencyKey == null ? null : idempotencyKey.toLowerCase(java.util.Locale.ROOT);
            limit = limit == null ? 3 : limit;
            rag = rag == null ? "abstract" : rag;
            model = model == null ? null : model.strip();
            paperIds = paperIds == null ? null : List.copyOf(paperIds);
            taskType = taskType == null ? "research" : taskType;
            if("citation_trace".equals(taskType)) {
                citationDirection=citationDirection==null ? "both" : citationDirection;
                if(topic==null||topic.isBlank())topic=DEFAULT_CITATION_TOPIC;
            } else if((topic==null||topic.isBlank())&&collectionId!=null&&!"search".equals(taskType))topic=DEFAULT_PAPER_TOPIC;
            learningGoal = learningGoal == null ? "" : learningGoal.strip();
            reflection = reflection == null ? "" : reflection.strip();
        }
    }
