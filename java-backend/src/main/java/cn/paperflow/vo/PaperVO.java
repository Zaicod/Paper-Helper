package cn.paperflow.vo;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;
import java.util.List;

public record PaperVO(long id, String source, String paperId, String title,
                        @JsonProperty("abstract") String abstractText,
                        List<String> authors, List<String> categories, String published,
                        String pageUrl, String pdfUrl, Instant addedAt, String note, boolean metadataEdited) {}
