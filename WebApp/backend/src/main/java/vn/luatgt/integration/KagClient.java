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
    public Map<String,Object> status() {
        return Map.of("liveness",probe("/v1/health","either"),
            "queryReadiness",probe("/v1/health?mode=ready&capability=query-v1","query"),
            "retrievalReadiness",probe("/v1/health?mode=ready&capability=retrieve","inspect"),
            "release",probe("/v1/graph/release","either"));
    }
    public JsonNode pipelineStatus() { return inspectView("/v1/pipeline/status",true); }
    public JsonNode benchmarkDatasets() { return inspectView("/v1/benchmark/datasets",false); }
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
    private void validateDatasets(JsonNode body) throws IOException {
        if(!fields(body).equals(Set.of("contract_version","state","datasets","execution_allowed","execution_blockers","metrics"))||!body.path("metrics").isNull()||
            !body.path("execution_blockers").equals(json.valueToTree(List.of("OPERATIONAL_PROOF_REQUIRED","BENCHMARK_EXECUTION_NOT_AUTHORIZED")))||
            !Set.of("AVAILABLE","NOT_CONFIGURED","UNAVAILABLE","LIMIT_EXCEEDED").contains(body.path("state").asText())||!body.path("datasets").isArray()||body.path("datasets").size()>20||
            (!body.path("state").asText().equals("AVAILABLE")&&!body.path("datasets").isEmpty())) throw new IOException("Invalid dataset catalog");
        var seen=new HashSet<String>();
        for(var row:body.path("datasets")) {
            String id=row.path("id").asText(),status=row.path("dataset_status").asText(),eligibility=row.path("dataset_eligibility").asText();
            if(!fields(row).equals(Set.of("id","dataset_status","dataset_eligibility","reason","dataset_hash","record_count","official_benchmark"))||!id.matches("[A-Za-z0-9_.-]{1,128}(?:/eval_questions\\.jsonl)?")||
                id.startsWith("../")||!seen.add(id)||!row.path("official_benchmark").isBoolean()||!Set.of("ELIGIBLE","BLOCKED").contains(eligibility)) throw new IOException("Invalid dataset identity");
            if(!row.path("dataset_status").isNull()&&!Set.of("PROVISIONAL","FROZEN").contains(status)) throw new IOException("Invalid dataset status");
            if(!row.path("dataset_hash").isNull()&&!row.path("dataset_hash").asText().matches("[0-9a-f]{64}")) throw new IOException("Invalid dataset hash");
            if(!row.path("record_count").isNull()&&(!row.path("record_count").isIntegralNumber()||!row.path("record_count").canConvertToLong()||row.path("record_count").asLong()<1)) throw new IOException("Invalid dataset count");
            if(eligibility.equals("ELIGIBLE")) {
                if(!status.equals("FROZEN")||row.path("dataset_hash").isNull()||row.path("record_count").isNull()||!row.path("reason").isNull()) throw new IOException("Unverified dataset eligibility");
            } else if(!Set.of("PROVISIONAL_DATASET","NO_GOLD","INVALID_DATASET","DATASET_TOO_LARGE").contains(row.path("reason").asText())) throw new IOException("Invalid blocked dataset");
            if(row.path("official_benchmark").asBoolean()&&!status.equals("FROZEN")) throw new IOException("Unverified official dataset");
        }
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
                        String capability=scope.equals("inspect")?"retrieve":"query-v1";
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
                String capability=scope.equals("inspect")?"retrieve":"query-v1";
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
                if(!res.getStatusCode().is2xxSuccessful()) throw new IOException("KAG error");
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
                if(!res.getStatusCode().is2xxSuccessful()) throw new IOException("KAG error");
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
