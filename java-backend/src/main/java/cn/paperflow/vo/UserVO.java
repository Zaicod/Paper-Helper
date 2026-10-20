package cn.paperflow.vo;

import cn.paperflow.auth.UserPrincipal;
import java.time.Instant;

/** Public account fields only; never serialize the database entity. */
public class UserVO {
    private final long id;
    private final String username;
    private final String email;
    private final Instant createdAt;

    public UserVO(long id, String username, String email, Instant createdAt) {
        this.id = id;
        this.username = username;
        this.email = email;
        this.createdAt = createdAt;
    }
    public long getId() { return id; }
    public String getUsername() { return username; }
    public String getEmail() { return email; }
    public Instant getCreatedAt() { return createdAt; }

    public static UserVO from(UserPrincipal principal) {
        return new UserVO(principal.id(), principal.username(), principal.email(), principal.createdAt());
    }
}
