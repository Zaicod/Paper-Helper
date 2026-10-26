package cn.paperflow.service.impl;

import cn.paperflow.auth.UserPrincipal;
import cn.paperflow.entity.UserAccount;
import cn.paperflow.mapper.UserMapper;
import cn.paperflow.service.AuthService;

import cn.paperflow.common.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

@Service
public class AuthServiceImpl implements AuthService {
    private final UserMapper users;
    private final PasswordEncoder passwords;
    private final String unknownPasswordHash;

    public AuthServiceImpl(UserMapper users, PasswordEncoder passwords) {
        this.users = users;
        this.passwords = passwords;
        this.unknownPasswordHash = passwords.encode(UUID.randomUUID().toString());
    }

    @Transactional
    public UserPrincipal register(String username, String email, String password) {
        if (password.getBytes(StandardCharsets.UTF_8).length > 72) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "密码的 UTF-8 编码不能超过 72 字节");
        }
        String normalizedUsername = normalize(username);
        String normalizedEmail = normalize(email);
        if (users.countByUsernameNormalized(normalizedUsername) > 0 || users.countByEmailNormalized(normalizedEmail) > 0) {
            throw new ApiException(HttpStatus.CONFLICT, "用户名或邮箱已被注册");
        }
        UserAccount account = new UserAccount();
        account.setUsername(username);
        account.setUsernameNormalized(normalizedUsername);
        account.setEmail(email);
        account.setEmailNormalized(normalizedEmail);
        account.setPasswordHash(passwords.encode(password));
        account.setCreatedAt(java.time.Instant.now());
        users.insert(account);
        return UserPrincipal.from(account);
    }

    @Transactional(readOnly = true)
    public UserPrincipal login(String identifier, String password) {
        String normalized = normalize(identifier);
        UserAccount account = users.findByIdentifier(normalized);
        // Hash unknown users too, avoiding a fast path that reveals account existence.
        String hash = account == null ? unknownPasswordHash : account.getPasswordHash();
        boolean validLength = password.getBytes(StandardCharsets.UTF_8).length <= 72;
        boolean matches = passwords.matches(validLength ? password : "invalid-password-length", hash);
        if (account == null || !validLength || !matches) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "用户名、邮箱或密码错误");
        }
        return UserPrincipal.from(account);
    }

    private static String normalize(String value) { return value.trim().toLowerCase(Locale.ROOT); }
}
