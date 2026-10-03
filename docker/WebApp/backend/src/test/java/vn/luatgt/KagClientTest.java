package vn.luatgt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.integration.KagClient;
import static org.junit.jupiter.api.Assertions.*;

class KagClientTest {
    @Test void transportReadsRestAndSseAndRejectsIncompleteStream() throws Exception {
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        var answer="{\"answer\":\"Nội dung thử\",\"citations\":[{\"doc_id\":\"test\",\"unit_id\":\"1\"}]}";
        var complete=new java.util.concurrent.atomic.AtomicBoolean(true);
        server.createContext("/v1/query",exchange -> {
            byte[] bytes=answer.getBytes(java.nio.charset.StandardCharsets.UTF_8); exchange.sendResponseHeaders(200,bytes.length);
            try(var output=exchange.getResponseBody()) { output.write(bytes); }
        });
        server.createContext("/v1/query/stream",exchange -> {
            String body="event: delta\ndata: {\"text\":\"Nội dung thử\"}\n\n"+(complete.get()?"event: done\ndata: "+answer+"\n\n":"");
            byte[] bytes=body.getBytes(java.nio.charset.StandardCharsets.UTF_8); exchange.getResponseHeaders().set("Content-Type","text/event-stream"); exchange.sendResponseHeaders(200,bytes.length);
            try(var output=exchange.getResponseBody()) { output.write(bytes); }
        });
        server.start();
        try {
            var client=new KagClient("http://127.0.0.1:"+server.getAddress().getPort(),new ObjectMapper());
            assertEquals("Nội dung thử",client.query(Map.of("message","test")).path("answer").asText());
            var events=new ArrayList<String>(); client.stream(Map.of("message","test"),(event,data) -> events.add(event));
            assertEquals(List.of("delta","done"),events);
            complete.set(false);
            assertThrows(ResponseStatusException.class,() -> client.stream(Map.of("message","test"),(event,data) -> {}));
        } finally { server.stop(0); }
    }
}
