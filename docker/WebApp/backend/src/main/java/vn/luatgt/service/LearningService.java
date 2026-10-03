package vn.luatgt.service;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.security.SecureRandom;
import java.time.*;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.dto.AnswerRequest;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.model.Exam;
import vn.luatgt.model.StudyAttempt;
import vn.luatgt.repository.ContentRepository;
import vn.luatgt.repository.ExamRepository;
import vn.luatgt.repository.StudyAttemptRepository;
import vn.luatgt.integration.ObjectStorage;

@Service
public class LearningService {
    private final ContentRepository contents; private final ExamRepository exams; private final StudyAttemptRepository studies; private final ContentService data; private final RateLimit rate;
    private final SecureRandom random=new SecureRandom();
    private final ObjectStorage storage;
    public LearningService(ContentRepository contents,ExamRepository exams,StudyAttemptRepository studies,ContentService data,RateLimit rate,ObjectStorage storage) {
        this.contents=contents; this.exams=exams; this.studies=studies; this.data=data; this.rate=rate;
        this.storage=storage;
    }
    public MediaService.Download examMedia(UUID id,UUID questionId,JwtAuthenticationToken auth) {
        var e=exams.findById(id).filter(exam -> exam.ownerId.equals(AuthService.user(auth))).orElseThrow(ApiErrors::missing);
        for(var q:snapshot(e)) if(q.path("questionId").asText().equals(questionId.toString())&&q.hasNonNull("imageKey"))
            return new MediaService.Download(storage.get(q.path("imageKey").asText()),q.path("imageMime").asText("image/png"));
        throw ApiErrors.missing();
    }
    ArrayNode snapshot(Exam e) { try { return (ArrayNode)data.mapper().readTree(e.snapshot); } catch(Exception ex) { throw new IllegalStateException(ex); } }
    public ObjectNode answers(Exam e) { try { return (ObjectNode)data.mapper().readTree(e.answers); } catch(Exception ex) { throw new IllegalStateException(ex); } }
    @Transactional
    public Map<String,Object> study(UUID questionId,AnswerRequest choice,JwtAuthenticationToken auth) {
        rate.check("study:"+auth.getName(),120,60);
        var c=contents.findById(questionId).filter(q -> q.kind.equals("questions")&&q.published).orElseThrow(ApiErrors::missing);
        var q=data.read(c); if(choice.selected()>=q.path("options").size()) throw ApiErrors.bad("Đáp án không tồn tại");
        var attempt=new StudyAttempt(); attempt.ownerId=AuthService.user(auth); attempt.questionId=questionId;
        attempt.chapter=q.path("chapter").asInt(); attempt.correct=choice.selected()==q.path("correctAnswer").asInt(); studies.save(attempt);
        return Map.of("correct",attempt.correct,"correctAnswer",q.path("correctAnswer"),"explanation",q.path("explanation").asText(""),"critical",q.path("critical").asBoolean());
    }
    
