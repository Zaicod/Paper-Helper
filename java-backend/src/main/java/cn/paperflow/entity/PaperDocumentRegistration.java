package cn.paperflow.entity;
import java.time.Instant;
public record PaperDocumentRegistration(String recordId,long ownerId,long collectionId,long paperId,
    String metadataHash,String documentId,String statusJson,Instant createdAt) {}
