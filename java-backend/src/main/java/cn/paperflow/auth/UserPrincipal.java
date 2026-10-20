package cn.paperflow.auth;

import cn.paperflow.entity.UserAccount;

import java.io.Serial;
import java.io.Serializable;
import java.security.Principal;
import java.time.Instant;

/** Session data deliberately contains no password hash or database entity. */
public record UserPrincipal(long id, String username, String email, Instant createdAt)
        implements Principal, Serializable {
    @Serial private static final long serialVersionUID = 1L;
    @Override public String getName() { return username; }
    public static UserPrincipal from(UserAccount account) {
        return new UserPrincipal(account.getId(), account.getUsername(), account.getEmail(), account.getCreatedAt());
    }
}
