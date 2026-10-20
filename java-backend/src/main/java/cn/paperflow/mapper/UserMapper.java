package cn.paperflow.mapper;

import cn.paperflow.entity.UserAccount;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

@Mapper
public interface UserMapper {
    @Select("SELECT COUNT(*) FROM pf_users WHERE username_normalized = #{username}")
    long countByUsernameNormalized(@Param("username") String username);

    @Select("SELECT COUNT(*) FROM pf_users WHERE email_normalized = #{email}")
    long countByEmailNormalized(@Param("email") String email);

    @Select("""
        SELECT id, username, username_normalized, email, email_normalized, password_hash, created_at
        FROM pf_users WHERE username_normalized = #{identifier} OR email_normalized = #{identifier}
        """)
    UserAccount findByIdentifier(@Param("identifier") String identifier);

    @Insert("""
        INSERT INTO pf_users(username, username_normalized, email, email_normalized, password_hash, created_at)
        VALUES (#{username}, #{usernameNormalized}, #{email}, #{emailNormalized}, #{passwordHash}, #{createdAt})
        """)
    @Options(useGeneratedKeys = true, keyProperty = "id", keyColumn = "id")
    int insert(UserAccount account);
}
