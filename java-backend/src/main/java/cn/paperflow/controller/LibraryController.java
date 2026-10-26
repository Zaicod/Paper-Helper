package cn.paperflow.controller;

import cn.paperflow.common.Result;
import cn.paperflow.service.LibraryService;
import cn.paperflow.dto.*;
import cn.paperflow.vo.*;

import cn.paperflow.auth.UserPrincipal;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/library/collections")
public class LibraryController {
    private final LibraryService library;
    public LibraryController(LibraryService library) { this.library = library; }

    @GetMapping
    public Result<CollectionPageVO> list(@AuthenticationPrincipal UserPrincipal user,
                               @RequestParam(defaultValue = "") String query,
                               @RequestParam(defaultValue = "0") int page,
                               @RequestParam(defaultValue = "20") int size) {
        return Result.success(library.list(user.id(), query, page, size));
    }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    public Result<CollectionVO> create(@AuthenticationPrincipal UserPrincipal user, @Valid @RequestBody CollectionDTO body) {
        return Result.success(library.create(user.id(), body));
    }
    @GetMapping("/{id}")
    public Result<CollectionDetailVO> detail(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id) {
        return Result.success(library.detail(user.id(), id));
    }
    @PutMapping("/{id}")
    public Result<CollectionVO> update(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id,
                                    @Valid @RequestBody CollectionDTO body) {
        return Result.success(library.update(user.id(), id, body));
    }
    @DeleteMapping("/{id}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id) { library.delete(user.id(), id); }
    @PutMapping("/{id}/note")
    public Result<Map<String, String>> note(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id,
                                    @Valid @RequestBody NoteDTO body) {
        return Result.success(Map.of("content", library.collectionNote(user.id(), id, body.content())));
    }
    @PostMapping("/{id}/papers") @ResponseStatus(HttpStatus.CREATED)
    public Result<PaperVO> addPaper(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id,
                              @Valid @RequestBody PaperDTO body) {
        return Result.success(library.addPaper(user.id(), id, body));
    }
    @GetMapping("/{id}/papers/{paperRecordId}")
    public Result<PaperVO> paper(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id,
                                @PathVariable long paperRecordId) {
        return Result.success(library.paper(user.id(), id, paperRecordId));
    }
    @PutMapping("/{id}/papers/{paperRecordId}")
    public Result<PaperVO> updatePaper(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id,
                                      @PathVariable long paperRecordId, @Valid @RequestBody PaperDTO body) {
        return Result.success(library.updatePaper(user.id(), id, paperRecordId, body));
    }
    @DeleteMapping("/{id}/papers/{paperRecordId}") @ResponseStatus(HttpStatus.NO_CONTENT)
    public void removePaper(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id, @PathVariable long paperRecordId) {
        library.removePaper(user.id(), id, paperRecordId);
    }
    @PutMapping("/{id}/paper-note")
    public Result<Map<String, String>> paperNote(@AuthenticationPrincipal UserPrincipal user, @PathVariable long id,
                                         @Valid @RequestBody PaperNoteDTO body) {
        return Result.success(Map.of("content", library.paperNote(user.id(), id, body)));
    }
}
