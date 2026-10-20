package cn.paperflow.service;

import cn.paperflow.vo.PaperSearchVO;

public interface PaperSearchService {
    PaperSearchVO search(String query,String source,int limit);
    PaperSearchVO search(String query,String source,int limit,Integer page,String sort);
    PaperSearchVO search(String query,String source,int limit,Integer page,String sort,String keywords);
}
