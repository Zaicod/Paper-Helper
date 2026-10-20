package cn.paperflow.settings;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.dto.ModelSettingDTO;
import cn.paperflow.entity.ModelSetting;
import cn.paperflow.mapper.ModelSettingsMapper;
import cn.paperflow.service.ModelSettingsService;
import cn.paperflow.service.impl.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
class ModelSettingsResolutionTest {
 @TempDir Path directory;
 @Test void cannotSelectDefaultWhenSavedCredentialCannotBeDecrypted() {
  var mapper=mock(ModelSettingsMapper.class);var cipher=new ModelKeyCipher(directory.resolve("missing-key").toString());
  var service=new ModelSettingsServiceImpl(mapper,cipher,mock(WorkerClient.class),new ObjectMapper());
  when(mapper.find(7,"qwen")).thenReturn(new ModelSetting(7,"qwen","saved-qwen","unreadable-ciphertext","••••"));
  assertThatThrownBy(()->service.setDefault(7,"qwen")).isInstanceOf(cn.paperflow.common.ApiException.class);
  verify(mapper,never()).insertDefault(anyLong(),anyString());
 }
 @Test void nullDefaultPreservesServerButExplicitProviderUsesSavedSettingsAndDeletedKeyNeverFallsBack() {
  var mapper=mock(ModelSettingsMapper.class);var cipher=new ModelKeyCipher(directory.resolve("key").toString());
  var service=new ModelSettingsServiceImpl(mapper,cipher,mock(WorkerClient.class),new ObjectMapper());
  String encrypted=cipher.encrypt("distinct-personal-secret","7:qwen",false);
  when(mapper.find(7,"qwen")).thenReturn(new ModelSetting(7,"qwen","saved-qwen",encrypted,"••••cret"));
  assertThat(service.resolve(7,null,null,true)).isEqualTo(new ModelSettingsService.Selection("qwen",null,"server"));
  assertThat(service.resolve(7,"qwen",null,true)).isEqualTo(new ModelSettingsService.Selection("qwen","saved-qwen","personal"));
  assertThat(service.resolve(7,"qwen","override",false)).isEqualTo(new ModelSettingsService.Selection("qwen","override","server"));
  when(mapper.defaultProvider(7)).thenReturn("qwen");
  assertThat(service.resolve(7,null,null,true)).isEqualTo(new ModelSettingsService.Selection("qwen","saved-qwen","personal"));
  String durable="{\"options\":{\"provider\":\"qwen\",\"credential_source\":\"personal\"}}";
  assertThat(service.dispatchPayload(7,durable)).contains("runtime_credentials","distinct-personal-secret");
  when(mapper.find(7,"qwen")).thenReturn(new ModelSetting(7,"qwen","saved-qwen",null,null));
  assertThat(service.resolve(7,"qwen",null,true).credentialSource()).isEqualTo("personal");
  assertThatThrownBy(()->service.dispatchPayload(7,durable)).isInstanceOf(ModelSettingsService.MissingCredentials.class);
 }
}
