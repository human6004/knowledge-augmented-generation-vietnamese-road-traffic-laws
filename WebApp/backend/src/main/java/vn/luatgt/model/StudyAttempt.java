package vn.luatgt.model;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity @Table(name="study_attempts")
public class StudyAttempt {
    @Id public UUID id = UUID.randomUUID();
    public UUID ownerId;
    public UUID questionId;
    public int chapter;
    public boolean correct;
    public Instant createdAt = Instant.now();
}
