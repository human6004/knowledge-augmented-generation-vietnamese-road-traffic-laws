package vn.luatgt.service;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.LocalDate;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.dto.ContentChangeRequest;
import vn.luatgt.dto.ImportRequest;
import vn.luatgt.dto.PublicationRequest;
import vn.luatgt.dto.BatchPublicationRequest;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.model.Content;
import vn.luatgt.repository.ContentRepository;
import vn.luatgt.repository.ContentHistoryRepository;
import vn.luatgt.repository.LawRelationRepository;
import vn.luatgt.model.ContentHistory;

@Service
public class ContentService {
    private final ContentRepository contents; private final ObjectMapper json;
    private final ContentHistoryRepository history; private final LawRelationRepository relations;
    public ObjectMapper mapper() { return json; }
    public ContentService(ContentRepository contents,ObjectMapper json,ContentHistoryRepository history,LawRelationRepository relations) { this.contents=contents; this.json=json; this.history=history; this.relations=relations; }
    public void remember(Content c) { var h=new ContentHistory(); h.contentId=c.id; h.contentVersion=c.version; h.data=c.data; h.published=c.published; history.save(h); }
    public boolean isEffective(Content c) {
        if(!effective(read(c))) return false;
        return !c.kind.equals("documents")||relations.findAll().stream().noneMatch(r -> r.predecessor.equals(c.id)&&r.type.equals("REPLACES")&&!r.effectiveDate.isAfter(LocalDate.now())&&contents.findById(r.successor).map(next -> next.published&&effective(read(next))).orElse(false));
    }
    public static void kind(String kind) { if(!Set.of("questions","signs","documents").contains(kind)) throw ApiErrors.bad("Loại dữ liệu không hợp lệ"); }
    public ObjectNode read(Content c) { try { return (ObjectNode)json.readTree(c.data); } catch(Exception e) { throw new IllegalStateException(e); } }
    public String write(JsonNode data) { try { return json.writeValueAsString(data); } catch(Exception e) { throw new IllegalStateException(e); } }
    public static String text(ObjectNode n,String field,int max,boolean required) {
        JsonNode value=n.get(field);
        if(value!=null && !value.isNull() && !value.isTextual()) throw ApiErrors.bad(field+": cần chuỗi");
        String s=value==null||value.isNull()?"":value.asText().trim();
        if(s.length()>max || required && s.isBlank()) throw ApiErrors.bad(field+": trống hoặc quá dài");
        n.put(field,s); return s;
    }
    public static void alias(ObjectNode n,String target,String source) { if(!n.has(target)&&n.has(source)) n.set(target,n.get(source)); }
    public static void date(ObjectNode n,String key,boolean required) {
        if(!n.hasNonNull(key)||n.path(key).asText().isBlank()) { if(required) throw ApiErrors.bad(key+": thiếu ngày"); n.putNull(key); return; }
        try { LocalDate.parse(n.get(key).textValue()); } catch(Exception e) { throw ApiErrors.bad(key+": phải là YYYY-MM-DD"); }
    }
    public ObjectNode validate(String kind,JsonNode input,boolean publish) {
        kind(kind);
        if(!input.isObject()) throw ApiErrors.bad("Mỗi dòng cần là object JSON");
        ObjectNode n=((ObjectNode)input).deepCopy();
        if(write(n).length()>50_000) throw ApiErrors.bad("Dòng dữ liệu quá lớn");
        n.remove(List.of("published","version","id"));
        if(n.hasNonNull("reviewed")&&!n.get("reviewed").isBoolean()) throw ApiErrors.bad("reviewed: phải là boolean");
        if(kind.equals("questions")) {
            alias(n,"externalId","code"); alias(n,"text","question"); alias(n,"correctAnswer","answer");
            text(n,"externalId",250,true); text(n,"text",5000,true);
            if(!n.path("chapter").isIntegralNumber() || !n.path("chapter").canConvertToInt() || n.path("chapter").asInt()<1 || n.path("chapter").asInt()>6) throw ApiErrors.bad("chapter: cần số từ 1 đến 6");
            var options=n.path("options");
            if(!options.isArray() || options.size()<2 || options.size()>4) throw ApiErrors.bad("options: cần 2–4 đáp án");
            for(var option:options) if(!option.isTextual() || option.asText().isBlank() || option.asText().length()>3000) throw ApiErrors.bad("Đáp án trống hoặc quá dài");
            if(n.hasNonNull("correctAnswer") && (!n.get("correctAnswer").isIntegralNumber() || !n.get("correctAnswer").canConvertToInt() || n.get("correctAnswer").asInt()<0 || n.get("correctAnswer").asInt()>=options.size())) throw ApiErrors.bad("correctAnswer: chỉ số từ 0");
            if(n.hasNonNull("critical") && !n.get("critical").isBoolean()) throw ApiErrors.bad("critical: phải là boolean");
            if(n.hasNonNull("imageRequired") && !n.get("imageRequired").isBoolean()) throw ApiErrors.bad("imageRequired: phải là boolean");
            text(n,"source",2000,publish); text(n,"explanation",10000,false);
            if(publish && (!n.hasNonNull("correctAnswer")||!n.hasNonNull("critical")||!n.path("reviewed").asBoolean(false))) throw ApiErrors.bad("Cần kiểm duyệt đáp án, phân loại điểm liệt và reviewed=true");
            if(publish && n.path("imageRequired").asBoolean(false) && !n.hasNonNull("imageKey")) throw ApiErrors.bad("Câu hỏi còn thiếu ảnh");
        } else if(kind.equals("signs")) {
            alias(n,"externalId","sign_id"); alias(n,"code","ma_bien"); alias(n,"name","ten"); alias(n,"group","nhom"); alias(n,"meaning","mo_ta");
            if(!n.hasNonNull("externalId")) n.put("externalId",n.path("code").asText());
            text(n,"externalId",250,true); text(n,"code",100,true); text(n,"name",500,true);
            text(n,"group",200,true); text(n,"meaning",20000,publish);
            text(n,"doc_id",250,publish); text(n,"unit_id",500,publish); text(n,"qcvn",200,publish); text(n,"so_hieu",200,publish);
            date(n,"ngay_hieu_luc",publish); date(n,"ngay_het_hieu_luc",false);
            if(publish && (!n.path("reviewed").asBoolean(false)||!n.hasNonNull("imageKey"))) throw ApiErrors.bad("Biển báo cần ảnh và reviewed=true trước khi xuất bản");
        } else {
            alias(n,"externalId","doc_id"); text(n,"externalId",250,true); text(n,"title",1000,true);
            text(n,"so_hieu",200,publish); text(n,"source",2000,publish);
            date(n,"ngay_hieu_luc",publish); date(n,"ngay_het_hieu_luc",false);
            if(publish && (!n.path("reviewed").asBoolean(false)||!n.hasNonNull("fileKey"))) throw ApiErrors.bad("Văn bản cần tệp nguồn và reviewed=true");
        }
        if(n.hasNonNull("ngay_hieu_luc")&&n.hasNonNull("ngay_het_hieu_luc") && LocalDate.parse(n.path("ngay_het_hieu_luc").asText()).isBefore(LocalDate.parse(n.path("ngay_hieu_luc").asText()))) throw ApiErrors.bad("Ngày hết hiệu lực trước ngày hiệu lực");
        return n;
    }
    public Map<String,Object> view(Content c,boolean admin) {
        var n=read(c);
        if(!admin&&c.kind.equals("questions")) n.retain(List.of("externalId","text","chapter","options","source","imageRequired","imageKey","imageMime"));
        return Map.of("id",c.id,"externalId",c.externalId,"version",c.version,"published",c.published,"data",n);
    }
    public static boolean effective(ObjectNode n) {
        LocalDate today=LocalDate.now();
        return (!n.hasNonNull("ngay_hieu_luc")||!LocalDate.parse(n.path("ngay_hieu_luc").asText()).isAfter(today))
            && (!n.hasNonNull("ngay_het_hieu_luc")||LocalDate.parse(n.path("ngay_het_hieu_luc").asText()).isAfter(today));
    }
    
