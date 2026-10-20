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
        @Pattern(regexp="research|study_report") String taskType,
        @Size(max=2000) String learningGoal,
        @Size(max=50000) String reflection) {
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
            learningGoal = learningGoal == null ? "" : learningGoal.strip();
            reflection = reflection == null ? "" : reflection.strip();
        }
    }
