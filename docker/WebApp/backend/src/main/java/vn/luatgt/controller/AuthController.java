package vn.luatgt.controller;

import jakarta.validation.Valid;
import java.util.*;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.*;
import vn.luatgt.dto.LoginRequest;
import vn.luatgt.dto.RegisterRequest;
import vn.luatgt.service.AuthService;

@RestController @RequestMapping("/api/auth")
public class AuthController {
    private final AuthService service;
    public AuthController(AuthService service) { this.service=service; }
    @PostMapping("/register") Map<String,Object> register(@Valid @RequestBody RegisterRequest input,jakarta.servlet.http.HttpServletRequest request) { return service.register(input,request.getRemoteAddr()); }
    @PostMapping("/login") Map<String,Object> login(@Valid @RequestBody LoginRequest input,jakarta.servlet.http.HttpServletRequest request) { return service.login(input,request.getRemoteAddr()); }
    @GetMapping("/me") Map<String,Object> me(JwtAuthenticationToken auth) { return service.me(auth); }
    @PostMapping("/logout") void logout(JwtAuthenticationToken auth) { service.logout(auth); }
}
