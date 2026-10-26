package cn.paperflow.research;
import cn.paperflow.dto.ResearchTaskDTO;
import org.junit.jupiter.api.Test;
import jakarta.validation.Validation;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
class DocumentDefaultTopicTest {
 @Test void selectedPaperGetsDefaultBeforeValidationButTopicOnlyStaysRequired() {
  var selected=new ResearchTaskDTO(UUID.randomUUID().toString(),"  ","live",1,"abstract",null,null,1L,List.of(1L),"study_report","","");
  assertThat(selected.topic()).contains("核心创新点").contains("不补造细节");
  try(var factory=Validation.buildDefaultValidatorFactory()) {
   assertThat(factory.getValidator().validate(selected)).isEmpty();
   assertThat(factory.getValidator().validate(new ResearchTaskDTO(UUID.randomUUID().toString()," ","live",1,"none",null,null,null,null,"search","",""))).isNotEmpty();
  }
 }
}
