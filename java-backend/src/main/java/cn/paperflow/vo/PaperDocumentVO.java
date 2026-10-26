package cn.paperflow.vo;
import java.time.Instant;
public record PaperDocumentVO(String documentId,String status,String message,String filename,String sha256,
    String sourceKind,Integer pageCount,Instant preparedAt) {}
