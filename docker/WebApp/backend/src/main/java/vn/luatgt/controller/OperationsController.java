package vn.luatgt.controller;
import vn.luatgt.service.*;
import vn.luatgt.dto.*;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api")
public class OperationsController {
    private final ModerationService moderation; private final LawService law;
    private final InfrastructureService infrastructure;
    public OperationsController(ModerationService moderation,LawService law,InfrastructureService infrastructure) { this.moderation=moderation; this.law=law; this.infrastructure=infrastructure; }
    @GetMapping("/admin/infrastructure") Map<String,String> infrastructure() { return infrastructure.status(); }
    @PostMapping("/chat/{id}/feedback") void feedback(@PathVariable UUID id,@Valid @RequestBody FeedbackRequest input,JwtAuthenticationToken auth) { moderation.feedback(id,AuthService.user(auth),input); }
    @GetMapping("/admin/chatlogs") List<Map<String,Object>> logs(@RequestParam(defaultValue="false") boolean pending) { return moderation.logs(pending); }
    @PostMapping("/admin/chatlogs/{id}/resolve") void resolve(@PathVariable UUID id,@Valid @RequestBody ResolutionRequest input) { moderation.resolve(id,input); }
    @GetMapping("/admin/reports") Map<String,Object> report() { return moderation.report(); }
    @GetMapping("/admin/law-relations") List<Map<String,Object>> relations() { return law.relations(); }
    @PostMapping("/admin/law-relations") void relate(@Valid @RequestBody LawRelationRequest input) { law.relate(input); }
    @PutMapping("/admin/law-relations/{id}") void updateRelation(@PathVariable UUID id,@Valid @RequestBody LawRelationRequest input) { law.update(id,input); }
    @GetMapping("/admin/content/{id}/history") List<Map<String,Object>> history(@PathVariable UUID id) { return law.history(id); }
}
