package cn.paperflow.dto;
import com.fasterxml.jackson.annotation.JsonProperty;
public record ModelSettingDTO(String model,@JsonProperty("api_key") String apiKey) {
 @Override public String toString(){return "ModelSettingDTO[redacted]";}
}
