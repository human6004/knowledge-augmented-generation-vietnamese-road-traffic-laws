package vn.luatgt.service;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import vn.luatgt.dto.LoginRequest;
import vn.luatgt.dto.RegisterRequest;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.model.Account;
import vn.luatgt.repository.AccountRepository;

@Service

public class AuthService {
    private final AccountRepository accounts; private final BCryptPasswordEncoder passwords; private final JwtEncoder encoder; private final RateLimit rate;
    private final String dummyHash;
    AuthService(AccountRepository accounts, BCryptPasswordEncoder passwords, JwtEncoder encoder, RateLimit rate) {
        this.accounts=accounts; this.passwords=passwords; this.encoder=encoder; this.rate=rate;
        dummyHash=passwords.encode(UUID.randomUUID().toString());
    }
    public static UUID user(JwtAuthenticationToken auth) { return UUID.fromString(auth.getName()); }
    public static Map<String,Object> profile(Account a) { return Map.of("id",a.id,"email",a.email,"name",a.name,"role",a.role); }
    private Map<String,Object> session(Account a) {
        Instant now=Instant.now(), expiry=now.plusSeconds(3600);
        var claims=JwtClaimsSet.builder().issuer("luatgt").subject(a.id.toString()).issuedAt(now).expiresAt(expiry).claim("ver",a.tokenVersion).build();
        String token=encoder.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(),claims)).getTokenValue();
        return Map.of("accessToken",token,"expiresAt",expiry,"user",profile(a));
    }
    @Transactional
    public Map<String,Object> register(RegisterRequest input, String address) {
        rate.check("auth:"+address,10,60);
        if(input.password().getBytes(StandardCharsets.UTF_8).length>72) throw ApiErrors.bad("Mật khẩu tối đa 72 byte");
        String email=input.email().trim().toLowerCase(Locale.ROOT);
        if(accounts.findByEmail(email).isPresent()) throw new ResponseStatusException(HttpStatus.CONFLICT,"Email đã được sử dụng");
        var a=new Account(); a.email=email; a.name=input.name().trim(); a.password=passwords.encode(input.password());
        accounts.saveAndFlush(a); return session(a);
    }
    
    public Map<String,Object> login(LoginRequest input,String address) {
        rate.check("auth:"+address,10,60);
        var account=accounts.findByEmail(input.email().trim().toLowerCase(Locale.ROOT));
        boolean matches=passwords.matches(input.password(), account.map(a -> a.password).orElse(dummyHash));
        if(account.isEmpty() || !matches || !account.get().enabled) throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,"Email hoặc mật khẩu không đúng");
        return session(account.get());
    }
    public Map<String,Object> me(JwtAuthenticationToken auth) { return profile(accounts.findById(user(auth)).orElseThrow()); }
    @Transactional
    public void logout(JwtAuthenticationToken auth) { var a=accounts.findById(user(auth)).orElseThrow(); a.tokenVersion++; accounts.save(a); }
}
