package cn.paperflow.entity;

import java.time.Instant;

/** Database row mapped explicitly by MyBatis; never serialized as an API response. */
public class PaperCollection {
    private Long id;
    private Long ownerId;
    private String name;
    private String nameNormalized;
    private String description;
    private String overallNote;
    private Instant createdAt;

    public PaperCollection() {}
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public Long getOwnerId() { return ownerId; }
    public void setOwnerId(Long ownerId) { this.ownerId = ownerId; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getNameNormalized() { return nameNormalized; }
    public void setNameNormalized(String nameNormalized) { this.nameNormalized = nameNormalized; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public String getOverallNote() { return overallNote; }
    public void setOverallNote(String overallNote) { this.overallNote = overallNote; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
