package vn.luatgt.controller;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.web.bind.annotation.*;
import vn.luatgt.dto.*;
import vn.luatgt.service.*;
@RestController @RequestMapping("/api")
public class KagController {
    private final KagSchema schema; private final LegalUnitService units;
    public KagController(KagSchema schema,LegalUnitService units) { this.schema=schema; this.units=units; }
    @GetMapping("/admin/kag/schema") Map<String,Object> schema() { return Map.of("identity",schema.identity(),"contract",schema.contract()); }
    @GetMapping("/admin/units") List<Map<String,Object>> admin(@RequestParam(required=false) String docId) { return units.list(docId,true); }
    @GetMapping("/units") List<Map<String,Object>> list(@RequestParam String docId) { return units.list(docId,false); }
    @PostMapping("/admin/imports/units/preview") List<Map<String,Object>> preview(@Valid @RequestBody ImportRequest request) { return units.preview(request); }
    @PostMapping("/admin/imports/units/confirm") Map<String,Integer> confirm(@Valid @RequestBody ImportRequest request) { return units.confirm(request); }
    @PutMapping("/admin/units/{id}") Map<String,Object> edit(@PathVariable UUID id,@Valid @RequestBody ContentChangeRequest request) { return units.edit(id,request); }
    @PostMapping("/admin/units/{id}/publication") Map<String,Object> publish(@PathVariable UUID id,@Valid @RequestBody PublicationRequest request) { return units.publish(id,request); }
}
