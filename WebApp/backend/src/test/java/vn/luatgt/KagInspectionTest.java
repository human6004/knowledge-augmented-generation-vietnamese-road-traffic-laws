package vn.luatgt;

import com.fasterxml.jackson.databind.*;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.integration.KagClient;
import vn.luatgt.service.KagSchema;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(OutputCaptureExtension.class)
class KagInspectionTest {
    @TempDir Path temporary;
    final ObjectMapper json=new ObjectMapper();
    final String query="q".repeat(43),inspect="i".repeat(43),release="synthetic-release";
    KagSchema schema; Path queryFile,inspectFile;
    @BeforeEach void setup() throws Exception {
        schema=new KagSchema(json); queryFile=temporary.resolve("query.key"); inspectFile=temporary.resolve("inspect.key");
        Files.writeString(queryFile,query); Files.writeString(inspectFile,inspect);
    }
    class Fixture implements AutoCloseable {
        final HttpServer server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        final ExecutorService workers=Executors.newCachedThreadPool();
        final AtomicInteger calls=new AtomicInteger(); final Map<String,String> tokens=new ConcurrentHashMap<>();
        volatile int retrieveStatus=200,delay; volatile JsonNode received; volatile String retrieveBody,media="application/json";
        volatile boolean wrongScope,healthLie,releaseAvailable;
        volatile String readyBody;
        volatile String pipelineBody="{\"contract_version\":\"h1-inspect-v1.0\",\"phase\":\"idle\",\"active_requests\":0,\"draining\":false,\"closed\":false,\"progress\":null,\"execution_allowed\":false,\"operational_proof\":\"DENY\",\"production_write\":\"BLOCKED\",\"provider_egress\":\"DENY\"}";
        volatile String benchmarkBody="{\"contract_version\":\"h1-inspect-v1.0\",\"state\":\"NOT_CONFIGURED\",\"datasets\":[],\"execution_allowed\":false,\"execution_blockers\":[\"OPERATIONAL_PROOF_REQUIRED\",\"BENCHMARK_EXECUTION_NOT_AUTHORIZED\"],\"metrics\":null}";
        Fixture() throws Exception {
            retrieveBody=result().toString(); server.setExecutor(workers);
            server.createContext("/v1",e->{
                calls.incrementAndGet(); String path=e.getRequestURI().toString();
                String token=e.getRequestHeaders().getFirst("Authorization"); tokens.put(path,token==null?"":token);
                int status=200; String body;
                if(path.equals("/v1/retrieve")) {
                    received=json.readTree(e.getRequestBody().readAllBytes()); status=retrieveStatus; body=status==200?retrieveBody:failure(code(status));
                    e.getResponseHeaders().set("X-KAG-Release-ID",e.getRequestHeaders().getFirst("X-KAG-Release-ID"));
                    if(delay>0) try { Thread.sleep(delay); } catch(InterruptedException x) { Thread.currentThread().interrupt(); }
                } else if(path.equals("/v1/graph/release")) { status=releaseAvailable?200:503; body=releaseAvailable?releaseView().toString():failure("RELEASE_UNAVAILABLE"); }
                else if(path.equals("/v1/pipeline/status")) body=pipelineBody;
                else if(path.equals("/v1/benchmark/datasets")) body=benchmarkBody;
                else if(path.contains("mode=ready")) {
                    status=wrongScope?403:healthLie||readyBody!=null?200:503;
                    String capability=path.endsWith("retrieve")?"retrieve":"query-v1";
                    body=wrongScope?failure("SCOPE_DENIED"):healthLie?"{\"status\":\"alive\"}":readyBody!=null?readyBody.replace("$cap",capability):readiness(capability);
                } else body="{\"contract_version\":\"h1-read-v1.0\",\"status\":\"alive\"}";
                if(!Set.of("Bearer "+query,"Bearer "+inspect).contains(token)) {status=401;body=failure("AUTH_INVALID");}
                else if((path.contains("capability=retrieve")||path.equals("/v1/retrieve"))&&!token.equals("Bearer "+inspect)||path.contains("capability=query-v1")&&!token.equals("Bearer "+query)) {status=403;body=failure("SCOPE_DENIED");}
                e.getResponseHeaders().set("Content-Type",media);
                byte[] bytes=body.getBytes(java.nio.charset.StandardCharsets.UTF_8);
                try { e.sendResponseHeaders(status,bytes.length); e.getResponseBody().write(bytes); } catch(java.io.IOException closed) {} finally { e.close(); }
            }); server.start();
        }
        String url() {return "http://127.0.0.1:"+server.getAddress().getPort();}
        public void close(){server.stop(0);workers.shutdownNow();}
    }
    String code(int status){return switch(status){case 401->"AUTH_INVALID";case 403->"SCOPE_DENIED";case 422->"INVALID_REQUEST";default->"RELEASE_UNAVAILABLE";};}
    String failure(String code){return "{\"request_id\":\"00000000-0000-4000-8000-000000000001\",\"error\":{\"code\":\""+code+"\",\"message\":\"Dịch vụ chưa sẵn sàng.\",\"retryable\":false},\"native_state\":null}";}
    String readiness(String capability) throws java.io.IOException {
        var value=(com.fasterxml.jackson.databind.node.ObjectNode)json.readTree(failure("NOT_READY"));
        value.put("status","unavailable").put("capability",capability).put("provider_transport","not_probed").put("production_write","blocked");
        value.putObject("checks").put("auth","pass").put("runtime","blocked").put("sources","unknown").put("admission","pass"); return value.toString();
    }
    JsonNode result() {
        var value=json.createObjectNode().put("contract_version","h1-read-v1.1").put("request_id","00000000-0000-4000-8000-000000000001")
            .put("release_id",release).put("source_snapshot_id","synthetic-source"); value.set("schema_contract",json.valueToTree(schema.identity()));
        var item=value.putArray("items").addObject().put("entity_type","VietRoadTraffic.LegalUnit").put("entity_id","test::1").put("doc_id","test").put("unit_id","test::1").putNull("sign_id").put("score",0.5);
        item.putObject("source_texts").put("text","TEST ONLY — nguồn thử, không phải căn cứ pháp luật.");
        item.putArray("vector_sources").addObject().put("property","text").put("score",0.5).put("index","synthetic-index"); item.putArray("graph_context");return value;
    }
    JsonNode releaseView() {
        var v=json.createObjectNode().put("contract_version","h1-read-v1.0").put("release_id",release).put("release_kind","sample").put("source_snapshot_id","synthetic-source")
            .put("source_catalog_sha256","a".repeat(64)).put("release_descriptor_sha256","b".repeat(64)).put("graph_fingerprint","c".repeat(64))
            .put("backend_identity_verified",false).put("source_identity_verified",false).putNull("verified_at").put("query_ready",false).put("production_write","blocked");
        v.set("schema_contract",json.valueToTree(schema.identity()));return v;
    }
    KagClient client(Fixture f,Map<String,Object> override) {
        var props=new HashMap<String,Object>(Map.of("app.kag-url",f.url(),"app.kag-token-file",queryFile.toString(),"app.kag-inspect-token-file",inspectFile.toString(),"app.kag-release-id",release)); props.putAll(override);
        try(var context=new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("test-only",props)); context.registerBean(ObjectMapper.class,()->json);context.registerBean(KagSchema.class,()->schema);
            context.register(KagClient.class);context.refresh();return context.getBean(KagClient.class);
        }
    }
    JsonNode status(KagClient client){return json.valueToTree(client.status());}
    @Test void livenessDoesNotPromoteReadinessAndScopesAreSeparate() throws Exception {
        try(var f=new Fixture()) {
            var s=status(client(f,Map.of()));assertEquals("ALIVE",s.at("/liveness/state").asText());
            assertEquals("NOT_READY",s.at("/queryReadiness/state").asText());assertEquals("NOT_READY",s.at("/retrievalReadiness/state").asText());
            assertEquals("RELEASE_UNAVAILABLE",s.at("/release/state").asText());
            assertEquals("Bearer "+query,f.tokens.get("/v1/health?mode=ready&capability=query-v1"));
            assertEquals("Bearer "+inspect,f.tokens.get("/v1/health?mode=ready&capability=retrieve"));
            assertFalse(s.toString().contains(query));assertFalse(s.toString().contains(inspect));
        }
    }
    @Test void missingTokensMakeNoCallsAndDoNotExposePaths() throws Exception {
        try(var f=new Fixture()) {
            var s=status(client(f,Map.of("app.kag-token-file","","app.kag-inspect-token-file","")));
            for(var check:s)assertEquals("NOT_CONFIGURED",check.path("state").asText());assertEquals(0,f.calls.get());assertFalse(s.toString().contains(temporary.toString()));
        }
    }
    @Test void queryTokenCannotSubstituteForInspect() throws Exception {
        try(var f=new Fixture()) {
            var c=client(f,Map.of("app.kag-inspect-token-file",""));assertEquals("NOT_CONFIGURED",status(c).at("/retrievalReadiness/state").asText());
            var e=assertThrows(ResponseStatusException.class,()->c.retrieve("Nguồn thử",1,false));assertEquals(503,e.getStatusCode().value());assertFalse(f.tokens.containsKey("/v1/retrieve"));
        }
    }
    @Test void identicalScopeSecretsAreRejectedLocally() throws Exception {
        Files.writeString(inspectFile,query);try(var f=new Fixture()){assertEquals("NOT_CONFIGURED",status(client(f,Map.of())).at("/retrievalReadiness/state").asText());}
    }
    @Test void wrongServiceTokenIsReportedWithoutLeakingIt() throws Exception {
        Files.writeString(inspectFile,"x".repeat(43));try(var f=new Fixture()){var s=status(client(f,Map.of()));assertEquals("AUTH_INVALID",s.at("/retrievalReadiness/code").asText());assertEquals(401,s.at("/retrievalReadiness/httpStatus").asInt());assertFalse(s.toString().contains("x".repeat(43)));}
    }
    @ParameterizedTest @ValueSource(strings={"short","newline","oversized","nonascii"}) void invalidInspectSecretsNeverEnterTransport(String fault) throws Exception {
        Files.writeString(inspectFile,switch(fault){case "short"->"short";case "newline"->inspect+"\n\n";case "oversized"->"x".repeat(515);default->"ệ".repeat(43);});
        try(var f=new Fixture()){assertEquals("NOT_CONFIGURED",status(client(f,Map.of())).at("/retrievalReadiness/state").asText());assertFalse(f.tokens.containsKey("/v1/health?mode=ready&capability=retrieve"));}
    }
    @Test void retrievalDoesNotInventMissingReleaseOrNeedQueryPublicationSnapshot() throws Exception {
        try(var f=new Fixture()){var c=client(f,Map.of("app.kag-release-id",""));assertThrows(ResponseStatusException.class,()->c.retrieve("Nguồn thử",1,false));assertFalse(f.tokens.containsKey("/v1/retrieve"));
            assertEquals(result(),client(f,Map.of("app.kag-token-file","","app.kag-webapp-snapshot-id","")).retrieve("Nguồn thử",1,false));}
    }
    @Test void artifactReleaseIsNotVerifiedGraphReadiness() throws Exception {
        try(var f=new Fixture()){f.releaseAvailable=true;var s=status(client(f,Map.of()));assertEquals("NOT_READY",s.at("/release/state").asText());assertEquals(releaseView(),s.at("/release/evidence"));}
    }
    @Test void health200WithoutCapabilityProofNeverMeansReady() throws Exception {
        try(var f=new Fixture()){f.healthLie=true;var s=status(client(f,Map.of()));assertNotEquals("READY",s.at("/queryReadiness/state").asText());assertNotEquals("READY",s.at("/retrievalReadiness/state").asText());assertEquals(200,s.at("/queryReadiness/httpStatus").asInt());assertEquals("INVALID_RESPONSE",s.at("/queryReadiness/code").asText());}
    }
    @Test void onlyStrictSampleCapabilityProofMeansReady() throws Exception {
        var valid=json.valueToTree(Map.of("status","ready","capability","$cap","release_kind","SAMPLE","release_id",release,
            "checks",Map.of("auth","pass","runtime","pass","sources","pass","admission","pass"),
            "provider_transport","metadata_verified","production_write","blocked"));
        try(var f=new Fixture()) {
            f.readyBody=valid.toString();var c=client(f,Map.of());
            assertEquals("READY",status(c).at("/queryReadiness/state").asText());
            assertEquals("READY",status(c).at("/retrievalReadiness/state").asText());
            for(String fault:List.of("release_kind","release_id","provider_transport","production_write","checks")) {
                var invalid=valid.deepCopy();((com.fasterxml.jackson.databind.node.ObjectNode)invalid).put(fault,"wrong");
                f.readyBody=invalid.toString();assertNotEquals("READY",status(c).at("/queryReadiness/state").asText());
            }
        }
    }
    @Test void sampleInspectionTimeoutIsBoundedAndSupportsVerifiedReads() throws Exception {
        try(var f=new Fixture()) {
            var c=client(f,Map.of());
            assertThrows(IllegalArgumentException.class,()->c.inspectionTimeout(1));
            assertThrows(IllegalArgumentException.class,()->c.inspectionTimeout(26));
            c.inspectionTimeout(25);f.delay=2500;assertEquals(result(),c.retrieve("Nguồn thử",1,false));
        }
    }
    @Test void upstreamScopeDenialIsNotWebappSessionFailure() throws Exception {
        try(var f=new Fixture()){f.wrongScope=true;var s=status(client(f,Map.of()));assertEquals("SCOPE_DENIED",s.at("/retrievalReadiness/code").asText());assertEquals(403,s.at("/retrievalReadiness/httpStatus").asInt());}
    }
    @Test void retrievalPreservesAllEvidenceAndAddsOnlyNativeContract() throws Exception {
        try(var f=new Fixture()){assertEquals(result(),client(f,Map.of()).retrieve("Nguồn thử 🚦",3,true));assertEquals("Bearer "+inspect,f.tokens.get("/v1/retrieve"));
            assertEquals(json.valueToTree(Map.of("message","Nguồn thử 🚦","top_k",3,"expand",true,"schema_contract",schema.identity())),f.received);}
    }
    @ParameterizedTest @ValueSource(ints={401,403,422,503}) void retrievalErrorsAreSafe(int code) throws Exception {
        try(var f=new Fixture()){f.retrieveStatus=code;var e=assertThrows(ResponseStatusException.class,()->client(f,Map.of()).retrieve("Nguồn thử",1,false));
            assertEquals(code==422?422:503,e.getStatusCode().value());assertNull(e.getCause());assertFalse(e.toString().contains(inspect));assertFalse(e.toString().contains(temporary.toString()));}
    }
    @ParameterizedTest @ValueSource(strings={"token","query-token","schema","release","items","answer","duplicate-json"}) void rejectsInvalidOrReflectedRetrieval(String fault) throws Exception {
        try(var f=new Fixture()) {var b=(com.fasterxml.jackson.databind.node.ObjectNode)result();switch(fault){
            case "token"->b.put("source_snapshot_id",inspect);case "query-token"->b.put("source_snapshot_id",query);case "schema"->b.putObject("schema_contract");case "release"->b.put("release_id","wrong");
            case "items"->b.putArray("items").addObject();case "answer"->b.put("answer","fake");default->{} }
            f.retrieveBody=fault.equals("duplicate-json")?"{\"items\":[],\"items\":[]}":b.toString();assertThrows(ResponseStatusException.class,()->client(f,Map.of()).retrieve("Nguồn thử",1,false));}
    }
    @Test void connectionRefusedAndTimeoutStayUnavailable() throws Exception {
        try(var f=new Fixture()){var c=client(f,Map.of());f.server.stop(0);assertEquals("UNAVAILABLE",status(c).at("/liveness/state").asText());}
        try(var f=new Fixture()){f.delay=3500;assertThrows(ResponseStatusException.class,()->client(f,Map.of()).retrieve("Nguồn thử",1,false));}
    }
    @Test void serviceErrorsDoNotExposeSecretsInOutput(CapturedOutput output) throws Exception {
        try(var f=new Fixture()){f.retrieveStatus=503;assertThrows(ResponseStatusException.class,()->client(f,Map.of()).retrieve("Nguồn thử",1,false));status(client(f,Map.of()));
            assertFalse(output.getAll().contains(query));assertFalse(output.getAll().contains(inspect));assertFalse(output.getAll().contains(temporary.toString()));}
    }
    @Test void runtimeInspectionUsesInspectTokenAndNeverCreatesProgress() throws Exception {
        try(var f=new Fixture()){var c=client(f,Map.of());var p=c.pipelineStatus();assertEquals("idle",p.path("phase").asText());assertTrue(p.path("progress").isNull());assertFalse(p.path("execution_allowed").asBoolean());
            assertEquals("NOT_CONFIGURED",c.benchmarkDatasets().path("state").asText());assertEquals("Bearer "+inspect,f.tokens.get("/v1/pipeline/status"));assertEquals("Bearer "+inspect,f.tokens.get("/v1/benchmark/datasets"));}
    }
    @Test void inspectionRejectsFakeProgressExecutionAndReflectedSecrets() throws Exception {
        try(var f=new Fixture()){var c=client(f,Map.of());for(String field:List.of("progress","execution_allowed","phase")){var v=(com.fasterxml.jackson.databind.node.ObjectNode)json.readTree(f.pipelineBody);if(field.equals("progress"))v.put(field,100);else if(field.equals("execution_allowed"))v.put(field,true);else v.put(field,inspect);String saved=f.pipelineBody;f.pipelineBody=v.toString();assertThrows(ResponseStatusException.class,c::pipelineStatus);f.pipelineBody=saved;}
            f.benchmarkBody=f.benchmarkBody.replace("\"metrics\":null","\"metrics\":{\"accuracy\":1}");assertThrows(ResponseStatusException.class,c::benchmarkDatasets);}
    }
    @Test void runtimeInspectionCannotFallBackToQueryToken() throws Exception {
        try(var f=new Fixture()){var c=client(f,Map.of("app.kag-inspect-token-file",""));assertThrows(ResponseStatusException.class,c::pipelineStatus);assertThrows(ResponseStatusException.class,c::benchmarkDatasets);assertEquals(0,f.calls.get());}
    }
    @ParameterizedTest @ValueSource(strings={"application/*","text/html","application/json;charset=iso-8859-1"}) void rejectsNoncanonicalMedia(String media) throws Exception {
        try(var f=new Fixture()){f.media=media;var c=client(f,Map.of());assertThrows(ResponseStatusException.class,()->c.retrieve("Nguồn thử",1,false));assertEquals("INVALID_RESPONSE",status(c).at("/liveness/code").asText());}
    }
    @ParameterizedTest @ValueSource(strings={"identity","score","vector","source-text","graph","oversized","unknown-error"}) void rejectsMalformedEvidence(String fault) throws Exception {
        try(var f=new Fixture()){var b=(com.fasterxml.jackson.databind.node.ObjectNode)result();var item=(com.fasterxml.jackson.databind.node.ObjectNode)b.path("items").get(0);
            switch(fault){case "identity"->item.put("entity_id","wrong");case "score"->item.put("score",2);case "vector"->((com.fasterxml.jackson.databind.node.ObjectNode)item.path("vector_sources").get(0)).put("index","");
                case "source-text"->item.putObject("source_texts").put("text",7);case "graph"->item.putArray("graph_context").addObject().put("predicate","unrelated");default->{} }
            f.retrieveBody=fault.equals("oversized")?" ".repeat(245761):fault.equals("unknown-error")?failure("internal-path-unsafe"):b.toString();if(fault.equals("unknown-error"))f.retrieveStatus=503;
            assertThrows(ResponseStatusException.class,()->client(f,Map.of()).retrieve("Nguồn thử",1,false));}
    }
}