    public List<Map<String,Object>> list(String kind,Integer chapter) {
        return contents.findByKindAndPublishedTrueOrderByExternalId(kind).stream()
            .filter(c -> isEffective(c) && (chapter==null||read(c).path("chapter").asInt()==chapter)).map(c -> view(c,false)).toList();
    }
    
    public List<Map<String,Object>> admin(String kind) { return contents.findByKindOrderByExternalId(kind).stream().map(c -> view(c,true)).toList(); }
    
    public List<Map<String,Object>> preview(String kind,ImportRequest input) {
        kind(kind); var seen=new HashSet<String>(); var result=new ArrayList<Map<String,Object>>(); int line=0;
        for(var row:input.rows()) {
            line++;
            try {
                var n=validate(kind,row,false); String key=n.path("externalId").asText();
                if(!seen.add(key)) throw ApiErrors.bad("Trùng mã trong tệp");
                boolean exists=contents.findByKindAndExternalId(kind,key).isPresent();
                result.add(Map.of("row",line,"valid",true,"existing",exists,"data",n));
            } catch(ResponseStatusException e) { result.add(Map.of("row",line,"valid",false,"message",Objects.requireNonNull(e.getReason()))); }
        }
        return result;
    }
    @Transactional
    public Map<String,Integer> confirm(String kind,ImportRequest input) {
        kind(kind); var seen=new HashSet<String>(); int inserted=0,updated=0,skipped=0;
        for(var row:input.rows()) {
            var n=validate(kind,row,false); String key=n.path("externalId").asText();
            if(!seen.add(key)) throw ApiErrors.bad("Trùng mã trong tệp: "+key);
            var existing=contents.findByKindAndExternalId(kind,key);
            if(existing.isPresent()&&!input.updateExisting()) { skipped++; continue; }
            var c=existing.orElseGet(Content::new);
            // Imported media references are never trusted; retain only assets uploaded on this server.
            n.remove(List.of("imageKey","fileKey","imageMime","fileMime"));
            if(existing.isPresent()) {
                remember(c);
                var old=read(c);
                for(String field:List.of("imageKey","fileKey","imageMime","fileMime")) if(old.has(field)) n.set(field,old.get(field));
                updated++;
            } else inserted++;
            c.kind=kind; c.externalId=key; c.data=write(n); c.published=false; contents.save(c);
        }
        contents.flush(); return Map.of("inserted",inserted,"updated",updated,"skipped",skipped);
    }
    @Transactional
    public Map<String,Object> edit(UUID id,ContentChangeRequest input) {
        var c=contents.findById(id).orElseThrow(ApiErrors::missing);
        if(c.version!=input.version()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Bản ghi vừa thay đổi");
        var n=validate(c.kind,input.data(),false); var old=read(c);
        remember(c);
        n.remove(List.of("imageKey","fileKey","imageMime","fileMime"));
        for(String field:List.of("imageKey","fileKey","imageMime","fileMime")) if(old.has(field)) n.set(field,old.get(field));
        c.externalId=n.path("externalId").asText(); c.data=write(n); c.published=false;
        contents.saveAndFlush(c); return view(c,true);
    }
    @Transactional
    public void batchPublication(BatchPublicationRequest input) {
        var seen=new HashSet<UUID>();
        for(var row:input.rows()) {
            if(!seen.add(row.id())) throw ApiErrors.bad("Trùng ID trong danh sách");
            var c=contents.findById(row.id()).filter(q -> q.kind.equals("questions")).orElseThrow(ApiErrors::missing);
            if(c.version!=row.version()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Câu hỏi vừa thay đổi: "+c.externalId);
            var n=read(c); n.put("reviewed",input.reviewed()); if(input.published()) validate(c.kind,n,true);
            remember(c); c.data=write(n); c.published=input.published(); contents.save(c);
        }
        contents.flush();
    }
    @Transactional
    public Map<String,Object> publish(UUID id,PublicationRequest input) {
        var c=contents.findById(id).orElseThrow(ApiErrors::missing);
        if(c.version!=input.version()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Bản ghi vừa thay đổi");
        if(input.published()) validate(c.kind,read(c),true);
        remember(c);
        c.published=input.published(); contents.saveAndFlush(c); return view(c,true);
    }
}
