package cn.paperflow.entity;

import java.time.Instant;

/** Database row mapped explicitly by MyBatis; never serialized as an API response. */
public class Paper {
    private Long id;
    private String source;
    private String externalId;
    private String title;
    private String abstractText;
    private String authorsJson;
    private String categoriesJson;
    private String published;
    private String pageUrl;
    private String pdfUrl;
    private Instant createdAt;

    public Paper() {}
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getExternalId() { return externalId; }
    public void setExternalId(String externalId) { this.externalId = externalId; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getAbstractText() { return abstractText; }
    public void setAbstractText(String abstractText) { this.abstractText = abstractText; }
    public String getAuthorsJson() { return authorsJson; }
    public void setAuthorsJson(String authorsJson) { this.authorsJson = authorsJson; }
    public String getCategoriesJson() { return categoriesJson; }
    public void setCategoriesJson(String categoriesJson) { this.categoriesJson = categoriesJson; }
    public String getPublished() { return published; }
    public void setPublished(String published) { this.published = published; }
    public String getPageUrl() { return pageUrl; }
    public void setPageUrl(String pageUrl) { this.pageUrl = pageUrl; }
    public String getPdfUrl() { return pdfUrl; }
    public void setPdfUrl(String pdfUrl) { this.pdfUrl = pdfUrl; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
