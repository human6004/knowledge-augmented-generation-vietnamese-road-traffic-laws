package vn.luatgt.integration;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.core.JsonParser;
import io.github.resilience4j.circuitbreaker.*;
import java.io.*;
import java.net.http.HttpClient;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.function.BiConsumer;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.service.KagSchema;

@Component
public class KagClient {
    private final RestClient client,inspectionClient; private final ObjectMapper json;
    private final JdkClientHttpRequestFactory queryFactory,inspectionFactory;
    private final KagSchema schema;
    private final String tokenFile,inspectTokenFile,release,snapshot;
    private final Clock clock;
    private RestClient builderClient;
    @Value("${app.kag-builder-token-file:}") private String builderTokenFile="";
    private static final ZoneId LEGAL_ZONE=ZoneId.of("Asia/Saigon");
    private static final Set<String> REQUEST_FIELDS=Set.of("user_id","message","context_id","schema_contract");
    private static final Set<String> CITATION_FIELDS=Set.of("doc_id","unit_id","sign_id","evidence_id","field","start","end","quote");
    private final CircuitBreaker breaker=CircuitBreaker.of("kag",CircuitBreakerConfig.custom().minimumNumberOfCalls(3).slidingWindowSize(6).waitDurationInOpenState(Duration.ofSeconds(30)).build());
    public KagClient(@Value("${app.kag-url}") String url,ObjectMapper json,KagSchema schema,
        @Value("${app.kag-token-file:}") String tokenFile,@Value("${app.kag-release-id:}") String release,
        @Value("${app.kag-webapp-snapshot-id:}") String snapshot,ObjectProvider<Clock> clocks,
        @Value("${app.kag-inspect-token-file:}") String inspectTokenFile) {
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        factory.setReadTimeout(Duration.ofSeconds(30));
        this.queryFactory=factory;
        this.client=RestClient.builder().baseUrl(url).requestFactory(factory).build(); this.json=json;
        this.schema=schema; this.tokenFile=tokenFile; this.release=release; this.snapshot=snapshot;
        this.clock=clocks.getIfAvailable(Clock::systemDefaultZone);
        this.inspectTokenFile=inspectTokenFile;
        var inspectionFactory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        inspectionFactory.setReadTimeout(Duration.ofSeconds(2));
        this.inspectionFactory=inspectionFactory;
        this.inspectionClient=RestClient.builder().baseUrl(url).requestFactory(inspectionFactory).build();
    }
    @Value("${app.kag-query-timeout-seconds:30}")
    public void queryTimeout(int seconds) {
        if(seconds<30||seconds>180) throw new IllegalArgumentException("Bounded KAG query timeout required");
        queryFactory.setReadTimeout(Duration.ofSeconds(seconds));
    }
    @Value("${app.kag-inspection-timeout-seconds:2}")
    public void inspectionTimeout(int seconds) {
        if(seconds<2||seconds>25) throw new IllegalArgumentException("Bounded KAG inspection timeout required");
        inspectionFactory.setReadTimeout(Duration.ofSeconds(seconds));
    }
    @Value("${app.kag-builder-url:}")
    public void builderEndpoint(String url) {
        if(url.isBlank()) {builderClient=null;return;}
        var uri=java.net.URI.create(url);
        if(!Set.of("http","https").contains(uri.getScheme())||uri.getHost()==null||uri.getUserInfo()!=null||uri.getQuery()!=null||uri.getFragment()!=null||!Set.of("","/").contains(uri.getPath()))
            throw new IllegalArgumentException("Private Builder endpoint required");
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        factory.setReadTimeout(Duration.ofSeconds(3));
        builderClient=RestClient.builder().baseUrl(url).requestFactory(factory).build();
    }
    public JsonNode builderStatus() {return builderRequest(null,null);}
    public JsonNode builderInputs() {return builderRequest("inputs",null);}
    public JsonNode builderAction(String action,String runId) {
        if(!Set.of("build","stop","resume").contains(action)||runId==null||!runId.matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Thao tác Builder không hợp lệ");
        return builderRequest(action,runId);
    }
    private JsonNode builderRequest(String action,String runId) {
        try {
            if(builderClient==null||builderTokenFile.isBlank()||!Path.of(builderTokenFile).isAbsolute())throw new IOException();
            String token=readToken(builderTokenFile);
            for(String file:List.of(tokenFile,inspectTokenFile)) {
                String other=null;try{other=readToken(file);}catch(IOException ignored){}
                if(token.equals(other))throw new IOException();
            }
            boolean read=action==null||action.equals("inputs");
            RestClient.RequestHeadersSpec<?> request=read?builderClient.get().uri("/v1/builder/"+(action==null?"status":"inputs")):
                builderClient.post().uri("/v1/builder/"+action).contentType(MediaType.APPLICATION_JSON).body(Map.of("run_id",runId));
            return request.header(HttpHeaders.AUTHORIZATION,"Bearer "+token).accept(MediaType.APPLICATION_JSON).exchange((req,res)->{
                int code=res.getStatusCode().value();
                if(code==409)throw new ResponseStatusException(HttpStatus.CONFLICT,"Builder đang bận hoặc thao tác chưa an toàn; hãy tải lại trạng thái");
                if(code==422)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"Yêu cầu Builder không hợp lệ");
                if(code!=(read?200:202))throw new IOException();
                var body=inspectionBody(res,token);
                if("inputs".equals(action))validateBuilderInputs(body);else validateBuilder(body);
                if(!read&&!body.path("run_id").asText().equals(runId))throw new IOException();
                return body;
            });
        } catch(ResponseStatusException e) {throw e;}
        catch(Exception e) {throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Builder chưa khả dụng; kiểm tra cấu hình Worker và quyền điều khiển");}
    }
    private void validateBuilderInputs(JsonNode body) throws IOException {
        String configuration=body.path("configuration").asText();
        if(!fields(body).equals(Set.of("contract_version","configuration","error_code","scope","target","inputs","preflight"))||
            !body.path("contract_version").asText().equals("builder-inputs-v1")||!Set.of("NOT_CONFIGURED","INVALID","CONFIGURED").contains(configuration)||
            !body.path("preflight").asText().equals("NOT_RUN"))throw new IOException();
        boolean configured=configuration.equals("CONFIGURED");
        if(configuration.equals("INVALID")?!body.path("error_code").asText().equals("CONFIG"):!body.path("error_code").isNull())throw new IOException();
        var target=body.path("target");
        if(configured) {
            if(!body.path("scope").asText().equals("FRESH_SAMPLE")||!fields(target).equals(Set.of("project_id","database","namespace"))||
                !bounded(target.path("project_id"),1,Integer.MAX_VALUE)||!target.path("database").asText().matches("(?:neo4j|vietroadtraffic|freshsample[a-z0-9]{8,40})")||
                !target.path("namespace").asText().equals("VietRoadTraffic"))throw new IOException();
        } else if(!target.isNull()||!body.path("scope").isNull())throw new IOException();
        var inputs=body.path("inputs");var names=new HashSet<String>();
        var expected=Set.of("c3_manifest","sample_manifest","vector_artifact","provenance","chunk_manifest","source_checkpoint");
        if(!inputs.isArray()||inputs.size()!=(configured?expected.size():0))throw new IOException();
        for(var input:inputs) {
            String name=input.path("name").asText();
            if(!fields(input).equals(Set.of("name","sha256","state"))||!expected.contains(name)||!names.add(name)||
                !input.path("sha256").asText().matches("[0-9a-f]{64}")||!Set.of("MATCHED","MISSING","INVALID","UNAVAILABLE").contains(input.path("state").asText()))throw new IOException();
        }
    }
    private void validateBuilder(JsonNode body) throws IOException {
        String state=body.path("state").asText();var actions=body.path("actions");
        if(!fields(body).equals(Set.of("contract_version","state","run_id","target","progress","error_code","actions","delete_reason","production_write"))||
            !body.path("contract_version").asText().equals("builder-control-v1")||!Set.of("IDLE","RUNNING","STOPPING","STOPPED","COMPLETE","BLOCKED").contains(state)||
            !fields(actions).equals(Set.of("build","stop","resume","delete"))||!body.path("delete_reason").asText().equals("DELETE_NOT_AUTHORIZED")||!body.path("production_write").asText().equals("BLOCKED"))throw new IOException();
        for(String name:List.of("build","stop","resume","delete")) {
            boolean allowed=switch(name){case "build"->Set.of("IDLE","COMPLETE").contains(state);case "stop"->state.equals("RUNNING");case "resume"->state.equals("STOPPED");default->false;};
            if(!actions.path(name).isBoolean()||actions.path(name).asBoolean()!=allowed)throw new IOException();
        }
        var runId=body.path("run_id");
        if(runId.isNull()? !Set.of("IDLE","BLOCKED").contains(state): !runId.isTextual()||!runId.asText().matches("[A-Za-z0-9][A-Za-z0-9._-]{0,127}"))throw new IOException();
        var target=body.path("target");
        if(target.isNull()? !state.equals("BLOCKED"): !fields(target).equals(Set.of("project_id","database","namespace"))||!bounded(target.path("project_id"),1,Integer.MAX_VALUE)||
            !target.path("database").asText().matches("(?:vietroadtraffic|freshsample[a-z0-9]{8,40})")||!target.path("namespace").asText().equals("VietRoadTraffic"))throw new IOException();
        var progress=body.path("progress");
        if(!progress.isNull()&&(!fields(progress).equals(Set.of("stage","done","total"))||!Set.of("preflight","plan","vectorize","export-artifact","write-nodes","verify-nodes","write-edges","verify","release").contains(progress.path("stage").asText())||
            !bounded(progress.path("total"),0,Integer.MAX_VALUE)||!bounded(progress.path("done"),0,progress.path("total").asInt())))throw new IOException();
        var error=body.path("error_code");if(!error.isNull()&&(!error.isTextual()||!error.asText().matches("[A-Z_]{1,32}")))throw new IOException();
    }
    public Map<String,Object> status() {
        return Map.of("liveness",probe("/v1/health","either"),
            "queryReadiness",probe("/v1/health?mode=ready&capability=query-v1","query"),
            "retrievalReadiness",probe("/v1/health?mode=ready&capability=retrieve","inspect"),
            "vectorRetrievalReadiness",probe("/v1/health?mode=ready&capability=retrieve-vector","inspect"),
            "release",probe("/v1/graph/release","either"));
    }
    public JsonNode pipelineStatus() { return inspectView("/v1/pipeline/status",true); }
    public JsonNode benchmarkDatasets() { return inspectView("/v1/benchmark/datasets",false); }
    public JsonNode sampleInspection() {
        try {
            headerIdentity(release);String token=inspectionToken();
            return inspectionClient.get().uri("/v1/operations/sample").header(HttpHeaders.AUTHORIZATION,"Bearer "+token)
                .header("X-KAG-Release-ID",release).accept(MediaType.APPLICATION_JSON).exchange((req,res)->{
                    if(res.getStatusCode().value()!=200) throw new IOException("Sample inspection unavailable");
                    var body=inspectionBody(res,token);validateSample(body);return body;
                });
        } catch(Exception e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Inspection SAMPLE chưa đủ bằng chứng hoặc chưa khả dụng"); }
    }
    private void validateSample(JsonNode body) throws IOException {
        if(!fields(body).equals(Set.of("contract_version","release_id","release_kind","source_snapshot_id","source_catalog_sha256","schema_contract","graph_fingerprint","backend","counts","nodes","edges","verified_at","execution_allowed","production_write","sample_receipt","datasets","providers"))||
            !body.path("contract_version").asText().equals("h1-sample-inspection-1.0")||!body.path("release_id").asText().equals(release)||
            !body.path("release_kind").asText().equals("SAMPLE")||!body.path("schema_contract").equals(json.valueToTree(schema.identity()))||
            !text(body.path("source_snapshot_id"),512,true)||!body.path("execution_allowed").equals(json.valueToTree(false))||!body.path("production_write").asText().equals("BLOCKED")) throw new IOException("Invalid sample authority");
        for(String field:List.of("source_catalog_sha256","graph_fingerprint")) if(!body.path(field).asText().matches("[0-9a-f]{64}")) throw new IOException("Invalid sample hash");
        try {java.time.OffsetDateTime.parse(body.path("verified_at").asText());} catch(Exception e){throw new IOException("Invalid verification time");}
        var backend=body.path("backend");
        if(!fields(backend).equals(Set.of("database","namespace","database_id","server_id","read_only","verified"))||!backend.path("database").asText().equals("vietroadtraffic")||
            !backend.path("namespace").asText().equals("VietRoadTraffic")||!text(backend.path("database_id"),512,true)||!text(backend.path("server_id"),512,true)||
            !backend.path("read_only").equals(json.valueToTree(true))||!backend.path("verified").equals(json.valueToTree(true))) throw new IOException("Unverified backend");
        var counts=body.path("counts");var nodes=body.path("nodes");var edges=body.path("edges");
        if(!fields(counts).equals(Set.of("nodes","edges","vectors"))||!bounded(counts.path("nodes"),1,32)||!bounded(counts.path("edges"),0,22)||!bounded(counts.path("vectors"),1,42)||
            !nodes.isArray()||nodes.size()!=counts.path("nodes").asInt()||!edges.isArray()||edges.size()!=counts.path("edges").asInt()) throw new IOException("Invalid graph limits");
        var seen=new HashSet<String>();var sources=new HashSet<String>();
        for(var node:nodes) {
            String kind=node.path("entity_type").asText(),id=node.path("entity_id").asText();
            if(!fields(node).equals(Set.of("entity_type","entity_id","properties","sources"))||!Set.of("VietRoadTraffic.LegalDocument","VietRoadTraffic.LegalUnit","VietRoadTraffic.TrafficSign").contains(kind)||
                !text(node.path("entity_id"),512,true)||!seen.add(json.valueToTree(List.of(kind,id)).toString())||!node.path("properties").isObject()||!node.path("sources").isArray()||node.path("sources").isEmpty()||node.path("sources").size()>2) throw new IOException("Invalid graph node");
            var props=node.path("properties");var approved=new HashMap<String,String>();
            for(var row:schema.contract().path("node_properties").path(kind.substring(kind.lastIndexOf('.')+1))) approved.put(row.path("logical_name").asText(),row.path("contract_type").asText());
            if(!approved.keySet().containsAll(fields(props))||!props.path("id").asText().equals(id)||!props.path("name").asText().equals(id)) throw new IOException("Invalid node properties");
            for(var property:fields(props)) {
                var value=props.path(property);String type=approved.get(property);
                if(value.isNull())continue;
                if((type.equals("INTEGER")||type.equals("OPTIONAL_INTEGER"))?!value.isIntegralNumber():type.equals("JSON_TEXT")?false:!text(value,131072,false)) throw new IOException("Invalid property type");
            }
            for(var source:node.path("sources")) if(!fields(source).equals(Set.of("evidence_id","field","source_sha256"))||!source.path("evidence_id").asText().matches("[0-9a-f]{64}")||
                !source.path("source_sha256").asText().matches("[0-9a-f]{64}")||!approved.containsKey(source.path("field").asText())||!props.has(source.path("field").asText())||!sources.add(source.path("evidence_id").asText())) throw new IOException("Invalid provenance");
        }
        var seenEdges=new HashSet<String>();
        for(var edge:edges) {
            var rule=schema.contract().path("relations").path(edge.path("predicate").asText());
            if(!fields(edge).equals(Set.of("from","predicate","to","properties"))||rule.isMissingNode()||!edge.path("properties").isObject()||!seenEdges.add(edge.toString())) throw new IOException("Invalid edge");
            for(String side:List.of("from","to")) {
                var endpoint=edge.path(side);
                if(!endpoint.isArray()||endpoint.size()!=2||!seen.contains(endpoint.toString())||!endpoint.path(0).asText().equals("VietRoadTraffic."+rule.path(side+"_type").asText())) throw new IOException("Invalid edge endpoint");
            }
            var approved=new HashSet<String>();for(var row:schema.contract().path("relation_properties").path(edge.path("predicate").asText()))approved.add(row.path("logical_name").asText());
            if(!approved.containsAll(fields(edge.path("properties"))))throw new IOException("Invalid relation properties");
        }
        var receipt=body.path("sample_receipt");
        if(!fields(receipt).equals(Set.of("stage","sealed_at","receipt_sha256","build_run_id","progress"))||!receipt.path("stage").asText().equals("GRAPH_VERIFIED")||
            !receipt.path("receipt_sha256").asText().matches("[0-9a-f]{64}")||!receipt.path("build_run_id").isNull()||!receipt.path("progress").isNull()) throw new IOException("Invalid sample receipt");
        try{java.time.Instant.parse(receipt.path("sealed_at").asText());}catch(Exception e){throw new IOException("Invalid seal time");}
        validateDatasets(body.path("datasets"),true);validateProviders(body.path("providers"));
        for(var row:body.at("/datasets/datasets")) if(row.has("smoke")&&!row.at("/smoke/graph_fingerprint").equals(body.path("graph_fingerprint"))) throw new IOException("Smoke graph mismatch");
    }
    private static boolean bounded(JsonNode value,int min,int max) {return value.isIntegralNumber()&&value.canConvertToInt()&&value.asInt()>=min&&value.asInt()<=max;}
    private void validateProviders(JsonNode body) throws IOException {
        if(!fields(body).equals(Set.of("state","attempts","receipt_window","configured_chat_model","configured_embedding_model","policy_response_version","exact_backend_identity_verified","upstream_attempts","proxy_retries"))||
            !body.path("exact_backend_identity_verified").equals(json.valueToTree(false))||!body.path("upstream_attempts").isNull()||!body.path("proxy_retries").isNull()||
            !Set.of("NOT_CONFIGURED","OBSERVED").contains(body.path("state").asText()))throw new IOException("Invalid provider claims");
        if(body.path("state").asText().equals("NOT_CONFIGURED")) {
            if(!body.path("attempts").isNull()||!body.path("receipt_window").isNull())throw new IOException("Unobserved provider counts");return;
        }
        if(!body.path("configured_chat_model").asText().equals("gemini-3.8-flash-high")||!body.path("configured_embedding_model").asText().equals("dg/text-embedding-3-large")||
            (!body.path("policy_response_version").isNull()&&!body.path("policy_response_version").asText().equals("gemini-3.8-flash-n")))throw new IOException("Invalid model route");
        var counts=body.path("attempts");if(!fields(counts).equals(Set.of("embedding","chat")))throw new IOException("Invalid request counts");
        for(var count:counts)if(!count.isIntegralNumber()||!count.canConvertToLong()||count.asLong()<0)throw new IOException("Invalid request count");
        var window=body.path("receipt_window");
        if(!fields(window).equals(Set.of("since","outcomes","recent"))||!window.path("recent").isArray()||window.path("recent").size()>50||!fields(window.path("outcomes")).equals(Set.of("embedding","chat")))throw new IOException("Invalid receipt window");
        try{java.time.OffsetDateTime.parse(window.path("since").asText());}catch(Exception e){throw new IOException("Invalid receipt time");}
        for(var outcome:window.path("outcomes")) {
            if(!fields(outcome).equals(Set.of("http_success","http_error","transport_error","cancelled")))throw new IOException("Invalid outcome counts");
            for(var count:outcome)if(!count.isIntegralNumber()||!count.canConvertToLong()||count.asLong()<0)throw new IOException("Invalid outcome count");
        }
        for(var row:window.path("recent")) {
            if(!fields(row).equals(Set.of("kind","attempt","outbound_id","request_id","source_component","configured_model","timestamp","outcome","status","provider_request_id","latency_ms","client_retry","proxy_retries","upstream_attempts"))||
                !Set.of("embedding","chat").contains(row.path("kind").asText())||!row.path("attempt").isIntegralNumber()||row.path("attempt").asLong()<1||
                !row.path("outbound_id").asText().matches("[0-9a-f]{32}")||!Set.of("kag.query","kag.retrieve","direct_runner").contains(row.path("source_component").asText())||
                !Set.of("attempted","http_success","http_error","transport_error","cancelled").contains(row.path("outcome").asText())||
                !row.path("client_retry").equals(json.valueToTree(false))||!row.path("proxy_retries").isNull()||!row.path("upstream_attempts").isNull()||
                !row.path("configured_model").asText().equals(body.path(row.path("kind").asText().equals("chat")?"configured_chat_model":"configured_embedding_model").asText()))throw new IOException("Invalid provider receipt");
            for(String id:List.of("request_id","provider_request_id"))if(!row.path(id).isNull()&&!row.path(id).asText().matches("[A-Za-z0-9_.:-]{1,128}"))throw new IOException("Invalid request identity");
            if(!row.path("status").isNull()&&!bounded(row.path("status"),100,599)||!row.path("latency_ms").isNull()&&(!row.path("latency_ms").isNumber()||!Double.isFinite(row.path("latency_ms").asDouble())||row.path("latency_ms").asDouble()<0))throw new IOException("Invalid receipt measurement");
            try{java.time.OffsetDateTime.parse(row.path("timestamp").asText());}catch(Exception e){throw new IOException("Invalid receipt timestamp");}
        }
    }
    private JsonNode inspectView(String path,boolean pipeline) {
        try {
            String token=inspectionToken();
            return inspectionClient.get().uri(path).header(HttpHeaders.AUTHORIZATION,"Bearer "+token).accept(MediaType.APPLICATION_JSON).exchange((req,res)->{
                if(res.getStatusCode().value()!=200) throw new IOException("Inspection unavailable");
                var body=inspectionBody(res,token);
                if(!body.path("contract_version").asText().equals("h1-inspect-v1.0")||!body.path("execution_allowed").isBoolean()||body.path("execution_allowed").asBoolean()) throw new IOException("Invalid inspection authority");
                if(pipeline) validatePipeline(body); else validateDatasets(body);
                return body;
            });
        } catch(Exception e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Inspection KAG chưa khả dụng hoặc chưa được cấu hình"); }
    }
    private void validatePipeline(JsonNode body) throws IOException {
        if(!fields(body).equals(Set.of("contract_version","phase","active_requests","draining","closed","progress","execution_allowed","operational_proof","production_write","provider_egress"))||
            !body.path("progress").isNull()||!body.path("operational_proof").asText().equals("DENY")||!body.path("production_write").asText().equals("BLOCKED")||!body.path("provider_egress").asText().equals("DENY")) throw new IOException("Invalid pipeline proof");
        String phase=body.path("phase").asText();var active=body.path("active_requests");
        if(phase.equals("unavailable")) {
            if(!active.isNull()||!body.path("closed").isNull()||!body.path("draining").isNull()) throw new IOException("Invalid unavailable runtime");
            return;
        }
        if(!active.isIntegralNumber()||!active.canConvertToInt()||active.asInt()<0||active.asInt()>1||!body.path("closed").isBoolean()||!body.path("draining").isBoolean()) throw new IOException("Invalid runtime state");
        String observed=body.path("closed").asBoolean()?"closed":body.path("draining").asBoolean()?"draining":active.asInt()==1?"running":"idle";
        if(!phase.equals(observed)) throw new IOException("Inconsistent runtime state");
    }
    private void validateDatasets(JsonNode body) throws IOException { validateDatasets(body,false); }
    private void validateDatasets(JsonNode body,boolean sample) throws IOException {
        if(!fields(body).equals(Set.of("contract_version","state","datasets","execution_allowed","execution_blockers","metrics"))||!body.path("metrics").isNull()||
            !body.path("execution_blockers").equals(json.valueToTree(List.of("OPERATIONAL_PROOF_REQUIRED","BENCHMARK_EXECUTION_NOT_AUTHORIZED")))||
            !Set.of("AVAILABLE","NOT_CONFIGURED","UNAVAILABLE","LIMIT_EXCEEDED").contains(body.path("state").asText())||!body.path("datasets").isArray()||body.path("datasets").size()>20||
            (!body.path("state").asText().equals("AVAILABLE")&&!body.path("datasets").isEmpty())) throw new IOException("Invalid dataset catalog");
        var seen=new HashSet<String>();
        for(var row:body.path("datasets")) {
            String id=row.path("id").asText(),status=row.path("dataset_status").asText(),eligibility=row.path("dataset_eligibility").asText();
            var expected=new HashSet<String>(Set.of("id","dataset_status","dataset_eligibility","reason","dataset_hash","record_count","official_benchmark"));
            if(sample)expected.addAll(Set.of("eligible_count","ineligible_count","invalid_count","gold_count","missing_gold","eligibility_scope"));
            if(sample&&row.has("smoke"))expected.add("smoke");
            if(sample&&row.has("metadata"))expected.add("metadata");
            if(!fields(row).equals(expected)||!id.matches("[A-Za-z0-9_.-]{1,128}(?:/eval_questions\\.jsonl)?")||
                id.startsWith("../")||!seen.add(id)||!row.path("official_benchmark").isBoolean()||!Set.of("ELIGIBLE","BLOCKED").contains(eligibility)) throw new IOException("Invalid dataset identity");
            if(!row.path("dataset_status").isNull()&&!Set.of("PROVISIONAL","FROZEN").contains(status)) throw new IOException("Invalid dataset status");
            if(!row.path("dataset_hash").isNull()&&!row.path("dataset_hash").asText().matches("[0-9a-f]{64}")) throw new IOException("Invalid dataset hash");
            if(!row.path("record_count").isNull()&&(!row.path("record_count").isIntegralNumber()||!row.path("record_count").canConvertToLong()||row.path("record_count").asLong()<(sample?0:1))) throw new IOException("Invalid dataset count");
            if(eligibility.equals("ELIGIBLE")) {
                if(!status.equals("FROZEN")||row.path("dataset_hash").isNull()||row.path("record_count").isNull()||!row.path("reason").isNull()) throw new IOException("Unverified dataset eligibility");
            } else if(!Set.of("PROVISIONAL_DATASET","NO_GOLD","INVALID_DATASET","DATASET_TOO_LARGE").contains(row.path("reason").asText())&&!(sample&&row.path("reason").asText().equals("NO_ELIGIBLE_QUESTIONS"))) throw new IOException("Invalid blocked dataset");
            if(row.path("official_benchmark").asBoolean()&&!status.equals("FROZEN")) throw new IOException("Unverified official dataset");
            if(sample) {
                if(row.has("metadata")) {
                    var meta=row.path("metadata");
                    if(!fields(meta).equals(Set.of("dataset_version","category_counts","generation_method"))||!meta.path("category_counts").isObject()||
                        (!meta.path("dataset_version").isNull()&&!text(meta.path("dataset_version"),512,true))||
                        (!meta.path("generation_method").isNull()&&!meta.path("generation_method").asText().equals("legacy-b2-evidence-first-adapted")))throw new IOException("Invalid dataset metadata");
                    long totalCategories=0;
                    var categories=meta.path("category_counts").fields();
                    while(categories.hasNext()) {var entry=categories.next();if(!Set.of("definition","obligation","sanction_numeric","effectiveness_metadata","inter_document","multi_hop","unanswerable","traffic_sign").contains(entry.getKey())||!bounded(entry.getValue(),1,1000000))throw new IOException("Invalid question category");totalCategories+=entry.getValue().asLong();}
                    if(!row.path("record_count").isNull()&&(totalCategories!=row.path("record_count").asLong()-row.path("invalid_count").asLong()||
                        (meta.path("dataset_version").isNull()!=(totalCategories==0))))throw new IOException("Inconsistent category counts");
                }
                if(row.has("smoke"))validateSmoke(row.path("smoke"),row.path("record_count"),row);
                if(!row.path("eligibility_scope").asText().equals("G1_RETRIEVAL_GOLD_COVERAGE")||!bounded(row.path("eligible_count"),0,1000000)||!bounded(row.path("ineligible_count"),0,1000000)||
                    !fields(row.path("missing_gold")).equals(Set.of("document","unit","sign")))throw new IOException("Invalid sample coverage");
                for(var ids:row.path("missing_gold")) {if(!ids.isArray()||ids.size()>10000)throw new IOException("Invalid missing gold");for(var idValue:ids)if(!text(idValue,512,true))throw new IOException("Invalid gold identity");}
                if(!row.path("record_count").isNull()&&(!bounded(row.path("invalid_count"),0,1000000)||!bounded(row.path("gold_count"),0,row.path("record_count").asInt())||
                    row.path("eligible_count").asLong()+row.path("ineligible_count").asLong()+row.path("invalid_count").asLong()!=row.path("record_count").asLong()))throw new IOException("Inconsistent coverage counts");
            }
        }
    }
    private void validateSmoke(JsonNode smoke,JsonNode total,JsonNode dataset) throws IOException {
        if(!fields(smoke).equals(Set.of("state","review_status","g1_eligible_count","graph_fingerprint","official_benchmark","runs"))||
            !Set.of("NOT_RUN","AVAILABLE","INVALID_RECEIPT").contains(smoke.path("state").asText())||
            !Set.of("PROVISIONAL","FROZEN","NOT_ATTESTED").contains(smoke.path("review_status").asText())||
            (!smoke.path("review_status").asText().equals("NOT_ATTESTED")&&!smoke.path("review_status").equals(dataset.path("dataset_status")))||
            !bounded(smoke.path("g1_eligible_count"),0,total.isIntegralNumber()?total.asInt():0)||
            !smoke.path("graph_fingerprint").asText().matches("[0-9a-f]{64}")||!smoke.path("official_benchmark").isBoolean()||!smoke.path("official_benchmark").equals(dataset.path("official_benchmark"))||
            !fields(smoke.path("runs")).equals(Set.of("G1","G2")))throw new IOException("Invalid smoke proof");
        boolean available=smoke.path("state").asText().equals("AVAILABLE"),hasRun=false;
        for(var run:smoke.path("runs")) {
            if(run.isNull())continue;hasRun=true;
            var runFields=new HashSet<String>(Set.of("status","started_at","finished_at","requested_count","attempted_count","failed_count","ineligible_count","metrics","latency_ms"));
            if(run.has("configuration"))runFields.add("configuration");
            if(!available||!Set.of("PROVISIONAL","FROZEN").contains(smoke.path("review_status").asText())||!fields(run).equals(runFields)||
                !run.path("status").asText().equals("COMPLETE")||!bounded(run.path("requested_count"),1,1000000)||!run.path("requested_count").equals(total)||
                !bounded(run.path("attempted_count"),0,total.asInt())||!bounded(run.path("failed_count"),0,run.path("attempted_count").asInt())||
                !bounded(run.path("ineligible_count"),0,total.asInt())||run.path("attempted_count").asInt()+run.path("ineligible_count").asInt()!=total.asInt()||
                !run.path("metrics").isObject()||run.path("metrics").size()>128||!fields(run.path("latency_ms")).equals(Set.of("successful","all_attempted")))throw new IOException("Invalid smoke run");
            if(run.has("configuration")) {
                var config=run.path("configuration");
                if(!fields(config).equals(Set.of("protocol_version","eval_version","metric_policy_version","ks","top_k","expand","rank_semantics","identity_catalog_hash","release_id","judge_config"))||
                    !config.path("protocol_version").asText().equals("1.0")||!config.path("eval_version").asText().equals("1.0")||!Set.of("1.0","1.1").contains(config.path("metric_policy_version").asText())||
                    !bounded(config.path("top_k"),1,10)||!config.path("ks").isArray()||config.path("ks").isEmpty()||config.path("ks").size()>10||
                    !config.path("expand").equals(json.valueToTree(false))||!config.path("rank_semantics").asText().equals("channel_projected_returned_top_k")||
                    (!config.path("identity_catalog_hash").isNull()&&!config.path("identity_catalog_hash").asText().matches("[0-9a-f]{64}"))||
                    (!config.path("release_id").isNull()&&!config.path("release_id").asText().equals(release)))throw new IOException("Invalid benchmark configuration");
                int previous=0;for(var k:config.path("ks")){if(!bounded(k,1,config.path("top_k").asInt())||k.asInt()<=previous)throw new IOException("Invalid benchmark cutoffs");previous=k.asInt();}
                var judge=config.path("judge_config");
                if(!judge.isNull()) {
                    if(!fields(judge).equals(Set.of("name","version","model","prompt_version","temperature","seed","calibrated"))||!text(judge.path("name"),512,true)||
                        !judge.path("version").isTextual()||!judge.path("model").isTextual()||!judge.path("prompt_version").isTextual()||!judge.path("temperature").isNumber()||!Double.isFinite(judge.path("temperature").asDouble())||
                        !judge.path("calibrated").isBoolean()||!judge.path("seed").isNull()&&(!judge.path("seed").isIntegralNumber()||!judge.path("seed").canConvertToLong()))throw new IOException("Invalid judge configuration");
                }
            }
            try {if(java.time.Instant.parse(run.path("finished_at").asText()).isBefore(java.time.Instant.parse(run.path("started_at").asText())))throw new IOException("Invalid smoke timestamps");}
            catch(java.time.format.DateTimeParseException invalid){throw new IOException("Invalid smoke timestamps");}
            for(var metric:run.path("metrics")) {
                if(!fields(metric).equals(Set.of("value","scored_count","status_counts","eligible_count","excluded_count","failed_count"))||
                    !fields(metric.path("status_counts")).equals(Set.of("OK","NOT_APPLICABLE","UNAVAILABLE","UNKNOWN"))||
                    (!metric.path("value").isNull()&&(!metric.path("value").isNumber()||!Double.isFinite(metric.path("value").asDouble())||metric.path("value").asDouble()<0)))throw new IOException("Invalid smoke metric");
                for(String k:List.of("scored_count","eligible_count","excluded_count","failed_count"))if(!bounded(metric.path(k),0,total.asInt()))throw new IOException("Invalid smoke metric count");
                int statusCount=0;for(var count:metric.path("status_counts")){if(!bounded(count,0,total.asInt()))throw new IOException("Invalid metric status");statusCount+=count.asInt();}
                if(statusCount!=total.asInt()||metric.path("eligible_count").asInt()+metric.path("excluded_count").asInt()!=total.asInt()||
                    metric.path("scored_count").asInt()!=metric.at("/status_counts/OK").asInt()||(metric.path("value").isNull()!=(metric.path("scored_count").asInt()==0)))throw new IOException("Inconsistent smoke metrics");
            }
            for(var latency:run.path("latency_ms")) {
                if(!fields(latency).equals(Set.of("count","min","mean","median","p95","max"))||!bounded(latency.path("count"),0,total.asInt()))throw new IOException("Invalid smoke latency");
                for(String k:List.of("min","mean","median","p95","max"))if(latency.path("count").asInt()==0?!latency.path(k).isNull():!latency.path(k).isNumber()||!Double.isFinite(latency.path(k).asDouble())||latency.path(k).asDouble()<0)throw new IOException("Invalid smoke latency");
            }
        }
        if(available!=hasRun)throw new IOException("Missing smoke execution");
    }
    private String inspectionToken() throws IOException {
        if(inspectTokenFile.isBlank()||!Path.of(inspectTokenFile).isAbsolute()) throw new IOException("Inspection credentials unavailable");
        String token=readToken(inspectTokenFile);
        if(!tokenFile.isBlank()) {
            String query=null; try { query=readToken(tokenFile); } catch(IOException ignored) {}
            if(token.equals(query)) throw new IOException("Distinct scopes required");
        }
        return token;
    }
    private Map<String,Object> probe(String path,String scope) {
        String token;
        try {
            if(scope.equals("inspect")) token=inspectionToken();
            else if(scope.equals("query")) token=readToken(tokenFile);
            else { try { token=readToken(tokenFile); } catch(IOException unavailable) { token=inspectionToken(); } }
        } catch(Exception e) { return Map.of("state","NOT_CONFIGURED","code","NOT_CONFIGURED","httpStatus",0); }
        final String sentToken=token;
        int[] observed={0};
        try {
            return inspectionClient.get().uri(path).header(HttpHeaders.AUTHORIZATION,"Bearer "+sentToken).header("X-KAG-Release-ID",release).accept(MediaType.APPLICATION_JSON).exchange((req,res)->{
                int code=res.getStatusCode().value(); observed[0]=code; var body=inspectionBody(res,sentToken);
                if(code!=200) {
                    String error=errorCode(body);
                    if(code==503&&error.equals("NOT_READY")&&path.contains("mode=ready")) {
                        String capability=path.endsWith("retrieve-vector")?"retrieve-vector":scope.equals("inspect")?"retrieve":"query-v1";
                        if(!body.path("capability").asText().equals(capability)||!body.path("status").asText().equals("unavailable")||!body.path("checks").isObject()||
                            !fields(body.path("checks")).containsAll(Set.of("auth","runtime","sources"))||!Set.of("auth","runtime","sources","admission").containsAll(fields(body.path("checks")))||
                            !body.path("production_write").asText().equals("blocked")||!body.path("provider_transport").asText().equals("not_probed")) throw new IOException("Invalid readiness");
                        for(var check:body.path("checks")) if(!check.isTextual()||!Set.of("pass","blocked","unknown").contains(check.asText())) throw new IOException("Invalid readiness check");
                        return Map.<String,Object>of("state","NOT_READY","httpStatus",code,"code",error,"evidence",Map.of("capability",capability,"checks",body.path("checks"),"provider_transport","not_probed","production_write","blocked"));
                    }
                    return Map.<String,Object>of("state",code==503&&error.equals("RELEASE_UNAVAILABLE")?"RELEASE_UNAVAILABLE":code==401||code==403?"NOT_CONFIGURED":"UNAVAILABLE","httpStatus",code,"code",error);
                }
                if(path.equals("/v1/health")) {
                    if(!fields(body).equals(Set.of("contract_version","status"))||!body.path("contract_version").asText().equals("h1-read-v1.0")||!body.path("status").asText().equals("alive")) throw new IOException("Invalid liveness");
                    return Map.<String,Object>of("state","ALIVE","httpStatus",200);
                }
                if(path.equals("/v1/graph/release")) {
                    validateRelease(body);
                    // H1 release_view verifies artifacts only; it cannot certify live graph readiness.
                    return Map.<String,Object>of("state","NOT_READY","httpStatus",200,"code","ARTIFACTS_ONLY","evidence",body);
                }
                String capability=path.endsWith("retrieve-vector")?"retrieve-vector":scope.equals("inspect")?"retrieve":"query-v1";
                if(capability.equals("retrieve-vector")) {
                    if(!fields(body).equals(Set.of("status","capability","release_kind","release_id","provider_transport","production_write"))||
                        !body.path("status").asText().equals("ready")||!body.path("capability").asText().equals(capability)||
                        !body.path("release_kind").asText().equals("SAMPLE")||!body.path("release_id").asText().equals(release)||
                        !body.path("provider_transport").asText().equals("not_probed")||!body.path("production_write").asText().equals("blocked"))throw new IOException("Invalid vector readiness");
                    return Map.<String,Object>of("state","READY","httpStatus",200,"evidence",body);
                }
                if(!fields(body).equals(Set.of("status","capability","release_kind","release_id","checks","provider_transport","production_write"))||
                    !body.path("status").asText().equals("ready")||!body.path("capability").asText().equals(capability)||
                    !body.path("release_kind").asText().equals("SAMPLE")||!body.path("release_id").asText().equals(release)||release.isBlank()||
                    !body.path("provider_transport").asText().equals("metadata_verified")||!body.path("production_write").asText().equals("blocked")||
                    !fields(body.path("checks")).equals(Set.of("auth","runtime","sources","admission"))) throw new IOException("Invalid sample readiness");
                for(var check:body.path("checks")) if(!check.isTextual()||!check.asText().equals("pass")) throw new IOException("Invalid readiness check");
                return Map.<String,Object>of("state","READY","httpStatus",200,"evidence",body);
            });
        } catch(Exception e) { return Map.of("state","UNAVAILABLE","httpStatus",observed[0],"code",observed[0]==0?"UNAVAILABLE":"INVALID_RESPONSE"); }
    }
    public JsonNode retrieve(String message,int topK,boolean expand) {
        try {
            if(!text(json.valueToTree(message),4000,true)||topK<1||topK>10) throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,"Yêu cầu truy xuất không hợp lệ");
            headerIdentity(release); String token=inspectionToken();
            byte[] request=json.writeValueAsBytes(Map.of("message",message,"top_k",topK,"expand",expand,"schema_contract",schema.identity()));
            if(request.length>64*1024) throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_ENTITY,"Yêu cầu truy xuất vượt giới hạn");
            return inspectionClient.post().uri("/v1/retrieve").contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION,"Bearer "+token).header("X-KAG-Release-ID",release).body(request).exchange((req,res)->{
                    var result=inspectionBody(res,token);
                    if(res.getStatusCode().value()!=200) {
                        String error=errorCode(result);
                        throw new ResponseStatusException(res.getStatusCode().value()==422?HttpStatus.UNPROCESSABLE_ENTITY:HttpStatus.SERVICE_UNAVAILABLE,
                            "Truy xuất KAG chưa khả dụng ("+error+")");
                    }
                    echo(res.getHeaders(),"X-KAG-Release-ID",release); validateRetrieval(result); return result;
                });
        } catch(ResponseStatusException e) { throw e; }
        catch(Exception e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Truy xuất KAG chưa khả dụng hoặc chưa được cấu hình"); }
    }
    private JsonNode inspectionBody(org.springframework.http.client.ClientHttpResponse response,String token) throws IOException {
        var type=response.getHeaders().getContentType();
        if(type==null||!type.getType().equalsIgnoreCase("application")||!type.getSubtype().equalsIgnoreCase("json")||(type.getCharset()!=null&&!type.getCharset().equals(StandardCharsets.UTF_8))||response.getHeaders().containsKey(HttpHeaders.CONTENT_ENCODING)) throw new IOException("Invalid response media");
        byte[] bytes=response.getBody().readNBytes(245761); if(bytes.length>245760) throw new IOException("Response too large");
        var body=parse(StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString(),token);
        if(body==null||!body.isObject()) throw new IOException("Invalid response");
        for(String file:List.of(tokenFile,inspectTokenFile)) {
            String other=null; try {other=readToken(file);} catch(IOException ignored) {}
            if(other!=null&&body.toString().contains(other)) throw new IOException("Credentials reflected");
        }
        return body;
    }
    private static String errorCode(JsonNode body) throws IOException {
        String code=body.path("error").path("code").asText();
        if(!Set.of("AUTH_REQUIRED","AUTH_INVALID","SCOPE_DENIED","INVALID_REQUEST","NOT_READY","RELEASE_UNAVAILABLE","QUERY_TIMEOUT","BACKEND_UNAVAILABLE","SCHEMA_CONTRACT_MISMATCH","RELEASE_MISMATCH","SOURCE_SNAPSHOT_MISMATCH","CONCURRENCY_LIMIT","RESULT_LIMIT_EXCEEDED","INTERNAL_ERROR","SOURCE_VALIDATION_FAILED","INVALID_NATIVE_RESULT").contains(code)) throw new IOException("Unknown error");
        return code;
    }
    private void validateRelease(JsonNode body) throws IOException {
        if(!fields(body).equals(Set.of("contract_version","release_id","release_kind","schema_contract","source_snapshot_id","source_catalog_sha256","release_descriptor_sha256","graph_fingerprint","backend_identity_verified","source_identity_verified","verified_at","query_ready","production_write"))||
            !body.path("contract_version").asText().equals("h1-read-v1.0")||!body.path("schema_contract").equals(json.valueToTree(schema.identity()))||
            !text(body.path("release_id"),512,true)||!text(body.path("source_snapshot_id"),512,true)||!text(body.path("release_kind"),128,true)||
            !body.path("production_write").asText().equals("blocked")||!body.path("verified_at").isNull()) throw new IOException("Invalid release");
        for(String field:List.of("source_catalog_sha256","release_descriptor_sha256","graph_fingerprint")) if(!body.path(field).asText().matches("[0-9a-f]{64}")) throw new IOException("Invalid release hash");
        for(String field:List.of("backend_identity_verified","source_identity_verified","query_ready")) if(!body.path(field).isBoolean()||body.path(field).asBoolean()) throw new IOException("Unsupported release proof");
    }
    private void validateRetrieval(JsonNode body) throws IOException {
        if(!fields(body).equals(Set.of("contract_version","request_id","release_id","source_snapshot_id","schema_contract","items"))||!body.path("contract_version").asText().equals("h1-read-v1.1")||
            !body.path("release_id").asText().equals(release)||!text(body.path("source_snapshot_id"),512,true)||!body.path("schema_contract").equals(json.valueToTree(schema.identity()))||
            !body.path("items").isArray()||body.path("items").size()>110) throw new IOException("Invalid retrieval");
        if(!UUID.fromString(body.path("request_id").asText()).toString().equals(body.path("request_id").asText())) throw new IOException("Invalid request identity");
        var seen=new HashSet<String>();
        for(var item:body.path("items")) {
            if(!fields(item).equals(Set.of("entity_type","entity_id","doc_id","unit_id","sign_id","source_texts","score","vector_sources","graph_context"))||
                !Set.of("VietRoadTraffic.LegalUnit","VietRoadTraffic.LegalDocument","VietRoadTraffic.TrafficSign").contains(item.path("entity_type").asText())||!text(item.path("entity_id"),245760,true)||
                !seen.add(item.path("entity_type").asText()+"\u0000"+item.path("entity_id").asText())||!item.path("source_texts").isObject()||item.path("source_texts").isEmpty()||
                !item.path("vector_sources").isArray()||!item.path("graph_context").isArray()) throw new IOException("Invalid evidence");
            for(String id:List.of("doc_id","unit_id","sign_id")) if(!item.path(id).isNull()&&!text(item.path(id),245760,true)) throw new IOException("Invalid source identity");
            String id=item.path("entity_type").asText().endsWith("LegalUnit")?"unit_id":item.path("entity_type").asText().endsWith("TrafficSign")?"sign_id":"doc_id";
            if(!item.path("entity_id").equals(item.path(id))) throw new IOException("Source identity mismatch");
            for(var source:item.path("source_texts")) if(!source.isNull()&&!text(source,245760,false)) throw new IOException("Invalid source text");
            double max=-1; var properties=new HashSet<String>();
            for(var vector:item.path("vector_sources")) {
                if(!fields(vector).equals(Set.of("property","score","index"))||!text(vector.path("property"),512,true)||!text(vector.path("index"),512,true)||
                    !item.path("source_texts").has(vector.path("property").asText())||!properties.add(vector.path("property").asText())||!score(vector.path("score"))) throw new IOException("Invalid vector metadata");
                max=Math.max(max,vector.path("score").asDouble());
            }
            if(item.path("score").isNull()?max!=-1||item.path("graph_context").isEmpty():!score(item.path("score"))||item.path("score").asDouble()!=max) throw new IOException("Invalid evidence score");
            for(var edge:item.path("graph_context")) {
                if(!fields(edge).equals(Set.of("from","predicate","to"))||!text(edge.path("predicate"),512,true)) throw new IOException("Invalid graph metadata");
                boolean incident=false;
                for(String side:List.of("from","to")) {
                    var endpoint=edge.path(side); if(!endpoint.isArray()||endpoint.size()!=2||!text(endpoint.get(0),512,true)||!text(endpoint.get(1),245760,true)) throw new IOException("Invalid graph endpoint");
                    incident|=endpoint.get(0).equals(item.path("entity_type"))&&endpoint.get(1).equals(item.path("entity_id"));
                }
                if(!incident) throw new IOException("Unrelated graph metadata");
            }
        }
    }
    private static boolean score(JsonNode value) {return value.isNumber()&&Double.isFinite(value.asDouble())&&value.asDouble()>=0&&value.asDouble()<=1;}
    public JsonNode query(Object request) {
        try {
            var admitted=admit(request);
            return breaker.executeSupplier(() -> post("/v1/query",admitted).exchange((req,res) -> {
                if(!res.getStatusCode().is2xxSuccessful()) return abstained(res,admitted);
                verifyHeaders(res.getHeaders(),admitted.date(),MediaType.APPLICATION_JSON);
                byte[] bytes=res.getBody().readNBytes(256*1024+1);
                if(bytes.length>256*1024) throw new IOException("KAG response too large");
                var result=parse(StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString(),admitted.token());
                validateResult(result); currentDate(admitted.date()); return result;
            }));
        } catch(Exception e) { throw unavailable(); }
    }
    public void stream(Object request,BiConsumer<String,JsonNode> consumer) {
        try {
            var admitted=admit(request);
            breaker.executeRunnable(() -> post("/v1/query/stream",admitted).accept(MediaType.TEXT_EVENT_STREAM).exchange((req,res) -> {
                if(!res.getStatusCode().is2xxSuccessful()) { consumer.accept("done",abstained(res,admitted)); return null; }
                verifyHeaders(res.getHeaders(),admitted.date(),MediaType.TEXT_EVENT_STREAM);
                try(var reader=new BufferedReader(new InputStreamReader(new LimitedInput(res.getBody()),StandardCharsets.UTF_8.newDecoder()))) {
                    String event="message",line; var payload=new StringBuilder(); boolean done=false;
                    while((line=reader.readLine())!=null) {
                        if(line.isEmpty()) {
                            if(payload.isEmpty()) continue;
                            if(!event.equals("delta")&&!event.equals("done")) throw new IOException("Unknown KAG event");
                            var result=parse(payload.toString(),admitted.token());
                            if(event.equals("done")) validateResult(result);
                            else if(!fields(result).equals(Set.of("text"))||!text(result.path("text"),4000,false)) throw new IOException("Invalid delta");
                            currentDate(admitted.date()); consumer.accept(event,result); payload.setLength(0);
                            if(event.equals("done")) { done=true; break; }
                            event="message";
                        } else if(line.startsWith("event:")) event=line.substring(6).trim();
                        else if(line.startsWith("data:")) { if(!payload.isEmpty()) payload.append('\n'); payload.append(line.substring(5).trim()); }
                    }
                    if(!done) throw new IOException("Incomplete KAG stream");
                }
                return null;
            }));
        } catch(Exception e) { throw unavailable(); }
    }
    private record Admitted(byte[] body,String token,LocalDate date) {}
    private JsonNode abstained(ClientHttpResponse response,Admitted admitted) throws IOException {
        var headers=response.getHeaders(); var media=headers.getContentType();
        if(response.getStatusCode().value()!=503||media==null||!media.getType().equalsIgnoreCase("application")||!media.getSubtype().equalsIgnoreCase("json")||
            (media.getCharset()!=null&&!media.getCharset().equals(StandardCharsets.UTF_8))||headers.containsKey(HttpHeaders.CONTENT_ENCODING)||
            !List.of("no-store").equals(headers.get(HttpHeaders.CACHE_CONTROL))) throw new IOException("Unverified KAG error");
        byte[] bytes=response.getBody().readNBytes(256*1024+1);
        if(bytes.length>256*1024) throw new IOException("KAG response too large");
        var body=parse(StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString(),admitted.token());
        if(!fields(body).equals(Set.of("request_id","error","native_state"))||!fields(body.path("error")).equals(Set.of("code","message","retryable"))||
            !body.path("error").path("code").isTextual()||!body.path("error").path("code").asText().equals("KAG_ABSTAINED")||
            !text(body.path("error").path("message"),4000,true)||!body.path("error").path("retryable").isBoolean()||body.path("error").path("retryable").asBoolean()||
            !body.path("native_state").isTextual()||!body.path("native_state").asText().equals("abstained")||!text(body.path("request_id"),36,true)) throw new IOException("Unverified KAG abstention");
        String id=body.path("request_id").asText();
        if(!UUID.fromString(id).toString().equals(id)) throw new IOException("Invalid request identity");
        echo(headers,"X-Request-ID",id);
        // Native errors have no success identity echoes; reject mismatches when echoes are present.
        for(var pin:Map.of("X-KAG-Release-ID",release,"X-WebApp-Snapshot-ID",snapshot,"X-KAG-As-Of",admitted.date().toString()).entrySet())
            if(headers.containsKey(pin.getKey())) echo(headers,pin.getKey(),pin.getValue());
        currentDate(admitted.date()); return json.createObjectNode().put("state","KAG_ABSTAINED");
    }
    private Admitted admit(Object request) throws IOException {
        headerIdentity(release); headerIdentity(snapshot);
        currentDate(LocalDate.now(clock));
        if(!(request instanceof Map<?,?> input)||!input.keySet().equals(REQUEST_FIELDS)||!(input.get("user_id") instanceof UUID owner)) throw new IOException("Invalid request");
        var body=json.valueToTree(request);
        if(!fields(body).equals(REQUEST_FIELDS)||!body.path("user_id").isTextual()||!owner.toString().equals(body.path("user_id").asText())||
            !text(body.path("message"),4000,true)||!body.path("context_id").isTextual()||!body.path("context_id").asText().isEmpty()||
            !body.path("schema_contract").equals(json.valueToTree(schema.identity()))) throw new IOException("Invalid request");
        byte[] bytes=json.writeValueAsBytes(body);
        if(bytes.length>64*1024) throw new IOException("Request too large");
        return new Admitted(bytes,readToken(tokenFile),LocalDate.now(clock));
    }
    private static String readToken(String credentialFile) throws IOException {
        if(credentialFile.isBlank()) throw new IOException("Credentials unavailable");
        Path path=Path.of(credentialFile);
        if(!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)||!Files.isReadable(path)) throw new IOException("Credentials unavailable");
        byte[] secret;
        try(var file=Files.newInputStream(path,LinkOption.NOFOLLOW_LINKS)) { secret=file.readNBytes(515); }
        if(secret.length>514) throw new IOException("Credentials unavailable");
        int length=secret.length;
        if(length>0&&secret[length-1]=='\n') {
            length--; if(length>0&&secret[length-1]=='\r') length--;
        }
        String token=StandardCharsets.US_ASCII.newDecoder().decode(ByteBuffer.wrap(secret,0,length)).toString();
        if(token.length()<43||token.length()>512||!token.matches("[A-Za-z0-9._~+/-]+=*")) throw new IOException("Credentials unavailable");
        return token;
    }
    private RestClient.RequestBodySpec post(String path,Admitted admitted) {
        currentDate(admitted.date());
        return client.post().uri(path).contentType(MediaType.APPLICATION_JSON).header(HttpHeaders.AUTHORIZATION,"Bearer "+admitted.token())
            .header("X-KAG-Release-ID",release).header("X-WebApp-Snapshot-ID",snapshot).header("X-KAG-As-Of",admitted.date().toString()).body(admitted.body());
    }
    private void verifyHeaders(HttpHeaders headers,LocalDate date,MediaType expected) throws IOException {
        echo(headers,"X-KAG-Release-ID",release); echo(headers,"X-WebApp-Snapshot-ID",snapshot); echo(headers,"X-KAG-As-Of",date.toString());
        var type=headers.getContentType();
        if(type==null||!expected.getType().equalsIgnoreCase(type.getType())||!expected.getSubtype().equalsIgnoreCase(type.getSubtype())||
            (type.getCharset()!=null&&!type.getCharset().equals(StandardCharsets.UTF_8))||headers.containsKey(HttpHeaders.CONTENT_ENCODING)) throw new IOException("Invalid response media");
        currentDate(date);
    }
    private static void echo(HttpHeaders headers,String name,String expected) throws IOException {
        var values=headers.get(name);
        if(values==null||values.size()!=1||!expected.equals(values.getFirst())) throw new IOException("Invalid identity echo");
    }
    private static void headerIdentity(String value) throws IOException {
        if(value.isBlank()||value.length()>512||!value.equals(value.strip())||value.chars().anyMatch(c->c<32||c>126)) throw new IOException("Identity unavailable");
    }
    private void currentDate(LocalDate expected) {
        if(!ZoneId.systemDefault().getRules().equals(LEGAL_ZONE.getRules())||!clock.getZone().getRules().equals(LEGAL_ZONE.getRules())||!expected.equals(LocalDate.now(clock))) throw unavailable();
    }
    private JsonNode parse(String value,String token) throws IOException {
        JsonNode result=json.reader().with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS).with(JsonParser.Feature.STRICT_DUPLICATE_DETECTION).readTree(value);
        if(result!=null&&result.toString().contains(token)) throw new IOException("Credentials reflected");
        return result;
    }
    private static Set<String> fields(JsonNode value) {
        var fields=new HashSet<String>(); if(value!=null&&value.isObject()) value.fieldNames().forEachRemaining(fields::add); return fields;
    }
    private static boolean text(JsonNode node,int max,boolean nonblank) {
        if(!node.isTextual()) return false;
        String value=node.asText();
        if(value.length()>max||(nonblank&&value.isBlank())) return false;
        for(int i=0;i<value.length();i++) {
            char c=value.charAt(i);
            if(Character.isHighSurrogate(c)) { if(++i==value.length()||!Character.isLowSurrogate(value.charAt(i))) return false; }
            else if(Character.isLowSurrogate(c)) return false;
        }
        return true;
    }
    private static void validateResult(JsonNode result) throws IOException {
        if(!fields(result).equals(Set.of("answer","citations"))||!text(result.path("answer"),20000,true)||!result.path("citations").isArray()||
            result.path("citations").isEmpty()||result.path("citations").size()>20) throw new IOException("Invalid result");
        for(var c:result.path("citations")) {
            if(!fields(c).equals(CITATION_FIELDS)||!text(c.path("doc_id"),256*1024,true)||!text(c.path("unit_id"),256*1024,true)||!c.path("sign_id").isNull()||
                !c.path("evidence_id").isTextual()||!c.path("evidence_id").asText().matches("[0-9a-f]{64}")||!c.path("field").asText().equals("text")||
                !text(c.path("quote"),20000,true)||!c.path("start").isIntegralNumber()||!c.path("start").canConvertToInt()||c.path("start").intValue()!=0||
                !c.path("end").isIntegralNumber()||!c.path("end").canConvertToInt()||c.path("end").intValue()!=c.path("quote").asText().codePointCount(0,c.path("quote").asText().length())) throw new IOException("Invalid citation structure");
        }
    }
    private static ResponseStatusException unavailable() { return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Dịch vụ KAG chưa khả dụng"); }
    private static class LimitedInput extends FilterInputStream {
        int total;
        LimitedInput(InputStream input) { super(input); }
        private void count(int n) throws IOException { if(n>0 && (total+=n)>256*1024) throw new IOException("Stream too large"); }
        @Override public int read() throws IOException { int n=super.read(); count(n<0?0:1); return n; }
        @Override public int read(byte[] b,int off,int len) throws IOException { int n=super.read(b,off,len); count(n); return n; }
    }
}
