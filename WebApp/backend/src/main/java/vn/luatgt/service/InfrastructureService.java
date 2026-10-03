package vn.luatgt.service;
import vn.luatgt.integration.ObjectStorage;
import javax.sql.DataSource;
import java.util.*;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
@Service
public class InfrastructureService {
    private final DataSource database; private final StringRedisTemplate redis; private final ObjectStorage storage;
    public InfrastructureService(DataSource database,StringRedisTemplate redis,ObjectStorage storage) { this.database=database; this.redis=redis; this.storage=storage; }
    public Map<String,String> status() {
        var result=new LinkedHashMap<String,String>();
        try(var connection=database.getConnection()) { result.put("MySQL",connection.isValid(2)?"UP":"DOWN"); } catch(Exception e) { result.put("MySQL","DOWN"); }
        try(var connection=Objects.requireNonNull(redis.getConnectionFactory()).getConnection()) { result.put("Redis","PONG".equals(connection.ping())?"UP":"DOWN"); } catch(Exception e) { result.put("Redis","DOWN"); }
        result.put("MinIO",storage.available()?"UP":"DOWN"); return result;
    }
}
