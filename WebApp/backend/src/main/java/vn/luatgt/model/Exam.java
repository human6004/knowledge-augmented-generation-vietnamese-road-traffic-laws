package vn.luatgt.model;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity @Table(name="exams")
public class Exam {
    @Id public UUID id = UUID.randomUUID();
    @Column(nullable=false) public UUID ownerId;
    @Column(nullable=false) public Instant startedAt;
    @Column(nullable=false) public Instant expiresAt;
    public Instant submittedAt;
    @Column(nullable=false, columnDefinition="longtext") public String snapshot;
    @Column(nullable=false, columnDefinition="longtext") public String answers = "{}";
    public Integer score;
    public Boolean criticalFailed;
    public Boolean passed;
}
