package cn.paperflow.controller;

import cn.paperflow.auth.UserPrincipal;
import cn.paperflow.common.Result;
import cn.paperflow.dto.ResearchTaskDTO;
import cn.paperflow.service.ResearchTaskService;
import cn.paperflow.service.StudyDocumentService;
import cn.paperflow.vo.*;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController @RequestMapping("/api/research/tasks")
public class ResearchController {
    private final ResearchTaskService service;
    private final StudyDocumentService documents;
    public ResearchController(ResearchTaskService service,StudyDocumentService documents) { this.service=service; this.documents=documents; }
    @PostMapping @ResponseStatus(HttpStatus.ACCEPTED)
    public Result<ResearchTaskVO> submit(@AuthenticationPrincipal UserPrincipal user,@Valid @RequestBody ResearchTaskDTO input) {
        return Result.success(service.submit(user.id(),input));
    }
    @PostMapping("/{id}/retry") @ResponseStatus(HttpStatus.ACCEPTED)
    public Result<ResearchTaskVO> retry(@AuthenticationPrincipal UserPrincipal user,@PathVariable String id,
        @Valid @RequestBody cn.paperflow.dto.RetryTaskDTO input) {
        return Result.success(service.retry(user.id(),id,input));
    }
    @GetMapping("/{id}")
    public Result<ResearchTaskVO> detail(@AuthenticationPrincipal UserPrincipal user,@PathVariable String id) {
        return Result.success(service.detail(user.id(),id));
    }
    @GetMapping("/{id}/document")
    public ResponseEntity<byte[]> document(@AuthenticationPrincipal UserPrincipal user,@PathVariable String id) {
        return ResponseEntity.ok().contentType(MediaType.parseMediaType("application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
            .header("Content-Disposition","attachment; filename=\"paperflow-study-report.docx\"")
            .header("Cache-Control","no-store").body(documents.download(user.id(),id));
    }
    @GetMapping
    public Result<ResearchTaskPageVO> list(@AuthenticationPrincipal UserPrincipal user,@RequestParam(defaultValue="0") int page,
        @RequestParam(defaultValue="10") int size,@RequestParam(required=false) String category,
        @RequestParam(required=false) String keyword) { return Result.success(service.list(user.id(),page,size,category,keyword)); }
}
