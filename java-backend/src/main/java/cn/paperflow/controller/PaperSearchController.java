package cn.paperflow.controller;

import cn.paperflow.common.Result;
import cn.paperflow.service.PaperSearchService;
import cn.paperflow.vo.PaperSearchVO;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/papers")
public class PaperSearchController {
    private final PaperSearchService service;
    private final cn.paperflow.service.UserRateLimitService limits;
    public PaperSearchController(PaperSearchService service,cn.paperflow.service.UserRateLimitService limits){this.service=service;this.limits=limits;}
    @GetMapping("/search")
    public Result<PaperSearchVO> search(@org.springframework.security.core.annotation.AuthenticationPrincipal cn.paperflow.auth.UserPrincipal user,
        @RequestParam(required=false) String query,@RequestParam(defaultValue="auto") String source,
        @RequestParam(defaultValue="10") int limit,@RequestParam(required=false) Integer page,
        @RequestParam(defaultValue="relevance") String sort,@RequestParam(required=false) String keywords){
        limits.search(user.id());
        return Result.success(service.search(query,source,limit,page,sort,keywords));}
}
