package vn.luatgt.model;
import jakarta.persistence.*;
import java.time.LocalDate;
import java.util.UUID;
@Entity @Table(name="law_relations")
public class LawRelation {
    @Id public UUID id=UUID.randomUUID();
    public UUID predecessor;
    public UUID successor;
    @Column(name="relation_type",length=20) public String type;
    public LocalDate effectiveDate;
    @Column(length=1000) public String note;
    @Version public long version;
}
