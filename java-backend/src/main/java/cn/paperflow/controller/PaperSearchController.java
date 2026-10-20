package cn.paperflow.controller;

import cn.paperflow.common.Result;
import cn.paperflow.service.PaperSearchService;
import cn.paperflow.vo.PaperSearchVO;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/papers")
public class PaperSearchController {
    private final PaperSearchService service;
    public PaperSearchController(PaperSearchService service){this.service=service;}
    @GetMapping("/search")
    public Result<PaperSearchVO> search(@RequestParam(required=false) String query,@RequestParam(defaultValue="auto") String source,
        @RequestParam(defaultValue="10") int limit,@RequestParam(required=false) Integer page,
        @RequestParam(defaultValue="relevance") String sort,@RequestParam(required=false) String keywords){
        return Result.success(service.search(query,source,limit,page,sort,keywords));}
}
