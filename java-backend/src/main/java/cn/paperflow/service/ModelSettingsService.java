package cn.paperflow.service;
import cn.paperflow.dto.ModelSettingDTO;
import cn.paperflow.vo.*;
public interface ModelSettingsService {
 ModelSettingsVO get(long owner);
 ModelSettingsVO save(long owner,String provider,ModelSettingDTO input);
 ModelSettingsVO setDefault(long owner,String provider);
 ModelSettingsVO deleteKey(long owner,String provider);
 ModelTestVO test(long owner,String provider);
 record Selection(String provider,String model,String credentialSource){}
 Selection resolve(long owner,String provider,String model,boolean live);
 String dispatchPayload(long owner,String payload);
 class MissingCredentials extends RuntimeException { public MissingCredentials(){super("model_credentials_missing");} }
}
