package cn.paperflow.service;

import cn.paperflow.auth.UserPrincipal;

/** Authentication business rules, independent of HTTP and database access. */
public interface AuthService {
    UserPrincipal register(String username, String email, String password);
    UserPrincipal login(String identifier, String password);
}
