package cn.paperflow.service;

import cn.paperflow.dto.ResearchTaskDTO;
import cn.paperflow.vo.*;

public interface ResearchTaskService {
    ResearchTaskVO submit(long owner,ResearchTaskDTO input);
    ResearchTaskVO retry(long owner,String id,cn.paperflow.dto.RetryTaskDTO input);
    ResearchTaskVO detail(long owner,String id);
    default ResearchTaskPageVO list(long owner,int page,int size) { return list(owner,page,size,null,null); }
    ResearchTaskPageVO list(long owner,int page,int size,String category,String keyword);
}
