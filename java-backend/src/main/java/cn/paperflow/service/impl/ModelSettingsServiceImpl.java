package cn.paperflow.service.impl;
import cn.paperflow.service.ModelSettingsService;
import cn.paperflow.mapper.ModelSettingsMapper;
import cn.paperflow.entity.ModelSetting;
import cn.paperflow.dto.ModelSettingDTO;
import cn.paperflow.vo.*;
import cn.paperflow.client.WorkerClient;
import cn.paperflow.common.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
@Service public class ModelSettingsServiceImpl implements ModelSettingsService {
 private final ModelSettingsMapper mapper;private final ModelKeyCipher cipher;private final WorkerClient worker;private final ObjectMapper json;
 public ModelSettingsServiceImpl(ModelSettingsMapper mapper,ModelKeyCipher cipher,WorkerClient worker,ObjectMapper json){this.mapper=mapper;this.cipher=cipher;this.worker=worker;this.json=json;}
 private static String provider(String value){if(!Set.of("qwen","openai").contains(value==null?"":value))throw new ApiException(HttpStatus.BAD_REQUEST,"模型提供商无效");return value;}
 private static String defaultModel(String provider){return "qwen".equals(provider)?"qwen3.8-flash":"gpt-5.6-luna";}
 @Transactional(readOnly=true) public ModelSettingsVO get(long owner){return new ModelSettingsVO(mapper.defaultProvider(owner),List.of("qwen","openai").stream().map(p->{var row=mapper.find(owner,p);return new ModelSettingsVO.Provider(p,row==null?defaultModel(p):row.model(),row!=null&&row.keyCiphertext()!=null,row==null?null:row.keyHint());}).toList());}
 @Transactional public ModelSettingsVO save(long owner,String p,ModelSettingDTO input){provider(p);String model=input.model()==null?"":input.model().strip();if(model.isEmpty()||model.length()>128||model.codePoints().anyMatch(Character::isISOControl))throw new ApiException(HttpStatus.BAD_REQUEST,"模型名称无效");
  mapper.lockOwner(owner);var old=mapper.find(owner,p);String supplied=input.apiKey()==null?"":input.apiKey();String raw=supplied.strip();if(raw.length()>4096||supplied.codePoints().anyMatch(Character::isISOControl))throw new ApiException(HttpStatus.BAD_REQUEST,"API Key 格式无效");
  String encrypted=old==null?null:old.keyCiphertext();String hint=old==null?null:old.keyHint();
  if(!raw.isEmpty()){try{encrypted=cipher.encrypt(raw,owner+":"+p,mapper.ciphertextCount()>0);}catch(IllegalStateException ex){throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"模型密钥存储不可用，请恢复主密钥文件");}hint=raw.length()<=8?"••••":"••••"+raw.substring(raw.length()-4);}
  if(encrypted==null)throw new ApiException(HttpStatus.BAD_REQUEST,"首次保存请填写 API Key");var row=new ModelSetting(owner,p,model,encrypted,hint);if(old==null)mapper.insert(row);else mapper.update(row);return get(owner);
 }
 @Transactional public ModelSettingsVO setDefault(long owner,String p){
  mapper.lockOwner(owner);
  if(p!=null){
   provider(p);var row=mapper.find(owner,p);
   if(row==null||row.keyCiphertext()==null)throw new ApiException(HttpStatus.BAD_REQUEST,"请先保存 API Key");
   try { secret(owner,p); }
   catch(MissingCredentials ex){throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE,"模型密钥不可用，请恢复主密钥文件或重新保存 API Key");}
  }
  mapper.clearDefault(owner);if(p!=null)mapper.insertDefault(owner,p);return get(owner);
 }
 @Transactional public ModelSettingsVO deleteKey(long owner,String p){provider(p);mapper.lockOwner(owner);var row=mapper.find(owner,p);if(row!=null)mapper.update(new ModelSetting(owner,p,row.model(),null,null));return get(owner);}
 private String secret(long owner,String p){var row=mapper.find(owner,p);if(row==null||row.keyCiphertext()==null)throw new MissingCredentials();try{return cipher.decrypt(row.keyCiphertext(),owner+":"+p);}catch(IllegalStateException ex){throw new MissingCredentials();}}
 public ModelTestVO test(long owner,String p){provider(p);var row=mapper.find(owner,p);if(row==null||row.keyCiphertext()==null)throw new ApiException(HttpStatus.BAD_REQUEST,"请先保存 API Key");try{return worker.testModel(p,row.model(),secret(owner,p));}catch(InterruptedException ex){Thread.currentThread().interrupt();return new ModelTestVO(false,"连接测试已中断");}catch(Exception ex){return new ModelTestVO(false,"连接失败，请检查模型、API Key 和服务配置");}}
 public Selection resolve(long owner,String p,String model,boolean live){
  String personalDefault=live && p==null?mapper.defaultProvider(owner):null;
  String resolved=p!=null?p:personalDefault!=null?personalDefault:"qwen";
  var row=live && (p!=null || personalDefault!=null)?mapper.find(owner,resolved):null;
  return new Selection(resolved,model!=null?model:row==null?null:row.model(),row==null?"server":"personal");
 }
 public String dispatchPayload(long owner,String payload){try{ObjectNode body=(ObjectNode)json.readTree(payload);var options=body.path("options");if(!"personal".equals(options.path("credential_source").asText()))return payload;String p=provider(options.path("provider").asText());body.putObject("runtime_credentials").put("provider",p).put("api_key",secret(owner,p));return json.writeValueAsString(body);}catch(MissingCredentials ex){throw ex;}catch(Exception ex){throw new MissingCredentials();}}
}
