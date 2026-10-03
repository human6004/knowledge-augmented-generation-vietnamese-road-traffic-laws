package vn.luatgt.controller;

import jakarta.validation.Valid;
import java.util.*;
import org.springframework.web.bind.annotation.*;
import vn.luatgt.dto.UserStatusRequest;
import vn.luatgt.service.UserService;

@RestController @RequestMapping("/api/admin/users")
public class UserController {
    private final UserService service;
    public UserController(UserService service) { this.service=service; }
    @GetMapping List<Map<String,Object>> list() { return service.list(); }
    @PatchMapping("/{id}") void status(@PathVariable UUID id,@Valid @RequestBody UserStatusRequest input) { service.status(id,input.enabled()); }
}
