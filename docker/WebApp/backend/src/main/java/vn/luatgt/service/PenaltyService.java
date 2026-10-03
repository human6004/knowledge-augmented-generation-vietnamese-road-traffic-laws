package vn.luatgt.service;
import vn.luatgt.dto.PenaltyRequest;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.model.PenaltyRule;
import vn.luatgt.repository.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
@Service
public class PenaltyService {
    private final PenaltyRepository penalties; private final ContentRepository contents; private final ContentService data;
    public PenaltyService(PenaltyRepository penalties,ContentRepository contents,ContentService data) { this.penalties=penalties; this.contents=contents; this.data=data; }
    private Map<String,Object> view(PenaltyRule rule) { try { return Map.of("id",rule.id,"documentId",rule.documentId,"data",data.mapper().readTree(rule.data),"version",rule.version,"published",rule.published); } catch(Exception e) { throw new IllegalStateException(e); } }
    public List<Map<String,Object>> list(boolean admin) { return penalties.findAll().stream().filter(p -> admin||p.published&&contents.findById(p.documentId).map(d -> d.published&&data.isEffective(d)).orElse(false)).map(this::view).toList(); }
    @Transactional public Map<String,Object> save(UUID id,PenaltyRequest request) {
        var doc=contents.findById(request.documentId()).filter(c -> c.kind.equals("documents")).orElseThrow(ApiErrors::missing);
        if(!request.data().isObject()) throw ApiErrors.bad("Cần object dữ liệu mức phạt");
        var n=((ObjectNode)request.data()).deepCopy(); ContentService.text(n,"behavior",3000,true); ContentService.text(n,"vehicle",100,true); ContentService.text(n,"unit_id",500,true); ContentService.text(n,"additional",3000,false);
        for(String key:List.of("minFine","maxFine","points")) if(!n.path(key).isIntegralNumber()||!n.path(key).canConvertToLong()||n.path(key).asLong()<0||n.path(key).asLong()>2_000_000_000L) throw ApiErrors.bad("Mức phạt/điểm phải là số không âm");
        if(n.path("minFine").asLong()>n.path("maxFine").asLong()||n.path("points").asInt()>12) throw ApiErrors.bad("Khoảng phạt hoặc điểm không hợp lệ");
        if(request.published()&&(!n.path("reviewed").isBoolean()||!n.path("reviewed").asBoolean()||!doc.published||!data.isEffective(doc))) throw ApiErrors.bad("Cần kiểm duyệt và văn bản đang có hiệu lực");
        var rule=id==null?new PenaltyRule():penalties.findById(id).orElseThrow(ApiErrors::missing);
        if(id!=null&&rule.version!=request.version()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Mức phạt vừa thay đổi");
        rule.documentId=doc.id; rule.data=data.write(n); rule.published=request.published(); return view(penalties.saveAndFlush(rule));
    }
}
