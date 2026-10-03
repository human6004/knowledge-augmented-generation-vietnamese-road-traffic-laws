package vn.luatgt.model;
import jakarta.persistence.*;
import java.util.UUID;
@Entity @Table(name="penalty_rules")
public class PenaltyRule {
    @Id public UUID id=UUID.randomUUID();
    public UUID documentId;
    @Column(columnDefinition="longtext") public String data;
    public boolean published;
    @Version public long version;
}
