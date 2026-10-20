package cn.paperflow.controller;

import cn.paperflow.auth.UserPrincipal;
import cn.paperflow.common.Result;
import cn.paperflow.dto.RegisterDTO;
import cn.paperflow.dto.LoginDTO;
import cn.paperflow.service.AuthService;
import cn.paperflow.vo.UserVO;
import cn.paperflow.vo.CsrfVO;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.servlet.http.Cookie;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthService auth;
    private final HttpSessionSecurityContextRepository contexts;
    private final HttpSessionCsrfTokenRepository csrfTokens;
    private final boolean secureCookies;

    public AuthController(AuthService auth, HttpSessionSecurityContextRepository contexts,
                          HttpSessionCsrfTokenRepository csrfTokens,
                          @Value("${server.servlet.session.cookie.secure:false}") boolean secureCookies) {
        this.auth = auth;
        this.contexts = contexts;
        this.csrfTokens = csrfTokens;
        this.secureCookies = secureCookies;
    }

    @GetMapping("/csrf")
    public Result<CsrfVO> csrf(CsrfToken token) { return Result.success(new CsrfVO(token.getToken(), token.getHeaderName())); }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<UserVO> register(@Valid @RequestBody RegisterDTO body, HttpServletRequest request, HttpServletResponse response) {
        return Result.success(signIn(auth.register(body.getUsername(), body.getEmail(), body.getPassword()), request, response));
    }

    @PostMapping("/login")
    public Result<UserVO> login(@Valid @RequestBody LoginDTO body, HttpServletRequest request, HttpServletResponse response) {
        return Result.success(signIn(auth.login(body.getIdentifier(), body.getPassword()), request, response));
    }

    @GetMapping("/me")
    public Result<UserVO> me(@AuthenticationPrincipal UserPrincipal user) { return Result.success(UserVO.from(user)); }

    @PostMapping("/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void logout(HttpServletRequest request, HttpServletResponse response) {
        HttpSession session = request.getSession(false);
        if (session != null) session.invalidate();
        SecurityContextHolder.clearContext();
        Cookie cookie = new Cookie("paperflow_java_session", "");
        cookie.setMaxAge(0);
        cookie.setHttpOnly(true);
        cookie.setSecure(secureCookies);
        cookie.setPath("/");
        cookie.setAttribute("SameSite", "Lax");
        response.addCookie(cookie);
    }

    private UserVO signIn(UserPrincipal user, HttpServletRequest request, HttpServletResponse response) {
        request.getSession(true);
        request.changeSessionId();
        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(UsernamePasswordAuthenticationToken.authenticated(user, null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
        SecurityContextHolder.setContext(context);
        contexts.saveContext(context, request, response);
        // The client obtains a new masked token after each authentication transition.
        csrfTokens.saveToken(null, request, response);
        return UserVO.from(user);
    }

}
