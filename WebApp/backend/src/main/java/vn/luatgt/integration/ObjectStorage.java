package vn.luatgt.integration;

import io.minio.*;
import java.io.*;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class ObjectStorage {
    private final MinioClient client;
    private final String bucket;
    public ObjectStorage(@Value("${app.minio-url}") String url,@Value("${app.minio-user}") String user,
                         @Value("${app.minio-password}") String password,@Value("${app.bucket}") String bucket) {
        this.client=MinioClient.builder().endpoint(url).credentials(user,password).build(); this.client.setTimeout(2000,10000,10000); this.bucket=bucket;
    }
    public boolean available() { try { client.bucketExists(BucketExistsArgs.builder().bucket(bucket).build()); return true; } catch(Exception e) { return false; } }
    public String put(byte[] bytes,String mime) {
        String key=UUID.randomUUID().toString();
        try {
            if(!client.bucketExists(BucketExistsArgs.builder().bucket(bucket).build())) {
                try { client.makeBucket(MakeBucketArgs.builder().bucket(bucket).build()); }
                catch(Exception race) { if(!client.bucketExists(BucketExistsArgs.builder().bucket(bucket).build())) throw race; }
            }
            client.putObject(PutObjectArgs.builder().bucket(bucket).object(key).contentType(mime).stream(new ByteArrayInputStream(bytes),bytes.length,-1).build());
            return key;
        } catch(Exception e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Kho tệp chưa khả dụng"); }
    }
    public byte[] get(String key) {
        try(var stream=client.getObject(GetObjectArgs.builder().bucket(bucket).object(key).build())) {
            byte[] bytes=stream.readNBytes(20*1024*1024+1);
            if(bytes.length>20*1024*1024) throw new IOException("Oversized object");
            return bytes;
        } catch(Exception e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,"Không thể tải tệp nguồn"); }
    }
}
