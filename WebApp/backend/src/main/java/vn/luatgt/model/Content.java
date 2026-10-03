package vn.luatgt.model;

import jakarta.persistence.*;
import java.util.UUID;

@Entity @Table(name="content", uniqueConstraints=@UniqueConstraint(columnNames={"kind","external_id"}))
public class Content {
    @Id public UUID id = UUID.randomUUID();
    @Column(nullable=false, length=20) public String kind;
    @Column(nullable=false, name="external_id", length=250) public String externalId;
    @Column(nullable=false, columnDefinition="text") public String data;
    public boolean published;
    @Version public long version;
}
