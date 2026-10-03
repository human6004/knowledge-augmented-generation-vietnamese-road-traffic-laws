package vn.luatgt.service;

import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class RateLimit {
    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script=new DefaultRedisScript<>("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",Long.class);
    public RateLimit(StringRedisTemplate redis) { this.redis=redis; }
    public void check(String key,int limit,int seconds) {
        Long count;
        try { count=redis.execute(script,List.of("rate:"+key),Integer.toString(seconds)); }
        catch(RuntimeException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Dịch vụ giới hạn truy cập chưa khả dụng"); }
        if(count==null) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Dịch vụ giới hạn truy cập chưa khả dụng");
        if(count>limit) throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS,"Vui lòng thử lại sau");
    }
}
