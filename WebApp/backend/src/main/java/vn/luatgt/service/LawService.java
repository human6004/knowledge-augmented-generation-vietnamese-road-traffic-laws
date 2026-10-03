package vn.luatgt.service;
import vn.luatgt.dto.LawRelationRequest;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.model.*;
import vn.luatgt.repository.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
@Service
public class LawService {
    private final ContentRepository contents; private final LawRelationRepository relations; private final ContentHistoryRepository history;
    public LawService(ContentRepository contents,LawRelationRepository relations,ContentHistoryRepository history) { this.contents=contents; this.relations=relations; this.history=history; }
    public List<Map<String,Object>> relations() { return relations.findAll().stream().map(r -> Map.<String,Object>of("id",r.id,"predecessor",r.predecessor,"successor",r.successor,"type",r.type,"effectiveDate",r.effectiveDate,"note",r.note,"version",r.version)).toList(); }
    public List<Map<String,Object>> history(UUID id) { return history.findByContentIdOrderByChangedAtDesc(id).stream().map(r -> Map.<String,Object>of("version",r.contentVersion,"data",r.data,"published",r.published,"changedAt",r.changedAt)).toList(); }
    @Transactional public void relate(LawRelationRequest request) {
        save(null,request);
    }
    @Transactional public void update(UUID id,LawRelationRequest request) { save(id,request); }
    private void save(UUID relationId,LawRelationRequest request) {
        // ponytail: serialize legal relation updates across document rows; narrow the lock if the document library grows large.
        contents.lockDocuments();
        if(request.predecessor().equals(request.successor())) throw ApiErrors.bad("Không thể liên kết văn bản với chính nó");
        for(UUID id:List.of(request.predecessor(),request.successor())) contents.findById(id).filter(c -> c.kind.equals("documents")).orElseThrow(ApiErrors::missing);
        var all=relations.findAll().stream().filter(r -> !r.id.equals(relationId)).toList(); var pending=new ArrayDeque<UUID>(); var seen=new HashSet<UUID>(); pending.add(request.successor());
        while(!pending.isEmpty()) { var id=pending.removeFirst(); if(id.equals(request.predecessor())) throw ApiErrors.bad("Quan hệ văn bản tạo vòng lặp"); if(!seen.add(id)) continue; all.stream().filter(r -> r.predecessor.equals(id)).forEach(r -> pending.add(r.successor)); }
        var relation=relationId==null?new LawRelation():relations.findById(relationId).orElseThrow(ApiErrors::missing);
        if(relationId!=null&&relation.version!=request.version()) throw new org.springframework.web.server.ResponseStatusException(org.springframework.http.HttpStatus.CONFLICT,"Quan hệ văn bản vừa thay đổi");
        relation.predecessor=request.predecessor(); relation.successor=request.successor(); relation.type=request.type(); relation.effectiveDate=request.effectiveDate(); relation.note=request.note(); relations.save(relation);
    }
}
