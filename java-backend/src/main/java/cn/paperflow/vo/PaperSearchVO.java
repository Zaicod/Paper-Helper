package cn.paperflow.vo;

import cn.paperflow.dto.PaperDTO;
import cn.paperflow.dto.SearchKeywordDTO;
import java.util.List;

public record PaperSearchVO(int contractVersion,String query,String requestedSource,String usedSource,List<PaperSearchItemVO> papers,
                            List<SourceWarning> warnings,Integer page,Integer pageSize,Long total,Boolean hasNext,String sort,
                            List<SearchKeywordDTO> keywords) {
    public record SourceWarning(String source,String code,String message) {}
}
