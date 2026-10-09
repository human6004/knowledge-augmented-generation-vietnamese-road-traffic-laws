package vn.luatgt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.integration.KagClient;
import vn.luatgt.service.KagSchema;
import static org.junit.jupiter.api.Assertions.*;

class KagClientTest {
    @TempDir Path temporary;
    final ObjectMapper json=new ObjectMapper();
    final UUID owner=UUID.fromString("00000000-0000-4000-8000-000000000001");
    static final String TOKEN="t".repeat(43),RELEASE="synthetic-release",SNAPSHOT="synthetic-publication";
    KagSchema schema; Path secret;
    @BeforeEach void setup() throws Exception { schema=new KagSchema(json); secret=temporary.resolve("service.key"); Files.writeString(secret,TOKEN); }
    Map<String,Object> request() { return new HashMap<>(Map.of("user_id",owner,"message","Căn cứ nào?","context_id","","schema_contract",schema.identity())); }
    JsonNode answer() {
        var result=json.createObjectNode().put("answer","Căn cứ nguyên văn 🚦.");
        String quote="Nội dung thử 🚦.";
        result.putArray("citations").addObject().put("doc_id","test").put("unit_id","test::1").putNull("sign_id")
            .put("evidence_id","a".repeat(64)).put("field","text").put("start",0).put("end",quote.codePointCount(0,quote.length())).put("quote",quote);
        return result;
    }
    class Fixture implements AutoCloseable {
        final HttpServer server; final AtomicInteger calls=new AtomicInteger();
        final Map<String,List<String>> headers=new TreeMap<>(String.CASE_INSENSITIVE_ORDER); JsonNode received;
        int status=200,delay; String media="application/json",omit,wrong,duplicate;
        String body=answer().toString(),delta="Nội dung thử",encoding; byte[] raw; boolean incomplete,closeBeforeHeaders;
        final AtomicReference<Runnable> onRequest=new AtomicReference<>(()->{});
        Fixture() throws Exception {
            server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            server.createContext("/v1/query",exchange->{
                calls.incrementAndGet(); headers.clear(); headers.putAll(exchange.getRequestHeaders());
                received=json.readTree(exchange.getRequestBody().readAllBytes());
                onRequest.get().run();
                if(closeBeforeHeaders) { exchange.close(); return; }
                if(delay>0) try { Thread.sleep(delay); } catch(InterruptedException e) { Thread.currentThread().interrupt(); }
                for(String name:List.of("X-KAG-Release-ID","X-WebApp-Snapshot-ID","X-KAG-As-Of")) {
                    String value=exchange.getRequestHeaders().getFirst(name);
                    if(value==null) value=name.equals("X-KAG-Release-ID")?RELEASE:name.equals("X-WebApp-Snapshot-ID")?SNAPSHOT:LocalDate.now(ZoneId.of("Asia/Saigon")).toString();
                    if(!name.equals(omit)) exchange.getResponseHeaders().add(name,name.equals(wrong)?"wrong":value);
                    if(name.equals(duplicate)) exchange.getResponseHeaders().add(name,value);
                }
                boolean streaming=exchange.getRequestURI().getPath().endsWith("/stream");
                exchange.getResponseHeaders().set("Content-Type",streaming&&media.equals("application/json")?"text/event-stream":media);
                if(encoding!=null) exchange.getResponseHeaders().set("Content-Encoding",encoding);
                byte[] bytes=raw!=null?raw:(streaming?"event: delta\ndata: "+json.createObjectNode().put("text",delta)+"\n\n"+(incomplete?"":"event: done\ndata: "+body+"\n\n"):body).getBytes(java.nio.charset.StandardCharsets.UTF_8);
                try { exchange.sendResponseHeaders(status,bytes.length); try(var out=exchange.getResponseBody()) { out.write(bytes); } }
                catch(java.io.IOException expectedDisconnect) { exchange.close(); }
            });
            server.start();
        }
        String url() { return "http://127.0.0.1:"+server.getAddress().getPort(); }
        @Override public void close() { server.stop(0); }
    }
    KagClient client(Fixture f,Map<String,Object> overrides,Clock clock) {
        var properties=new HashMap<String,Object>(Map.of("app.kag-url",f.url(),"app.kag-token-file",secret.toString(),"app.kag-release-id",RELEASE,"app.kag-webapp-snapshot-id",SNAPSHOT));
        properties.putAll(overrides);
        try(var context=new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("synthetic",properties));
            context.registerBean(ObjectMapper.class,()->json); context.registerBean(KagSchema.class,()->schema);
            if(clock!=null) context.registerBean(Clock.class,()->clock);
            context.register(KagClient.class); context.refresh(); return context.getBean(KagClient.class);
        }
    }
    KagClient client(Fixture f) { return client(f,Map.of(),null); }
    void unavailable(org.junit.jupiter.api.function.Executable call) {
        var error=assertThrows(ResponseStatusException.class,call);
        assertEquals(503,error.getStatusCode().value()); assertEquals("Dịch vụ KAG chưa khả dụng",error.getReason());
        assertNull(error.getCause()); assertFalse(error.toString().contains(TOKEN)); assertFalse(error.toString().contains(secret.toString()));
    }
    @Test void transportReadsRestAndSseAndRejectsIncompleteStream() throws Exception {
        try(var f=new Fixture()) {
            var client=client(f); assertEquals(answer(),client.query(request()));
            var events=new ArrayList<String>(); client.stream(request(),(event,data)->events.add(event));
            assertEquals(List.of("delta","done"),events); f.incomplete=true;
            unavailable(()->client.stream(request(),(event,data)->{}));
        }
    }
    @Test void serviceBearerAndPinsUseOnlyServerConfiguration() throws Exception {
        try(var f=new Fixture()) {
            assertEquals(answer(),client(f).query(request()));
            assertTrue(List.of("Bearer "+TOKEN).equals(f.headers.get("Authorization")));
            assertEquals(List.of(RELEASE),f.headers.get("X-kag-release-id"));
            assertEquals(List.of(SNAPSHOT),f.headers.get("X-webapp-snapshot-id"));
            assertEquals(List.of(LocalDate.now().toString()),f.headers.get("X-kag-as-of"));
            assertEquals(owner.toString(),f.received.path("user_id").asText());
            assertEquals(json.valueToTree(schema.identity()),f.received.path("schema_contract"));
            assertEquals(Set.of("user_id","message","context_id","schema_contract"),fields(f.received));
            assertFalse(f.received.toString().contains(TOKEN));
        }
    }
    static Set<String> fields(JsonNode n) { var fields=new HashSet<String>(); n.fieldNames().forEachRemaining(fields::add); return fields; }
    @Test void secretRotationReloadsOnlyConfiguredFileWithoutRetry() throws Exception {
        try(var f=new Fixture()) {
            var client=client(f); client.query(request()); Files.writeString(secret,"u".repeat(43)); client.query(request());
            assertTrue(List.of("Bearer "+"u".repeat(43)).equals(f.headers.get("Authorization"))); assertEquals(2,f.calls.get());
        }
    }
    @ParameterizedTest @ValueSource(strings={"app.kag-token-file","app.kag-release-id","app.kag-webapp-snapshot-id"})
    void missingConfigurationFailsBeforeHttp(String property) throws Exception {
        try(var f=new Fixture()) { var client=client(f,Map.of(property,""),null); unavailable(()->client.query(request())); assertEquals(0,f.calls.get()); }
    }
    @Test void missingSecretFailsBeforeHttp() throws Exception {
        Files.delete(secret); try(var f=new Fixture()) { unavailable(()->client(f).query(request())); assertEquals(0,f.calls.get()); }
    }
    @Test void unreadableSecretFailsBeforeHttp() throws Exception {
        var view=Files.getFileAttributeView(secret,AclFileAttributeView.class); assertNotNull(view,"Windows ACL fixture required");
        var original=view.getAcl(); var denied=new ArrayList<AclEntry>();
        denied.add(AclEntry.newBuilder().setType(AclEntryType.DENY).setPrincipal(view.getOwner()).setPermissions(AclEntryPermission.READ_DATA).build()); denied.addAll(original);
        view.setAcl(denied);
        try(var f=new Fixture()) { unavailable(()->client(f).query(request())); assertEquals(0,f.calls.get()); }
        finally { view.setAcl(original); }
    }
    @ParameterizedTest @ValueSource(strings={"short","newline","bom","long","nonascii"})
    void invalidSecretFailsBeforeHttp(String mode) throws Exception {
        Files.writeString(secret,switch(mode) { case "short"->"x"; case "newline"->TOKEN+"\n"; case "bom"->"\ufeff"+TOKEN; case "long"->"x".repeat(513); default->"é".repeat(43); });
        try(var f=new Fixture()) { unavailable(()->client(f).query(request())); assertEquals(0,f.calls.get()); }
    }
    @ParameterizedTest @ValueSource(strings={"user_id","schema_contract","message","context_id","Authorization"})
    void invalidOrBrowserControlledRequestRejectedBeforeHttp(String field) throws Exception {
        var request=request(); request.put(field,switch(field) { case "user_id"->owner.toString().toUpperCase(Locale.ROOT); case "schema_contract"->Map.of("namespace","fake"); case "message"->"\ud800"; case "context_id"->"unsupported"; default->"Bearer forged-browser-token"; });
        try(var f=new Fixture()) { unavailable(()->client(f).query(request)); assertEquals(0,f.calls.get()); }
    }
    @ParameterizedTest @ValueSource(strings={"namespace","schema_sha256","contract_sha256"})
    void alteredSchemaIdentityRejectedBeforeHttp(String field) throws Exception {
        var identity=new HashMap<>(schema.identity()); identity.put(field,"wrong"); var request=request(); request.put("schema_contract",identity);
        try(var f=new Fixture()) { unavailable(()->client(f).query(request)); assertEquals(0,f.calls.get()); }
    }
    @ParameterizedTest @ValueSource(strings={"X-KAG-Release-ID","X-WebApp-Snapshot-ID","X-KAG-As-Of"})
    void missingWrongDuplicateEchoRejectedBeforeBodyOrConsumer(String header) throws Exception {
        for(String mode:List.of("missing","wrong","duplicate")) try(var f=new Fixture()) {
            if(mode.equals("missing")) f.omit=header; else if(mode.equals("wrong")) f.wrong=header; else f.duplicate=header;
            var client=client(f); unavailable(()->client.query(request())); var events=new AtomicInteger();
            unavailable(()->client.stream(request(),(event,data)->events.incrementAndGet())); assertEquals(0,events.get());
        }
    }
    @Test void dateRolloverRejectsOldEchoEvenAfterSuccessfulHttp() throws Exception {
        var instant=new AtomicReference<>(Instant.now());
        Clock clock=new Clock() { public ZoneId getZone(){return ZoneId.of("Asia/Saigon");} public Clock withZone(ZoneId zone){return this;} public Instant instant(){return instant.get();} };
        try(var f=new Fixture()) { f.onRequest.set(()->instant.updateAndGet(value->value.plus(Duration.ofDays(1)))); unavailable(()->client(f,Map.of(),clock).query(request())); }
    }
    @Test void wrongJvmTimezoneFailsClosed() throws Exception {
        var old=TimeZone.getDefault(); TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
        try(var f=new Fixture()) { unavailable(()->client(f).query(request())); assertEquals(0,f.calls.get()); }
        finally { TimeZone.setDefault(old); }
    }
    @ParameterizedTest @ValueSource(strings={"{}","{\"answer\":\"x\"}","{\"answer\":\"x\",\"citations\":[]}","null","[]","{\"answer\":\"x\",\"answer\":\"y\",\"citations\":[]}","NaN","{\"answer\":\"x\",\"citations\":[]} {}"})
    void malformedOrEmptyResultRejected(String body) throws Exception {
        try(var f=new Fixture()) { f.body=body; unavailable(()->client(f).query(request())); }
    }
    @ParameterizedTest @ValueSource(strings={"quote","unit_id","doc_id","field","sign_id","start","extra"})
    void invalidCitationCannotBeRepairedOrDropped(String field) throws Exception {
        var body=(com.fasterxml.jackson.databind.node.ObjectNode)answer(); var citation=(com.fasterxml.jackson.databind.node.ObjectNode)body.path("citations").get(0);
        if(field.equals("start")) citation.put(field,-1); else if(field.equals("sign_id")) citation.put(field,"sign-only"); else if(field.equals("field")) citation.put(field,"title");
        else if(field.equals("extra")) citation.put(field,true); else citation.putNull(field);
        try(var f=new Fixture()) { f.body=body.toString(); unavailable(()->client(f).query(request())); }
    }
    @Test void exactEveryCitationAndUtf16LimitsArePreserved() throws Exception {
        var body=(com.fasterxml.jackson.databind.node.ObjectNode)answer(); body.put("answer","🚦".repeat(10000));
        var citations=(com.fasterxml.jackson.databind.node.ArrayNode)body.path("citations"); citations.add(citations.get(0).deepCopy());
        try(var f=new Fixture()) { f.body=body.toString(); assertEquals(body,client(f).query(request())); body.put("answer","🚦".repeat(10000)+"x"); f.body=body.toString(); unavailable(()->client(f).query(request())); }
    }
    @Test void responseByteCapRemainsExactly256KiB() throws Exception {
        try(var f=new Fixture()) { int size=f.body.getBytes(java.nio.charset.StandardCharsets.UTF_8).length; f.body+=" ".repeat(256*1024-size);
            var client=client(f); assertEquals(answer(),client.query(request())); f.body+=" "; unavailable(()->client.query(request())); }
    }
    @ParameterizedTest @ValueSource(strings={"text/plain","application/json; charset=iso-8859-1","application/xml"})
    void unsupportedResponseMediaRejected(String media) throws Exception { try(var f=new Fixture()) { f.media=media; unavailable(()->client(f).query(request())); } }
    @ParameterizedTest @ValueSource(ints={401,403,409,422,429,500,502,503,504})
    void allNon2xxRemainGeneric503WithoutParsingNativeErrors(int status) throws Exception {
        for(String code:List.of("KAG_ABSTAINED","V1_RESULT_UNREPRESENTABLE")) try(var f=new Fixture()) {
            f.status=status; f.body="{\"code\":\""+code+"\",\"answer\":\"fabricated\",\"secret\":\""+TOKEN+"\"}";
            unavailable(()->client(f).query(request())); assertEquals(1,f.calls.get());
        }
    }
    @Test void circuitBreakerAndNoUnsafePostRetryRemain() throws Exception {
        try(var f=new Fixture()) { f.status=503; var client=client(f); for(int i=0;i<4;i++) unavailable(()->client.query(request())); assertEquals(3,f.calls.get()); }
        try(var f=new Fixture()) { f.closeBeforeHeaders=true; unavailable(()->client(f).query(request())); assertEquals(1,f.calls.get()); }
    }
    @Test void realReadTimeoutRemains30Seconds() throws Exception {
        try(var f=new Fixture()) { f.delay=31000; long start=System.nanoTime(); unavailable(()->client(f).query(request()));
            long seconds=Duration.ofNanos(System.nanoTime()-start).toSeconds(); assertTrue(seconds>=29&&seconds<36); assertEquals(1,f.calls.get()); }
    }
    @Test void reflectedServiceTokenNeverReachesRestOrStreamConsumer() throws Exception {
        try(var f=new Fixture()) {
            f.body=((com.fasterxml.jackson.databind.node.ObjectNode)answer()).put("answer",TOKEN).toString();
            unavailable(()->client(f).query(request()));
        }
        try(var f=new Fixture()) {
            f.delta=TOKEN; var events=new AtomicInteger();
            unavailable(()->client(f).stream(request(),(event,data)->events.incrementAndGet())); assertEquals(0,events.get());
        }
    }
    @Test void strictWireRejectsMalformedUtf8CompressionAndDuplicateValidFields() throws Exception {
        for(String mode:List.of("utf8","gzip","duplicate","surrogate","unknown")) try(var f=new Fixture()) {
            if(mode.equals("utf8")) f.raw=new byte[]{(byte)0xc3,0x28};
            else if(mode.equals("gzip")) f.encoding="gzip";
            else if(mode.equals("duplicate")) f.body="{\"answer\":\"x\","+f.body.substring(1);
            else if(mode.equals("surrogate")) f.body=f.body.replace("Căn cứ nguyên văn 🚦.","\\ud800");
            else f.body="{\"unknown\":true,"+f.body.substring(1);
            unavailable(()->client(f).query(request()));
        }
    }
    @Test void doneOnlyPreservesEveryCitationAndExactRestPayload() throws Exception {
        try(var f=new Fixture()) {
            var expected=(com.fasterxml.jackson.databind.node.ObjectNode)answer();
            var citations=(com.fasterxml.jackson.databind.node.ArrayNode)expected.path("citations");
            var second=(com.fasterxml.jackson.databind.node.ObjectNode)citations.get(0).deepCopy();
            second.put("unit_id","test::2").put("evidence_id","b".repeat(64));
            citations.add(second); f.body=expected.toString();
            f.raw=("event: done\ndata: "+f.body+"\n\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
            f.media="text/event-stream; charset=utf-8";
            var events=new ArrayList<String>(); var payloads=new ArrayList<JsonNode>();
            client(f).stream(request(),(event,data)->{ events.add(event); payloads.add(data); });
            assertEquals(List.of("done"),events); assertEquals(List.of(expected),payloads);
            f.raw=null; f.media="application/json";
            assertEquals(expected,client(f).query(request()));
        }
    }
    @Test void legacyDeltaDoneRemainsExactAndOrdered() throws Exception {
        try(var f=new Fixture()) {
            var events=new ArrayList<String>(); var payloads=new ArrayList<JsonNode>();
            client(f).stream(request(),(event,data)->{ events.add(event); payloads.add(data); });
            assertEquals(List.of("delta","done"),events);
            assertEquals(json.createObjectNode().put("text",f.delta),payloads.getFirst());
            assertEquals(answer(),payloads.getLast());
        }
    }
    @ParameterizedTest @ValueSource(strings={"missing","truncated-json","no-blank","one-newline","unknown-error","partial-error","duplicate-json","malformed-utf8","empty-citations"})
    void malformedOrIncompleteSseNeverDeliversDone(String mode) throws Exception {
        try(var f=new Fixture()) {
            String done="event: done\ndata: "+f.body;
            String delta="event: delta\ndata: {\"text\":\"partial\"}\n\n";
            f.raw=switch(mode) {
                case "missing" -> delta.getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "truncated-json" -> (done.substring(0,done.length()-1)+"\n\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "no-blank" -> done.getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "one-newline" -> (done+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "unknown-error" -> "event: error\ndata: {\"message\":\"unavailable\"}\n\n".getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "partial-error" -> (delta+"event: error\ndata: {\"message\":").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "duplicate-json" -> ("event: done\ndata: {\"answer\":\"x\","+f.body.substring(1)+"\n\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                case "empty-citations" -> "event: done\ndata: {\"answer\":\"x\",\"citations\":[]}\n\n".getBytes(java.nio.charset.StandardCharsets.UTF_8);
                default -> new byte[]{(byte)0xc3,0x28};
            };
            var events=new ArrayList<String>(); unavailable(()->client(f).stream(request(),(event,data)->events.add(event)));
            assertFalse(events.contains("done"));
            assertEquals(mode.equals("missing")||mode.equals("partial-error")?List.of("delta"):List.of(),events);
        }
    }
    @Test void streamByteCeilingRejectsWholeOversizedDoneWithoutConsumer() throws Exception {
        for(int size:new int[]{245760,256*1024,256*1024+1}) try(var f=new Fixture()) {
            String frame="event: done\ndata: "+f.body;
            int padding=size-frame.getBytes(java.nio.charset.StandardCharsets.UTF_8).length-2;
            f.raw=(frame+" ".repeat(padding)+"\n\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
            assertEquals(size,f.raw.length);
            var events=new ArrayList<String>();
            if(size<=256*1024) {
                client(f).stream(request(),(event,data)->{ events.add(event); assertEquals(answer(),data); });
                assertEquals(List.of("done"),events);
            } else {
                unavailable(()->client(f).stream(request(),(event,data)->events.add(event)));
                assertTrue(events.isEmpty());
            }
        }
    }
    @ParameterizedTest @ValueSource(strings={"json-media","text-media","wrong-charset","gzip","missing-release","wrong-snapshot","duplicate-date"})
    void invalidSseMediaOrIdentityFailsBeforeAnyEvent(String mode) throws Exception {
        try(var f=new Fixture()) {
            f.raw=("event: done\ndata: "+f.body+"\n\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
            switch(mode) {
                case "json-media" -> f.media="application/json; charset=utf-8";
                case "text-media" -> f.media="text/plain";
                case "wrong-charset" -> f.media="text/event-stream; charset=iso-8859-1";
                case "gzip" -> f.encoding="gzip";
                case "missing-release" -> f.omit="X-KAG-Release-ID";
                case "wrong-snapshot" -> f.wrong="X-WebApp-Snapshot-ID";
                default -> f.duplicate="X-KAG-As-Of";
            }
            var events=new ArrayList<String>(); unavailable(()->client(f).stream(request(),(event,data)->events.add(event)));
            assertTrue(events.isEmpty());
        }
    }
    @ParameterizedTest @ValueSource(ints={409,502,503,504})
    void preheaderSseFailuresNeverConsumeFabricatedDone(int status) throws Exception {
        try(var f=new Fixture()) {
            f.status=status; f.raw=("event: done\ndata: "+f.body+"\n\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
            var events=new ArrayList<String>(); unavailable(()->client(f).stream(request(),(event,data)->events.add(event)));
            assertTrue(events.isEmpty()); assertEquals(1,f.calls.get());
        }
    }
    @ParameterizedTest @ValueSource(strings={"exact","one-over","astral-exact","astral-one-over"})
    void legacyDeltaUtf16LimitRejectsBeforeConsumer(String mode) throws Exception {
        try(var f=new Fixture()) {
            f.delta=switch(mode) {
                case "exact" -> "x".repeat(4000);
                case "one-over" -> "x".repeat(4001);
                case "astral-exact" -> "🚦".repeat(2000);
                default -> "🚦".repeat(2000)+"x";
            };
            var events=new ArrayList<String>();
            if(mode.endsWith("one-over")) {
                unavailable(()->client(f).stream(request(),(event,data)->events.add(event)));
                assertTrue(events.isEmpty());
            } else {
                client(f).stream(request(),(event,data)->events.add(event));
                assertEquals(List.of("delta","done"),events);
            }
        }
    }
}
