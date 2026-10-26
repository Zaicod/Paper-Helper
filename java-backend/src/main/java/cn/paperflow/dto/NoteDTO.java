package cn.paperflow.dto;

import jakarta.validation.constraints.*;

public record NoteDTO(@NotNull @Size(max = 50000) String content) {}
