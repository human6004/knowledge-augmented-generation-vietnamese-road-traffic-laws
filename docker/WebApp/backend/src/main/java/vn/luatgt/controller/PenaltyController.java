package vn.luatgt.controller;
import vn.luatgt.dto.PenaltyRequest;
import vn.luatgt.service.PenaltyService;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api")
public class PenaltyController {
    private final PenaltyService service;
    public PenaltyController(PenaltyService service) { this.service=service; }
    @GetMapping("/penalties") List<Map<String,Object>> list() { return service.list(false); }
    @GetMapping("/admin/penalties") List<Map<String,Object>> admin() { return service.list(true); }
    @PostMapping("/admin/penalties") Map<String,Object> create(@Valid @RequestBody PenaltyRequest input) { return service.save(null,input); }
    @PutMapping("/admin/penalties/{id}") Map<String,Object> update(@PathVariable UUID id,@Valid @RequestBody PenaltyRequest input) { return service.save(id,input); }
}
