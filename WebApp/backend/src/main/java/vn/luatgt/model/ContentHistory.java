package vn.luatgt.model;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;
@Entity @Table(name="content_history")
public class ContentHistory {
    @Id public UUID id=UUID.randomUUID();
    public UUID contentId;
    public long contentVersion;
    @Column(columnDefinition="longtext") public String data;
    public boolean published;
    public Instant changedAt=Instant.now();
}
