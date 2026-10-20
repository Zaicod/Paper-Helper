package cn.paperflow.dto;

import jakarta.validation.constraints.*;
import java.text.Normalizer;

public record CollectionDTO(@NotBlank @Size(max = 255) String name,
                              @NotNull @Size(max = 2000) String description) {
    public CollectionDTO {
        name = name == null ? null : Normalizer.normalize(name, Normalizer.Form.NFKC).strip();
        description = description == null ? "" : description;
    }
}
