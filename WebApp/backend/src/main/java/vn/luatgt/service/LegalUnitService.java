package vn.luatgt.service;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.dto.*;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.model.*;
import vn.luatgt.repository.*;

@Service
public class LegalUnitService {
    private final LegalUnitRepository units; private final ContentRepository documents;
    private final ContentService content; private final KagSchema schema;
    public LegalUnitService(LegalUnitRepository units,ContentRepository documents,ContentService content,KagSchema schema) { this.units=units; this.documents=documents; this.content=content; this.schema=schema; }
    public ObjectNode read(LegalUnit unit) { try { return (ObjectNode)content.mapper().readTree(unit.data); } catch(Exception e) { throw new IllegalStateException(e); } }
    private Content document(ObjectNode n) { return documents.findByKindAndExternalId("documents",KagSchema.exactId(n,"doc_id",250)).orElseThrow(() -> ApiErrors.bad("doc_id chưa có trong thư viện văn bản")); }
    private ObjectNode validate(JsonNode input) {
        if(!input.isObject()) throw ApiErrors.bad("Mỗi đơn vị pháp lý cần object JSON");
        var n=schema.normalize("units",(ObjectNode)input); n.remove(List.of("published","version","id"));
        if(content.write(n).length()>100_000) throw ApiErrors.bad("Đơn vị pháp lý quá lớn");
        KagSchema.exactId(n,"unit_id",500); document(n);
        for(String key:List.of("so_hieu","unit_type","text")) if(!n.path(key).isTextual()||n.path(key).asText().isBlank()) throw ApiErrors.bad(key+": cần chuỗi không trống");
        if(!n.path("order").isIntegralNumber()||!n.path("order").canConvertToInt()||n.path("order").asInt()<0) throw ApiErrors.bad("order: cần số nguyên không âm");
        if(n.hasNonNull("parent_id")) KagSchema.exactId(n,"parent_id",500);
        if(n.hasNonNull("reviewed")&&!n.path("reviewed").isBoolean()) throw ApiErrors.bad("reviewed: cần boolean");
        return n;
    }
    private void hierarchy(ObjectNode n,Map<String,ObjectNode> pending) {
        var seen=new HashSet<String>(); seen.add(n.path("unit_id").asText());
        String docId=n.path("doc_id").asText(); var cursor=n;
        while(cursor.hasNonNull("parent_id")) {
            String parent=cursor.path("parent_id").asText();
            if(!seen.add(parent)) throw ApiErrors.bad("parent_id tạo vòng lặp");
            cursor=pending.get(parent);
            if(cursor==null) cursor=units.findByUnitId(parent).map(this::read).orElseThrow(() -> ApiErrors.bad("parent_id chưa tồn tại"));
            if(!cursor.path("doc_id").asText().equals(docId)) throw ApiErrors.bad("parent_id thuộc văn bản khác");
        }
    }
    private Map<String,Object> view(LegalUnit u) { return Map.of("id",u.id,"externalId",u.unitId,"version",u.version,"published",u.published,"data",read(u)); }
    public List<Map<String,Object>> list(String docId,boolean admin) {
        var rows=docId==null?units.findAll():documents.findByKindAndExternalId("documents",docId).map(d -> units.findByDocumentIdOrderByUnitId(d.id)).orElse(List.of());
        return rows.stream().filter(u -> admin||u.published&&documents.findById(u.documentId).map(d -> d.published&&content.isEffective(d)).orElse(false))
            .sorted(Comparator.comparing((LegalUnit u) -> read(u).path("order").asInt()).thenComparing(u -> u.unitId)).map(this::view).toList();
    }
    public List<Map<String,Object>> preview(ImportRequest request) {
        var result=new ArrayList<Map<String,Object>>(); var seen=new HashSet<String>(); var pending=new HashMap<String,ObjectNode>(); int row=0;
        for(var input:request.rows()) {
            row++;
            try { var n=validate(input); String id=n.path("unit_id").asText(); if(!seen.add(id)) throw ApiErrors.bad("Trùng unit_id trong tệp");
                var existing=units.findByUnitId(id); pending.put(id,existing.isPresent()&&!request.updateExisting()?read(existing.get()):n);
                result.add(Map.of("row",row,"valid",true,"existing",existing.isPresent(),"data",n));
            } catch(ResponseStatusException e) { result.add(Map.of("row",row,"valid",false,"message",Objects.requireNonNull(e.getReason()))); }
        }
        for(int i=0;i<result.size();i++) if(Boolean.TRUE.equals(result.get(i).get("valid"))) {
            var value=result.get(i);
            try { hierarchy((ObjectNode)value.get("data"),pending); }
            catch(ResponseStatusException e) { result.set(i,Map.of("row",value.get("row"),"valid",false,"message",Objects.requireNonNull(e.getReason()))); }
        }
        return result;
    }
    @Transactional public Map<String,Integer> confirm(ImportRequest request) {
        // ponytail: serialize hierarchy changes on document rows; use per-document locks if ingestion throughput requires it.
        documents.lockDocuments();
        var pending=new LinkedHashMap<String,ObjectNode>(); int inserted=0,updated=0,skipped=0;
        var seen=new HashSet<String>();
        for(var input:request.rows()) {
            var n=validate(input); String id=n.path("unit_id").asText(); if(!seen.add(id)) throw ApiErrors.bad("Trùng unit_id trong tệp");
            var existing=units.findByUnitId(id);
            if(existing.isPresent()&&!request.updateExisting()) { skipped++; continue; }
            if(existing.isPresent()&&!read(existing.get()).path("doc_id").equals(n.path("doc_id"))) throw ApiErrors.bad("Không đổi doc_id của unit đã có");
            pending.put(id,n);
        }
        for(var n:pending.values()) hierarchy(n,pending);
        for(var entry:pending.entrySet()) {
            var existing=units.findByUnitId(entry.getKey()); var u=existing.orElseGet(LegalUnit::new);
            if(existing.isPresent()) updated++; else inserted++;
            u.unitId=entry.getKey(); u.documentId=document(entry.getValue()).id; u.data=content.write(entry.getValue()); u.published=false; units.save(u);
        }
        units.flush(); return Map.of("inserted",inserted,"updated",updated,"skipped",skipped);
    }
    @Transactional public Map<String,Object> edit(UUID id,ContentChangeRequest input) {
        documents.lockDocuments();
        var u=units.findById(id).orElseThrow(ApiErrors::missing);
        if(u.version!=input.version()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Đơn vị pháp lý vừa thay đổi");
        var n=validate(input.data());
        if(!u.unitId.equals(n.path("unit_id").asText())||!u.documentId.equals(document(n).id)) throw ApiErrors.bad("Không đổi unit_id/doc_id; tạo bản nháp mới nếu nguồn khác");
        hierarchy(n,Map.of(u.unitId,n)); u.data=content.write(n); u.published=false; return view(units.saveAndFlush(u));
    }
    @Transactional public Map<String,Object> publish(UUID id,PublicationRequest input) {
        documents.lockDocuments();
        var u=units.findById(id).orElseThrow(ApiErrors::missing);
        if(u.version!=input.version()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Đơn vị pháp lý vừa thay đổi");
        if(input.published()) { var n=validate(read(u)); hierarchy(n,Map.of());
            if(!n.path("reviewed").asBoolean(false)||!document(n).published) throw ApiErrors.bad("Cần duyệt unit và xuất bản văn bản nguồn trước"); }
        u.published=input.published(); return view(units.saveAndFlush(u));
    }
    public boolean citation(String docId,String unitId,String quote) {
        return units.findByUnitId(unitId).filter(u -> u.published&&read(u).path("doc_id").asText().equals(docId)&&!quote.isBlank()&&read(u).path("text").asText().contains(quote)).isPresent();
    }
}
