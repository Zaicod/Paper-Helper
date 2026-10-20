package cn.paperflow.service;

import cn.paperflow.dto.SearchKeywordDTO;
import cn.paperflow.vo.PaperSearchVO;
import java.util.List;
import java.util.Optional;

public interface PaperSearchCacheService {
    String key(String query,String source,int limit,Integer page,String sort,List<SearchKeywordDTO> keywords);
    Optional<PaperSearchVO> get(String key);
    void put(String key,PaperSearchVO result);
    void evict(String key);
}
