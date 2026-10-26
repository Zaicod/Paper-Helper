package cn.paperflow.controller;
import cn.paperflow.auth.UserPrincipal;
import cn.paperflow.common.*;
import cn.paperflow.service.PaperDocumentService;
import cn.paperflow.vo.PaperDocumentVO;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;
@RestController
public class PaperDocumentController {
 private final PaperDocumentService documents;
 public PaperDocumentController(PaperDocumentService documents){this.documents=documents;}
 @GetMapping("/api/library/collections/{collection}/papers/{paper}/document")
 public Result<PaperDocumentVO> status(@AuthenticationPrincipal UserPrincipal user,@PathVariable long collection,@PathVariable long paper){return Result.success(documents.status(user.id(),collection,paper));}
 @PostMapping("/api/library/collections/{collection}/papers/{paper}/document/prepare")
 public Result<PaperDocumentVO> prepare(@AuthenticationPrincipal UserPrincipal user,@PathVariable long collection,@PathVariable long paper){return Result.success(documents.prepare(user.id(),collection,paper,null,null));}
 @PostMapping(value="/api/library/collections/{collection}/papers/{paper}/document",consumes=MediaType.MULTIPART_FORM_DATA_VALUE)
 public Result<PaperDocumentVO> upload(@AuthenticationPrincipal UserPrincipal user,@PathVariable long collection,@PathVariable long paper,@RequestParam("file") MultipartFile file)throws IOException{
  if(file.isEmpty()||file.getSize()>25L*1024*1024)throw new ApiException(HttpStatus.BAD_REQUEST,"请上传不超过25MiB的 PDF");
  byte[] content=file.getBytes();if(content.length<5||!new String(content,0,5,java.nio.charset.StandardCharsets.US_ASCII).equals("%PDF-"))throw new ApiException(HttpStatus.BAD_REQUEST,"文件不是有效 PDF");
  return Result.success(documents.prepare(user.id(),collection,paper,content,file.getOriginalFilename()));
 }
 @GetMapping("/api/library/documents/{id}/file")
 public ResponseEntity<byte[]> download(@AuthenticationPrincipal UserPrincipal user,@PathVariable String id){return ResponseEntity.ok().contentType(MediaType.APPLICATION_PDF).header("Cache-Control","no-store").header("X-Content-Type-Options","nosniff").header("Content-Disposition","attachment; filename=\"paper.pdf\"").body(documents.download(user.id(),id));}
}
