package vn.luatgt.controller;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import java.util.*;
import org.springframework.web.bind.annotation.*;
import vn.luatgt.dto.*;
import vn.luatgt.service.*;
@RestController @RequestMapping("/api")
public class KagController {
    private final KagSchema schema; private final LegalUnitService units; private final InfrastructureService infrastructure;
    public KagController(KagSchema schema,LegalUnitService units,InfrastructureService infrastructure) { this.schema=schema; this.units=units; this.infrastructure=infrastructure; }
    @GetMapping("/admin/kag/status") Map<String,Object> status() { return infrastructure.kagStatus(); }
    @GetMapping("/admin/kag/sample") JsonNode sample(@RequestParam Map<String,String> parameters) {
        if(!parameters.isEmpty())throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.BAD_REQUEST,"Inspection không nhận truy vấn tùy ý");
        return infrastructure.sampleInspection();
    }
    @GetMapping("/admin/kag/pipeline") JsonNode pipeline() { return infrastructure.pipelineStatus(); }
    @GetMapping("/admin/kag/benchmark/datasets") JsonNode datasets() { return infrastructure.benchmarkDatasets(); }
    @PostMapping("/admin/kag/retrieve") JsonNode retrieve(@Valid @RequestBody KagRetrieveRequest request) { return infrastructure.retrieve(request); }
    @GetMapping("/admin/kag/schema") Map<String,Object> schema() { return Map.of("identity",schema.identity(),"contract",schema.contract()); }
    @GetMapping("/admin/units") List<Map<String,Object>> admin(@RequestParam(required=false) String docId) { return units.list(docId,true); }
    @GetMapping("/units") List<Map<String,Object>> list(@RequestParam String docId) { return units.list(docId,false); }
    @PostMapping("/admin/imports/units/preview") List<Map<String,Object>> preview(@Valid @RequestBody ImportRequest request) { return units.preview(request); }
    @PostMapping("/admin/imports/units/confirm") Map<String,Integer> confirm(@Valid @RequestBody ImportRequest request) { return units.confirm(request); }
    @PutMapping("/admin/units/{id}") Map<String,Object> edit(@PathVariable UUID id,@Valid @RequestBody ContentChangeRequest request) { return units.edit(id,request); }
    @PostMapping("/admin/units/{id}/publication") Map<String,Object> publish(@PathVariable UUID id,@Valid @RequestBody PublicationRequest request) { return units.publish(id,request); }
}
