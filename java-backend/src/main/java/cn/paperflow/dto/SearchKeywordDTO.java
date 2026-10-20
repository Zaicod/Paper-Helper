package cn.paperflow.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;

/** A literal user term, never a provider query expression. */
public record SearchKeywordDTO(@NotBlank @Size(max=500) String text,
    @JsonProperty("match_mode") @NotNull @Pattern(regexp="exact|fuzzy") String matchMode) {
    public SearchKeywordDTO { text=text==null ? null : text.strip(); }
}
