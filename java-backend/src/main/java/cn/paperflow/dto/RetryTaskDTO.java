package cn.paperflow.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import java.util.Locale;

public record RetryTaskDTO(
    @NotBlank @Pattern(regexp="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}") String idempotencyKey) {
    public RetryTaskDTO { idempotencyKey=idempotencyKey==null?null:idempotencyKey.toLowerCase(Locale.ROOT); }
}
