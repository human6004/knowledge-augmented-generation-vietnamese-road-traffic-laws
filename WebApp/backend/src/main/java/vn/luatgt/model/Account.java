package vn.luatgt.model;

import jakarta.persistence.*;
import java.util.UUID;

@Entity @Table(name="accounts")
public class Account {
    @Id public UUID id = UUID.randomUUID();
    @Column(nullable=false, unique=true, length=254) public String email;
    @Column(nullable=false, length=100) public String password;
    @Column(nullable=false, length=100) public String name;
    @Column(nullable=false, length=10) public String role = "USER";
    public boolean enabled = true;
    public int tokenVersion;
}
