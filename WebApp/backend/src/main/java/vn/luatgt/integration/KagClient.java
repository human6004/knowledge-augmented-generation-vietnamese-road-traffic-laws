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
    private final RestClient client; private final ObjectMapper json;
    private final KagSchema schema;
    private final String tokenFile,release,snapshot;
    private final Clock clock;
    private static final ZoneId LEGAL_ZONE=ZoneId.of("Asia/Saigon");
    private static final Set<String> REQUEST_FIELDS=Set.of("user_id","message","context_id","schema_contract");
    private static final Set<String> CITATION_FIELDS=Set.of("doc_id","unit_id","sign_id","evidence_id","field","start","end","quote");
    private final CircuitBreaker breaker=CircuitBreaker.of("kag",CircuitBreakerConfig.custom().minimumNumberOfCalls(3).slidingWindowSize(6).waitDurationInOpenState(Duration.ofSeconds(30)).build());
    public KagClient(@Value("${app.kag-url}") String url,ObjectMapper json,KagSchema schema,
        @Value("${app.kag-token-file:}") String tokenFile,@Value("${app.kag-release-id:}") String release,
        @Value("${app.kag-webapp-snapshot-id:}") String snapshot,ObjectProvider<Clock> clocks) {
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        factory.setReadTimeout(Duration.ofSeconds(30));
        this.client=RestClient.builder().baseUrl(url).requestFactory(factory).build(); this.json=json;
        this.schema=schema; this.tokenFile=tokenFile; this.release=release; this.snapshot=snapshot;
        this.clock=clocks.getIfAvailable(Clock::systemDefaultZone);
    }
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
        if(tokenFile.isBlank()) throw new IOException("Credentials unavailable");
        Path path=Path.of(tokenFile);
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
        return new Admitted(bytes,token,LocalDate.now(clock));
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
