package vn.luatgt;

import vn.luatgt.model.*;
import vn.luatgt.repository.*;
import vn.luatgt.service.RateLimit;
import vn.luatgt.integration.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import java.time.Instant;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.*;
import org.springframework.http.*;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest @AutoConfigureMockMvc
class CoreTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired ContentRepository contents;
    @Autowired ExamRepository exams;
    @Autowired ContentHistoryRepository history;
    @Autowired LawRelationRepository relations;
    @Autowired PenaltyRepository penalties;
    @MockitoBean RateLimit rate;
    @MockitoBean KagClient kag;
    @MockitoBean ObjectStorage storage;
    String admin;
    @BeforeEach void admin() throws Exception { admin=token("admin@test.vn","TEST-only-admin-password"); }
    String token(String email,String password) throws Exception {
        return body(mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(Map.of("email",email,"password",password)))).andExpect(status().isOk()).andReturn()).path("accessToken").asText();
    }
    String register() throws Exception {
        return body(mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(Map.of("email",UUID.randomUUID()+"@test.vn","password","TEST-only-user-password","name","Học viên")))).andExpect(status().isOk()).andExpect(jsonPath("$.user.role").value("USER")).andReturn()).path("accessToken").asText();
    }
    JsonNode body(MvcResult result) throws Exception { return json.readTree(result.getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8)); }
    @Test void authCannotEscalateAndLogoutRevokesToken() throws Exception {
        mvc.perform(post("/api/auth/register").contentType(MediaType.APPLICATION_JSON).content("{\"email\":\"attacker@test.vn\",\"name\":\"User\",\"password\":\"TEST-only-user-password\",\"role\":\"ADMIN\"}")).andExpect(status().isBadRequest());
        String user=register();
        mvc.perform(get("/api/admin/users").header("Authorization","Bearer "+user)).andExpect(status().isForbidden());
        mvc.perform(post("/api/auth/logout").header("Authorization","Bearer "+user)).andExpect(status().isOk());
        mvc.perform(get("/api/auth/me").header("Authorization","Bearer "+user)).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/questions")).andExpect(status().isUnauthorized());
    }
    @Test void importsAreAtomicDraftsAndPreserveLegalMetadata() throws Exception {
        String rows="{\"rows\":[{\"sign_id\":\"QCVN 41:2024/BGTVT::DP.127\",\"ma_bien\":\"DP.127\",\"ten\":\"Biển hết tốc độ tối đa\",\"nhom\":\"Biển hết cấm\",\"doc_id\":\"51_2024_TT_BGTVT\",\"mo_ta\":\"Cần kiểm tra nội dung đầy đủ\",\"qcvn\":\"QCVN 41:2024/BGTVT\",\"so_hieu\":\"51/2024/TT-BGTVT\",\"unit_id\":\"D84\",\"ngay_hieu_luc\":\"2025-01-01\",\"ngay_het_hieu_luc\":null}]}";
        mvc.perform(post("/api/admin/imports/signs/confirm").header("Authorization","Bearer "+admin).contentType(MediaType.APPLICATION_JSON).content(rows)).andExpect(status().isOk()).andExpect(jsonPath("$.inserted").value(1));
        var sign=contents.findByKindAndExternalId("signs","QCVN 41:2024/BGTVT::DP.127").orElseThrow();
        assertFalse(sign.published); assertEquals("51_2024_TT_BGTVT",json.readTree(sign.data).path("doc_id").asText());
        mvc.perform(post("/api/admin/content/"+sign.id+"/publication").header("Authorization","Bearer "+admin).contentType(MediaType.APPLICATION_JSON).content("{\"version\":0,\"published\":true}")).andExpect(status().isBadRequest());
        long count=contents.count();
        mvc.perform(post("/api/admin/imports/questions/confirm").header("Authorization","Bearer "+admin).contentType(MediaType.APPLICATION_JSON).content("{\"rows\":[{\"externalId\":\"valid-first\",\"text\":\"Câu hỏi\",\"chapter\":1,\"options\":[\"A\",\"B\"]},{\"externalId\":\"invalid\"}]}")).andExpect(status().isBadRequest());
        assertEquals(count,contents.count());
    }
    @Test void all600PdfDraftsAreAcceptedForPreviewButNotPublished() throws Exception {
        var rows=json.readTree(java.nio.file.Files.readString(java.nio.file.Path.of("../docs/imports/questions-draft.json")));
        assertEquals(600,rows.size());
        var result=body(mvc.perform(post("/api/admin/imports/questions/preview").header("Authorization","Bearer "+admin).contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(Map.of("rows",rows)))).andExpect(status().isOk()).andReturn());
        assertEquals(600,result.size());
        for(var row:result) assertTrue(row.path("valid").asBoolean(),row.toString());
    }
    @Test void zipMatchesCodeAndRejectsTraversal() throws Exception {
        var sign=new Content(); sign.kind="signs"; sign.externalId="ZIP-TEST"; sign.data="{\"externalId\":\"ZIP-TEST\",\"code\":\"DP.127\",\"name\":\"Biển thử\",\"group\":\"Biển hết cấm\"}"; contents.save(sign);
        // Remove another sign with the same code so the archive has an unambiguous match.
        for(var c:contents.findByKindOrderByExternalId("signs")) if(!c.id.equals(sign.id)) contents.delete(c);
        var png=new java.io.ByteArrayOutputStream(); javax.imageio.ImageIO.write(new java.awt.image.BufferedImage(10,10,java.awt.image.BufferedImage.TYPE_INT_RGB),"png",png);
        var archive=new java.io.ByteArrayOutputStream();
        try(var zip=new java.util.zip.ZipOutputStream(archive)) { zip.putNextEntry(new java.util.zip.ZipEntry("DP.127.png")); zip.write(png.toByteArray()); zip.closeEntry(); }
        when(storage.put(any(),eq("image/png"))).thenReturn("test-image-key");
        mvc.perform(multipart("/api/admin/signs/images-zip").file(new org.springframework.mock.web.MockMultipartFile("file","images.zip","application/zip",archive.toByteArray())).header("Authorization","Bearer "+admin)).andExpect(status().isOk()).andExpect(jsonPath("$.matched[0]").value("DP.127"));
        var saved=contents.findById(sign.id).orElseThrow(); assertFalse(saved.published); assertEquals("test-image-key",json.readTree(saved.data).path("imageKey").asText());
        var bad=new java.io.ByteArrayOutputStream();
        try(var zip=new java.util.zip.ZipOutputStream(bad)) { zip.putNextEntry(new java.util.zip.ZipEntry("../DP.127.png")); zip.write(png.toByteArray()); zip.closeEntry(); }
        mvc.perform(multipart("/api/admin/signs/images-zip").file(new org.springframework.mock.web.MockMultipartFile("file","bad.zip","application/zip",bad.toByteArray())).header("Authorization","Bearer "+admin)).andExpect(status().isBadRequest());
    }
    void bank() throws Exception {
        penalties.deleteAllInBatch(); relations.deleteAllInBatch(); history.deleteAllInBatch();
        contents.deleteAllInBatch();
        for(int chapter=1;chapter<=6;chapter++) for(int i=0;i<12;i++) {
            var c=new Content(); c.kind="questions"; c.externalId="C"+chapter+"Q"+i; c.published=true;
            c.data=json.writeValueAsString(Map.of("externalId",c.externalId,"text","Câu hỏi "+i,"chapter",chapter,"options",List.of("Đúng","Sai"),"correctAnswer",0,"critical",i==0,"reviewed",true,"source","test","answerCandidates",List.of(0),"imageKey","snapshot-image")); contents.save(c);
        }
    }
    @Test void examHasQuotasOwnershipSnapshotAndCriticalFailure() throws Exception {
        // No studies refer to these questions in this test database.
        bank(); String user=register(), other=register();
        var publicQuestions=body(mvc.perform(get("/api/questions").header("Authorization","Bearer "+user)).andExpect(status().isOk()).andReturn());
        assertFalse(publicQuestions.toString().contains("answerCandidates")); assertFalse(publicQuestions.toString().contains("correctAnswer"));
        var start=body(mvc.perform(post("/api/exams").header("Authorization","Bearer "+user)).andExpect(status().isOk()).andReturn());
        assertEquals(30,start.path("questions").size()); assertFalse(start.toString().contains("correctAnswer")); assertFalse(start.toString().contains("critical")); assertFalse(start.toString().contains("answerCandidates"));
        UUID id=UUID.fromString(start.path("id").asText()); var stored=exams.findById(id).orElseThrow(); var questions=json.readTree(stored.snapshot);
        assertEquals(1,questions.findValues("critical").stream().filter(JsonNode::asBoolean).count());
        int[] quotas={8,1,1,1,9,9};
        for(int ch=1;ch<=6;ch++) { final int chapter=ch; var stream=new ArrayList<JsonNode>(); questions.forEach(stream::add); assertEquals(quotas[ch-1],stream.stream().filter(q -> q.path("chapter").asInt()==chapter&&!q.path("critical").asBoolean()).count()); }
        mvc.perform(get("/api/exams/"+id).header("Authorization","Bearer "+other)).andExpect(status().isNotFound());
        String mediaPath="/api/exams/"+id+"/questions/"+questions.get(0).path("questionId").asText()+"/media";
        when(storage.get("snapshot-image")).thenReturn(new byte[]{1,2,3});
        mvc.perform(get(mediaPath).header("Authorization","Bearer "+other)).andExpect(status().isNotFound());
        var imageChanged=contents.findById(UUID.fromString(questions.get(0).path("questionId").asText())).orElseThrow();
        var imageData=(ObjectNode)json.readTree(imageChanged.data); imageData.put("imageKey","changed-image"); imageChanged.data=imageData.toString(); contents.save(imageChanged);
        mvc.perform(get(mediaPath).header("Authorization","Bearer "+user)).andExpect(status().isOk()).andExpect(content().bytes(new byte[]{1,2,3}));
        for(var q:questions) mvc.perform(put("/api/exams/"+id+"/answers/"+q.path("questionId").asText()).header("Authorization","Bearer "+user).contentType(MediaType.APPLICATION_JSON).content("{\"selected\":"+(q.path("critical").asBoolean()?1:0)+"}")).andExpect(status().isOk());
        // Alter the current bank; grading must still use the saved snapshot.
        var changed=contents.findAll().getFirst(); var n=(ObjectNode)json.readTree(changed.data); n.put("correctAnswer",1); changed.data=n.toString(); contents.save(changed);
        var result=body(mvc.perform(post("/api/exams/"+id+"/submit").header("Authorization","Bearer "+user)).andExpect(status().isOk()).andReturn());
        assertEquals(29,result.path("score").asInt()); assertTrue(result.path("criticalFailed").asBoolean()); assertFalse(result.path("passed").asBoolean());
        mvc.perform(post("/api/exams/"+id+"/submit").header("Authorization","Bearer "+user)).andExpect(jsonPath("$.score").value(29));
        mvc.perform(put("/api/exams/"+id+"/answers/"+questions.get(0).path("questionId").asText()).header("Authorization","Bearer "+user).contentType(MediaType.APPLICATION_JSON).content("{\"selected\":0}")).andExpect(status().isConflict());
        var passing=body(mvc.perform(post("/api/exams").header("Authorization","Bearer "+user)).andReturn()); UUID passingId=UUID.fromString(passing.path("id").asText());
        int wrong=0;
        for(var q:json.readTree(exams.findById(passingId).orElseThrow().snapshot)) {
            int choice=q.path("correctAnswer").asInt();
            if(!q.path("critical").asBoolean()&&wrong<3) { choice=1-choice; wrong++; }
            mvc.perform(put("/api/exams/"+passingId+"/answers/"+q.path("questionId").asText()).header("Authorization","Bearer "+user).contentType(MediaType.APPLICATION_JSON).content("{\"selected\":"+choice+"}")).andExpect(status().isOk());
        }
        mvc.perform(post("/api/exams/"+passingId+"/submit").header("Authorization","Bearer "+user)).andExpect(jsonPath("$.score").value(27)).andExpect(jsonPath("$.passed").value(true));
        var expiring=body(mvc.perform(post("/api/exams").header("Authorization","Bearer "+user)).andReturn()); UUID expiredId=UUID.fromString(expiring.path("id").asText());
        var expired=exams.findById(expiredId).orElseThrow(); expired.expiresAt=Instant.now().minusSeconds(1); exams.save(expired);
        mvc.perform(put("/api/exams/"+expiredId+"/answers/"+expiring.path("questions").get(0).path("questionId").asText()).header("Authorization","Bearer "+user).contentType(MediaType.APPLICATION_JSON).content("{\"selected\":0}")).andExpect(status().isConflict());
        mvc.perform(get("/api/exams/"+expiredId).header("Authorization","Bearer "+user)).andExpect(jsonPath("$.score").value(0));
    }
    @Test void unavailableKagNeverFabricatesAnAnswer() throws Exception {
        when(kag.query(any())).thenThrow(new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Dịch vụ KAG chưa khả dụng")); String user=register();
        mvc.perform(post("/api/chat").header("Authorization","Bearer "+user).contentType(MediaType.APPLICATION_JSON).content("{\"message\":\"Mức phạt là gì?\"}")).andExpect(status().isServiceUnavailable());
        mvc.perform(get("/api/chat").header("Authorization","Bearer "+user)).andExpect(status().isOk()).andExpect(jsonPath("$[0].state").value("UNAVAILABLE")).andExpect(jsonPath("$[0].answer").value(""));
    }
}