    public List<Map<String,Object>> progress(JwtAuthenticationToken auth) {
        var attempts=studies.findByOwnerId(AuthService.user(auth)); var result=new ArrayList<Map<String,Object>>();
        for(int chapter=1;chapter<=6;chapter++) {
            final int ch=chapter; var selected=attempts.stream().filter(a -> a.chapter==ch).toList();
            result.add(Map.of("chapter",ch,"attempts",selected.size(),"correct",selected.stream().filter(a -> a.correct).count(),"practiced",selected.stream().map(a -> a.questionId).distinct().count()));
        }
        return result;
    }
    @Transactional
    public Map<String,Object> start(JwtAuthenticationToken auth) {
        rate.check("exam:"+auth.getName(),10,3600);
        var bank=new ArrayList<ObjectNode>();
        for(var c:contents.findByKindAndPublishedTrueOrderByExternalId("questions")) {
            var q=data.read(c); q.put("questionId",c.id.toString()); bank.add(q);
        }
        Collections.shuffle(bank,random); var selected=new ArrayList<ObjectNode>();
        selected.add(bank.stream().filter(q -> q.path("critical").asBoolean()).findFirst().orElseThrow(() -> ApiErrors.bad("Chưa có câu điểm liệt đã kiểm duyệt")));
        int[] quotas={8,1,1,1,9,9};
        for(int chapter=1;chapter<=6;chapter++) {
            final int ch=chapter;
            var pool=bank.stream().filter(q -> q.path("chapter").asInt()==ch&&!q.path("critical").asBoolean()).limit(quotas[ch-1]).toList();
            if(pool.size()!=quotas[ch-1]) throw ApiErrors.bad("Ngân hàng đã xuất bản chưa đủ câu chương "+ch);
            selected.addAll(pool);
        }
        Collections.shuffle(selected,random);
        var e=new Exam(); e.ownerId=AuthService.user(auth); e.startedAt=Instant.now(); e.expiresAt=e.startedAt.plusSeconds(1200);
        e.snapshot=data.write(data.mapper().valueToTree(selected)); exams.save(e); return examView(e);
    }
    private Exam owned(UUID id,JwtAuthenticationToken auth) { return exams.owned(id,AuthService.user(auth)).orElseThrow(ApiErrors::missing); }
    private void finish(Exam e) {
        if(e.submittedAt!=null) return;
        var answered=answers(e); int score=0; boolean critical=false;
        for(var q:snapshot(e)) {
            var selected=answered.get(q.path("questionId").asText());
            boolean correct=selected!=null&&selected.asInt()==q.path("correctAnswer").asInt();
            if(correct) score++; else if(q.path("critical").asBoolean()) critical=true;
        }
        e.score=score; e.criticalFailed=critical; e.passed=score>=27&&!critical;
        e.submittedAt=Instant.now(); exams.save(e);
    }
    private Map<String,Object> examView(Exam e) {
        var qs=snapshot(e);
        if(e.submittedAt==null) for(var q:qs) ((ObjectNode)q).retain(List.of("questionId","externalId","text","chapter","options","imageKey","imageMime"));
        var result=new LinkedHashMap<String,Object>(); result.put("id",e.id); result.put("license","B"); result.put("ruleset","B-2025-06");
        result.put("startedAt",e.startedAt); result.put("expiresAt",e.expiresAt); result.put("serverTime",Instant.now());
        result.put("questions",qs); result.put("answers",answers(e)); result.put("submittedAt",e.submittedAt);
        if(e.submittedAt!=null) { result.put("score",e.score); result.put("criticalFailed",e.criticalFailed); result.put("passed",e.passed); }
        return result;
    }
    @Transactional
    public Map<String,Object> exam(UUID id,JwtAuthenticationToken auth) {
        var e=owned(id,auth); if(!Instant.now().isBefore(e.expiresAt)) finish(e); return examView(e);
    }
    @Transactional
    public Map<String,Object> answer(UUID id,UUID questionId,AnswerRequest choice,JwtAuthenticationToken auth) {
        var e=owned(id,auth);
        if(e.submittedAt!=null||!Instant.now().isBefore(e.expiresAt)) throw new ResponseStatusException(HttpStatus.CONFLICT,"Bài thi đã nộp hoặc hết giờ");
        var q=new ArrayList<JsonNode>(); snapshot(e).forEach(q::add);
        var question=q.stream().filter(n -> n.path("questionId").asText().equals(questionId.toString())).findFirst().orElseThrow(ApiErrors::missing);
        if(choice.selected()>=question.path("options").size()) throw ApiErrors.bad("Đáp án không tồn tại");
        var a=answers(e); a.put(questionId.toString(),choice.selected()); e.answers=data.write(a); exams.save(e); return examView(e);
    }
    @Transactional
    public Map<String,Object> submit(UUID id,JwtAuthenticationToken auth) { var e=owned(id,auth); finish(e); return examView(e); }
    
    public List<Map<String,Object>> history(JwtAuthenticationToken auth) {
        return exams.findTop20ByOwnerIdOrderByStartedAtDesc(AuthService.user(auth)).stream().map(e -> {
            var result=new LinkedHashMap<String,Object>(); result.put("id",e.id); result.put("startedAt",e.startedAt);
            result.put("submittedAt",e.submittedAt); result.put("score",e.score); result.put("passed",e.passed); return (Map<String,Object>)result;
        }).toList();
    }
}
