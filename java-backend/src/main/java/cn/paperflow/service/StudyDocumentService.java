package cn.paperflow.service;

/** Export the persisted study snapshot after checking task ownership. */
public interface StudyDocumentService {
    byte[] download(long owner,String taskId);
}
