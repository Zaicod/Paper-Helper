package cn.paperflow.entity;

import java.time.Instant;

/** Database row mapped explicitly by MyBatis; never serialized as an API response. */
public class CollectionPaper {
    private Long id;
    private Long collectionId;
    private Long paperId;
    private String note;
    private Instant addedAt;
    private String metadataJson;
    private boolean metadataEdited;

    public CollectionPaper() {}
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getCollectionId() { return collectionId; }
    public void setCollectionId(Long collectionId) { this.collectionId = collectionId; }
    public Long getPaperId() { return paperId; }
    public void setPaperId(Long paperId) { this.paperId = paperId; }
    public String getNote() { return note; }
    public void setNote(String note) { this.note = note; }
    public Instant getAddedAt() { return addedAt; }
    public void setAddedAt(Instant addedAt) { this.addedAt = addedAt; }
    public String getMetadataJson() { return metadataJson; }
    public void setMetadataJson(String metadataJson) { this.metadataJson = metadataJson; }
    public boolean isMetadataEdited() { return metadataEdited; }
    public void setMetadataEdited(boolean metadataEdited) { this.metadataEdited = metadataEdited; }
}
