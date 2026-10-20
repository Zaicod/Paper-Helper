package cn.paperflow.service;

import cn.paperflow.dto.*;
import cn.paperflow.vo.*;

/** Business rules for a user's collections and personal notes. */
public interface LibraryService {
    CollectionPageVO list(long owner, String query, int page, int size);
    CollectionVO create(long owner, CollectionDTO input);
    CollectionVO update(long owner, long id, CollectionDTO input);
    CollectionDetailVO detail(long owner, long id);
    void delete(long owner, long id);
    String collectionNote(long owner, long id, String content);
    PaperVO addPaper(long owner, long id, PaperDTO input);
    PaperVO paper(long owner, long id, long paperId);
    PaperVO updatePaper(long owner, long id, long paperId, PaperDTO input);
    void removePaper(long owner, long id, long paperId);
    String paperNote(long owner, long id, PaperNoteDTO input);
}
