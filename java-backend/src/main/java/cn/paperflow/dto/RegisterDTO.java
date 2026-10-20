package cn.paperflow.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** Only registration input; password hashes and account IDs cannot be supplied. */
public class RegisterDTO {
    @NotBlank @Size(min = 3, max = 64) @Pattern(regexp = "[\\p{L}\\p{N}_.-]+")
    private String username;
    @NotBlank @Email @Size(max = 320)
    private String email;
    @NotNull @Size(min = 8, max = 128)
    private String password;

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username == null ? null : username.trim(); }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email == null ? null : email.trim(); }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
}
