package vn.luatgt.model;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity @Table(name="chat_messages")
public class ChatMessage {
    @Id public UUID id = UUID.randomUUID();
    public UUID ownerId;
    @Column(columnDefinition="longtext") public String question;
    @Column(columnDefinition="longtext") public String answer;
    @Column(columnDefinition="longtext") public String citations = "[]";
    public String state;
    public String feedback;
    @Column(length=1000) public String feedbackNote;
    public boolean resolved;
    @Column(length=1000) public String resolution;
    public Instant createdAt = Instant.now();
}

