package vn.luatgt.model;
import jakarta.persistence.*;
import java.util.UUID;
@Entity @Table(name="legal_units")
public class LegalUnit {
    @Id public UUID id=UUID.randomUUID();
    @Column(nullable=false) public UUID documentId;
    @Column(nullable=false,unique=true,length=500) public String unitId;
    @Column(nullable=false,columnDefinition="longtext") public String data;
    public boolean published;
    @Version public long version;
}
