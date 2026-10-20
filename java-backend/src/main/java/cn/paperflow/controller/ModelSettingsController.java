package cn.paperflow.controller;
import cn.paperflow.auth.UserPrincipal;
import cn.paperflow.common.Result;
import cn.paperflow.dto.*;
import cn.paperflow.vo.*;
import cn.paperflow.service.ModelSettingsService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/model-settings")
public class ModelSettingsController {
 private final ModelSettingsService settings;public ModelSettingsController(ModelSettingsService settings){this.settings=settings;}
 @GetMapping public Result<ModelSettingsVO> get(@AuthenticationPrincipal UserPrincipal user){return Result.success(settings.get(user.id()));}
 @PutMapping("/{provider}") public Result<ModelSettingsVO> save(@AuthenticationPrincipal UserPrincipal user,@PathVariable String provider,@RequestBody ModelSettingDTO body){return Result.success(settings.save(user.id(),provider,body));}
 @PutMapping("/default") public Result<ModelSettingsVO> defaults(@AuthenticationPrincipal UserPrincipal user,@RequestBody DefaultModelDTO body){return Result.success(settings.setDefault(user.id(),body.provider()));}
 @DeleteMapping("/{provider}/key") public Result<ModelSettingsVO> delete(@AuthenticationPrincipal UserPrincipal user,@PathVariable String provider){return Result.success(settings.deleteKey(user.id(),provider));}
 @PostMapping("/{provider}/test") public Result<ModelTestVO> test(@AuthenticationPrincipal UserPrincipal user,@PathVariable String provider){return Result.success(settings.test(user.id(),provider));}
}
