package cn.paperflow.mapper;
import cn.paperflow.entity.ModelSetting;
import org.apache.ibatis.annotations.*;
@Mapper public interface ModelSettingsMapper {
 @Select("SELECT owner_id,provider,model,key_ciphertext,key_hint FROM pf_model_settings WHERE owner_id=#{owner} AND provider=#{provider}") ModelSetting find(@Param("owner") long owner,@Param("provider") String provider);
 @Select("SELECT COUNT(*) FROM pf_model_settings WHERE key_ciphertext IS NOT NULL") long ciphertextCount();
 @Select("SELECT id FROM pf_users WHERE id=#{owner} FOR UPDATE") Long lockOwner(long owner);
 @Insert("INSERT INTO pf_model_settings(owner_id,provider,model,key_ciphertext,key_hint) VALUES(#{ownerId},#{provider},#{model},#{keyCiphertext},#{keyHint})") void insert(ModelSetting setting);
 @Update("UPDATE pf_model_settings SET model=#{model},key_ciphertext=#{keyCiphertext},key_hint=#{keyHint} WHERE owner_id=#{ownerId} AND provider=#{provider}") void update(ModelSetting setting);
 @Select("SELECT provider FROM pf_model_defaults WHERE owner_id=#{owner}") String defaultProvider(long owner);
 @Delete("DELETE FROM pf_model_defaults WHERE owner_id=#{owner}") void clearDefault(long owner);
 @Insert("INSERT INTO pf_model_defaults(owner_id,provider) VALUES(#{owner},#{provider})") void insertDefault(@Param("owner") long owner,@Param("provider") String provider);
}
