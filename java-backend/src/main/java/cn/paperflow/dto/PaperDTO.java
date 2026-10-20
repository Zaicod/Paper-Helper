package cn.paperflow.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.*;
import java.util.List;

public record PaperDTO(
    @NotBlank @Size(max = 64) String source,
    @NotBlank @Size(max = 255) String paperId,
    @NotBlank @Size(max = 1024) String title,
    @JsonProperty("abstract") @NotNull @Size(max = 10000) String abstractText,
    @NotNull @Size(max = 50) List<@NotBlank @Size(max = 128) String> authors,
    @NotNull @Size(max = 50) List<@NotBlank @Size(max = 64) String> categories,
    @Size(max = 64) String published,
    @NotBlank @Size(max = 2048) String pageUrl,
    @Size(max = 2048) String pdfUrl) {
    public PaperDTO {
        source = source == null ? null : source.strip(); paperId = paperId == null ? null : paperId.strip(); title = title == null ? null : title.strip();
        abstractText = abstractText == null ? "" : abstractText;
        authors = authors == null ? List.of() : List.copyOf(authors);
        categories = categories == null ? List.of() : List.copyOf(categories);
        pageUrl = pageUrl == null ? null : pageUrl.strip(); pdfUrl = pdfUrl == null ? null : pdfUrl.strip();
        if (pdfUrl != null && pdfUrl.isEmpty()) pdfUrl = null;
    }
}
