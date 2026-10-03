package vn.luatgt.integration;

import com.fasterxml.jackson.databind.*;
import io.github.resilience4j.circuitbreaker.*;
import java.io.*;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.function.BiConsumer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@Component
public class KagClient {
    private final RestClient client; private final ObjectMapper json;
    private final CircuitBreaker breaker=CircuitBreaker.of("kag",CircuitBreakerConfig.custom().minimumNumberOfCalls(3).slidingWindowSize(6).waitDurationInOpenState(Duration.ofSeconds(30)).build());
    public KagClient(@Value("${app.kag-url}") String url,ObjectMapper json) {
        var factory=new JdkClientHttpRequestFactory(HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build());
        factory.setReadTimeout(Duration.ofSeconds(30));
        this.client=RestClient.builder().baseUrl(url).requestFactory(factory).build(); this.json=json;
    }
    public JsonNode query(Object request) {
        try {
            return breaker.executeSupplier(() -> client.post().uri("/v1/query").body(request).exchange((req,res) -> {
                if(!res.getStatusCode().is2xxSuccessful()) throw new IOException("KAG error");
                byte[] bytes=res.getBody().readNBytes(256*1024+1);
                if(bytes.length>256*1024) throw new IOException("KAG response too large");
                return json.readTree(bytes);
            }));
        } catch(RuntimeException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Dịch vụ KAG chưa khả dụng"); }
    }
    public void stream(Object request,BiConsumer<String,JsonNode> consumer) {
        try {
            breaker.executeRunnable(() -> client.post().uri("/v1/query/stream").accept(MediaType.TEXT_EVENT_STREAM).body(request).exchange((req,res) -> {
                if(!res.getStatusCode().is2xxSuccessful()||res.getHeaders().getContentType()==null||!MediaType.TEXT_EVENT_STREAM.isCompatibleWith(res.getHeaders().getContentType())) throw new IOException("Invalid KAG stream");
                try(var reader=new BufferedReader(new InputStreamReader(new LimitedInput(res.getBody()),java.nio.charset.StandardCharsets.UTF_8))) {
                    String event="message",line; var payload=new StringBuilder(); boolean done=false;
                    while((line=reader.readLine())!=null) {
                        if(line.isEmpty()) {
                            if(payload.isEmpty()) continue;
                            if(!event.equals("delta")&&!event.equals("done")) throw new IOException("Unknown KAG event");
                            consumer.accept(event,json.readTree(payload.toString())); payload.setLength(0);
                            if(event.equals("done")) { done=true; break; }
                            event="message";
                        } else if(line.startsWith("event:")) event=line.substring(6).trim();
                        else if(line.startsWith("data:")) { if(!payload.isEmpty()) payload.append('\n'); payload.append(line.substring(5).trim()); }
                    }
                    if(!done) throw new IOException("Incomplete KAG stream");
                }
                return null;
            }));
        } catch(RuntimeException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Dịch vụ KAG chưa khả dụng"); }
    }
    private static class LimitedInput extends FilterInputStream {
        int total;
        LimitedInput(InputStream input) { super(input); }
        private void count(int n) throws IOException { if(n>0 && (total+=n)>256*1024) throw new IOException("Stream too large"); }
        @Override public int read() throws IOException { int n=super.read(); count(n<0?0:1); return n; }
        @Override public int read(byte[] b,int off,int len) throws IOException { int n=super.read(b,off,len); count(n); return n; }
    }
}
