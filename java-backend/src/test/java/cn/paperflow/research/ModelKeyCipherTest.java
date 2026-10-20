package cn.paperflow.settings;
import cn.paperflow.service.impl.ModelKeyCipher;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import static org.assertj.core.api.Assertions.*;
class ModelKeyCipherTest {
 @TempDir Path directory;
 @Test void persistsReusesAuthenticatesAndRefusesMissingExistingMaster() throws Exception {
  Path key=directory.resolve("master.key");var cipher=new ModelKeyCipher(key.toString());
  String encrypted=cipher.encrypt("secret-value", "7:qwen",false);
  assertThat(encrypted).doesNotContain("secret-value");
  assertThat(new ModelKeyCipher(key.toString()).decrypt(encrypted,"7:qwen")).isEqualTo("secret-value");
  assertThatThrownBy(()->cipher.decrypt(encrypted,"8:qwen")).isInstanceOf(RuntimeException.class);
  Files.delete(key);
  assertThatThrownBy(()->cipher.encrypt("replacement","7:qwen",true)).isInstanceOf(RuntimeException.class);
  assertThat(Files.exists(key)).isFalse();
 }
}
