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
        volatile String sampleBody;
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
                else if(path.equals("/v1/operations/sample")) body=sampleBody==null?sampleView().toString():sampleBody;
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
    com.fasterxml.jackson.databind.node.ObjectNode sampleView() {
        var v=json.createObjectNode().put("contract_version","h1-sample-inspection-1.0").put("release_id",release).put("release_kind","SAMPLE")
            .put("source_snapshot_id","synthetic-source").put("source_catalog_sha256","a".repeat(64)).put("graph_fingerprint","c".repeat(64))
            .put("verified_at","2026-10-11T00:00:00+00:00").put("execution_allowed",false).put("production_write","BLOCKED");
        v.set("schema_contract",json.valueToTree(schema.identity()));
        v.putObject("backend").put("database","vietroadtraffic").put("namespace","VietRoadTraffic").put("database_id","fixture-db").put("server_id","fixture-server").put("read_only",true).put("verified",true);
        v.putObject("counts").put("nodes",1).put("edges",0).put("vectors",1);
        var n=v.putArray("nodes").addObject().put("entity_type","VietRoadTraffic.LegalDocument").put("entity_id","test-doc");
        n.putObject("properties").put("id","test-doc").put("name","test-doc").put("title","TEST ONLY").put("so_hieu","fixture");
        n.putArray("sources").addObject().put("evidence_id","d".repeat(64)).put("field","title").put("source_sha256","e".repeat(64));
        v.putArray("edges");v.putObject("sample_receipt").put("stage","GRAPH_VERIFIED").put("sealed_at","2026-10-11T00:00:00Z").put("receipt_sha256","f".repeat(64)).putNull("build_run_id").putNull("progress");
        v.putObject("providers").put("state","NOT_CONFIGURED").putNull("attempts").putNull("receipt_window").putNull("configured_chat_model").putNull("configured_embedding_model")
            .putNull("policy_response_version").put("exact_backend_identity_verified",false).putNull("upstream_attempts").putNull("proxy_retries");
        v.putObject("datasets").put("contract_version","h1-inspect-v1.0").put("state","NOT_CONFIGURED").putArray("datasets");
        var d=(com.fasterxml.jackson.databind.node.ObjectNode)v.path("datasets");d.put("execution_allowed",false).putNull("metrics");d.putArray("execution_blockers").add("OPERATIONAL_PROOF_REQUIRED").add("BENCHMARK_EXECUTION_NOT_AUTHORIZED");
        return v;
    }
    @Test void verifiedSampleInspectionUsesInspectScopeAndPreservesActualGraph() throws Exception {
        try(var f=new Fixture()) {
            var value=client(f,Map.of()).sampleInspection();
            assertEquals("test-doc",value.at("/nodes/0/entity_id").asText());assertEquals(1,value.at("/counts/nodes").asInt());
            assertTrue(value.at("/backend/read_only").asBoolean());assertFalse(value.path("execution_allowed").asBoolean());
            assertEquals("Bearer "+inspect,f.tokens.get("/v1/operations/sample"));
        }
    }
    @ParameterizedTest @ValueSource(strings={"graph","write","counts","property","identity","secret","model"})
    void sampleInspectionRejectsUnverifiedOrSensitivePayload(String change) throws Exception {
        try(var f=new Fixture()) {
            var body=sampleView();
            switch(change) {
                case "graph" -> ((com.fasterxml.jackson.databind.node.ObjectNode)body.path("backend")).put("verified",false);
                case "write" -> body.put("execution_allowed",true);
                case "counts" -> ((com.fasterxml.jackson.databind.node.ObjectNode)body.path("counts")).put("nodes",32);
                case "property" -> ((com.fasterxml.jackson.databind.node.ObjectNode)body.at("/nodes/0/properties")).put("password","PRIVATE");
                case "identity" -> body.put("release_id","foreign");
                case "secret" -> ((com.fasterxml.jackson.databind.node.ObjectNode)body.at("/nodes/0/properties")).put("title",query);
                case "model" -> ((com.fasterxml.jackson.databind.node.ObjectNode)body.path("providers")).put("exact_backend_identity_verified",true);
            }
            f.sampleBody=body.toString();var error=assertThrows(ResponseStatusException.class,()->client(f,Map.of()).sampleInspection());
            assertEquals(503,error.getStatusCode().value());assertFalse(error.toString().contains("PRIVATE"));
        }
    }
    KagClient client(Fixture f,Map<String,Object> override) {
        var props=new HashMap<String,Object>(Map.of("app.kag-url",f.url(),"app.kag-token-file",queryFile.toString(),"app.kag-inspect-token-file",inspectFile.toString(),"app.kag-release-id",release)); props.putAll(override);
        try(var context=new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("test-only",props)); context.registerBean(ObjectMapper.class,()->json);context.registerBean(KagSchema.class,()->schema);
            context.register(KagClient.class);context.refresh();return context.getBean(KagClient.class);
        }
    }
    @Test void provisionalSmokeDoesNotAuthorizeOfficialBenchmarkOrHumanReview() throws Exception {
        try(var f=new Fixture()) {
            var body=sampleView();((com.fasterxml.jackson.databind.node.ObjectNode)body.path("datasets")).put("state","AVAILABLE");
            var row=((com.fasterxml.jackson.databind.node.ArrayNode)body.at("/datasets/datasets")).addObject();
            row.put("id","sample/eval_questions.jsonl").put("dataset_status","PROVISIONAL").put("dataset_eligibility","BLOCKED").put("reason","PROVISIONAL_DATASET")
                .put("dataset_hash","a".repeat(64)).put("record_count",1).put("official_benchmark",false).put("eligible_count",0).put("ineligible_count",1).put("invalid_count",0).put("gold_count",1).put("eligibility_scope","G1_RETRIEVAL_GOLD_COVERAGE");
            var missing=row.putObject("missing_gold");for(String kind:List.of("document","unit","sign"))missing.putArray(kind);
            var smoke=row.putObject("smoke").put("state","NOT_RUN").put("review_status","PROVISIONAL").put("g1_eligible_count",1).put("graph_fingerprint",body.path("graph_fingerprint").asText()).put("official_benchmark",false);
            smoke.putObject("runs").putNull("G1").putNull("G2");f.sampleBody=body.toString();
            assertEquals(1,client(f,Map.of()).sampleInspection().at("/datasets/datasets/0/smoke/g1_eligible_count").asInt());
            var metadata=row.putObject("metadata").put("dataset_version","fixture-v2").putNull("generation_method");
            metadata.putObject("category_counts").put("definition",1);f.sampleBody=body.toString();
            assertEquals("fixture-v2",client(f,Map.of()).sampleInspection().at("/datasets/datasets/0/metadata/dataset_version").asText());
            ((com.fasterxml.jackson.databind.node.ObjectNode)metadata.path("category_counts")).put("definition",2);f.sampleBody=body.toString();
            assertThrows(ResponseStatusException.class,()->client(f,Map.of()).sampleInspection());
            ((com.fasterxml.jackson.databind.node.ObjectNode)metadata.path("category_counts")).put("definition",1);
            smoke.put("review_status","HUMAN_REVIEWED");f.sampleBody=body.toString();assertThrows(ResponseStatusException.class,()->client(f,Map.of()).sampleInspection());
            smoke.put("review_status","PROVISIONAL").put("graph_fingerprint","0".repeat(64));f.sampleBody=body.toString();assertThrows(ResponseStatusException.class,()->client(f,Map.of()).sampleInspection());
            row.put("dataset_status","FROZEN").put("dataset_eligibility","ELIGIBLE").putNull("reason").put("record_count",5).put("eligible_count",5).put("ineligible_count",0).put("gold_count",5);
            ((com.fasterxml.jackson.databind.node.ObjectNode)metadata.path("category_counts")).put("definition",5);
            smoke.put("review_status","FROZEN").put("state","AVAILABLE").put("g1_eligible_count",5).put("graph_fingerprint",body.path("graph_fingerprint").asText());
            var run=((com.fasterxml.jackson.databind.node.ObjectNode)smoke.path("runs")).putObject("G1").put("status","COMPLETE").put("started_at","2026-10-12T00:00:00Z").put("finished_at","2026-10-12T00:01:00Z")
                .put("requested_count",5).put("attempted_count",5).put("failed_count",0).put("ineligible_count",0);
            run.putObject("metrics");var latency=run.putObject("latency_ms");
            for(String scope:List.of("successful","all_attempted"))latency.putObject(scope).put("count",5).put("min",1).put("mean",1).put("median",1).put("p95",1).put("max",1);
            var config=run.putObject("configuration").put("protocol_version","1.0").put("eval_version","1.0").put("metric_policy_version","1.1").put("top_k",1).put("expand",false).put("rank_semantics","channel_projected_returned_top_k").putNull("identity_catalog_hash").put("release_id",release);
            config.putArray("ks").add(1);config.putObject("judge_config").put("name","synthetic-judge").put("version","v1").put("model","fixture-model").put("prompt_version","p1").put("temperature",0).putNull("seed").put("calibrated",false);
            f.sampleBody=body.toString();assertEquals(5,client(f,Map.of()).sampleInspection().at("/datasets/datasets/0/smoke/runs/G1/requested_count").asInt());
            smoke.put("review_status","PROVISIONAL");f.sampleBody=body.toString();assertThrows(ResponseStatusException.class,()->client(f,Map.of()).sampleInspection());
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
