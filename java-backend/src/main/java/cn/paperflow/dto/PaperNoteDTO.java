package cn.paperflow.dto;

import jakarta.validation.constraints.*;

public record PaperNoteDTO(@NotBlank @Size(max = 64) String source,
                             @NotBlank @Size(max = 255) String paperId,
                             @NotNull @Size(max = 50000) String content) {
    public PaperNoteDTO { source = source == null ? null : source.strip(); paperId = paperId == null ? null : paperId.strip(); }
}
