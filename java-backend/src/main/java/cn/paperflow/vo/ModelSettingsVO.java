package cn.paperflow.vo;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
public record ModelSettingsVO(@JsonProperty("default_provider") String defaultProvider,List<Provider> providers) {
 public record Provider(String provider,String model,boolean configured,@JsonProperty("key_hint") String keyHint){}
}
