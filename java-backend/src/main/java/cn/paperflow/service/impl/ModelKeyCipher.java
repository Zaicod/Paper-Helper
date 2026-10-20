package cn.paperflow.service.impl;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Value;
import javax.crypto.Cipher;
import javax.crypto.spec.*;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.*;
@Component public class ModelKeyCipher {
 private final Path file; private final SecureRandom random=new SecureRandom();
 public ModelKeyCipher(@Value("${paperflow.model-settings.key-file:./data/model-settings-master.key}") String file){this.file=Path.of(file).toAbsolutePath();}
 private synchronized byte[] key(boolean existing) throws Exception {
  if(!Files.exists(file)) {
   if(existing) throw new IllegalStateException("model_master_key_missing");
   Files.createDirectories(file.getParent());Path temporary=Files.createTempFile(file.getParent(),".master-",".tmp");
   try {
    var posix=Files.getFileAttributeView(temporary,PosixFileAttributeView.class);
    if(posix!=null)posix.setPermissions(PosixFilePermissions.fromString("rw-------"));
    var acl=Files.getFileAttributeView(temporary,AclFileAttributeView.class);
    if(acl!=null)acl.setAcl(List.of(AclEntry.newBuilder().setType(AclEntryType.ALLOW).setPrincipal(Files.getOwner(temporary)).setPermissions(EnumSet.allOf(AclEntryPermission.class)).build()));
    byte[] generated=new byte[32];random.nextBytes(generated);Files.write(temporary,generated,StandardOpenOption.TRUNCATE_EXISTING);
    try { Files.createLink(file,temporary); } catch(FileAlreadyExistsException raced) { /* Reuse the winning process's key. */ }
   } finally { Files.deleteIfExists(temporary); }
  }
  byte[] bytes=Files.readAllBytes(file);if(bytes.length!=32)throw new IllegalStateException("model_master_key_invalid");return bytes;
 }
 public String encrypt(String value,String context,boolean existing) {
  try {byte[] nonce=new byte[12];random.nextBytes(nonce);Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(key(existing),"AES"),new GCMParameterSpec(128,nonce));cipher.updateAAD(context.getBytes(StandardCharsets.UTF_8));byte[] ciphertext=cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));byte[] result=new byte[nonce.length+ciphertext.length];System.arraycopy(nonce,0,result,0,12);System.arraycopy(ciphertext,0,result,12,ciphertext.length);return Base64.getEncoder().encodeToString(result);}
  catch(Exception error){throw new IllegalStateException("model_key_unavailable");}
 }
 public String decrypt(String value,String context) {
  try {byte[] bytes=Base64.getDecoder().decode(value);Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,new SecretKeySpec(key(true),"AES"),new GCMParameterSpec(128,bytes,0,12));cipher.updateAAD(context.getBytes(StandardCharsets.UTF_8));return new String(cipher.doFinal(bytes,12,bytes.length-12),StandardCharsets.UTF_8);}
  catch(Exception error){throw new IllegalStateException("model_key_unavailable");}
 }
}
