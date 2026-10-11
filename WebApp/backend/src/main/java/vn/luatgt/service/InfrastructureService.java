package vn.luatgt.service;
import vn.luatgt.integration.ObjectStorage;
import vn.luatgt.integration.KagClient;
import vn.luatgt.dto.KagRetrieveRequest;
import com.fasterxml.jackson.databind.JsonNode;
import javax.sql.DataSource;
import java.util.*;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
@Service
public class InfrastructureService {
    private final DataSource database; private final StringRedisTemplate redis; private final ObjectStorage storage; private final KagClient kag;
    public InfrastructureService(DataSource database,StringRedisTemplate redis,ObjectStorage storage,KagClient kag) { this.database=database; this.redis=redis; this.storage=storage; this.kag=kag; }
    public Map<String,Object> kagStatus() { return kag.status(); }
    public JsonNode pipelineStatus() { return kag.pipelineStatus(); }
    public JsonNode benchmarkDatasets() { return kag.benchmarkDatasets(); }
    public JsonNode retrieve(KagRetrieveRequest request) { return kag.retrieve(request.message(),request.top_k(),request.expand()); }
    public Map<String,String> status() {
        var result=new LinkedHashMap<String,String>();
        try(var connection=database.getConnection()) { result.put("MySQL",connection.isValid(2)?"UP":"DOWN"); } catch(Exception e) { result.put("MySQL","DOWN"); }
        try(var connection=Objects.requireNonNull(redis.getConnectionFactory()).getConnection()) { result.put("Redis","PONG".equals(connection.ping())?"UP":"DOWN"); } catch(Exception e) { result.put("Redis","DOWN"); }
        result.put("MinIO",storage.available()?"UP":"DOWN"); return result;
    }
}
