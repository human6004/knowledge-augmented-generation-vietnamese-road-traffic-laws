package vn.luatgt.config;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import jakarta.validation.constraints.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.*;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.*;
import vn.luatgt.model.Account;
import vn.luatgt.repository.AccountRepository;

@Configuration
public class SecurityConfig {
    @Bean BCryptPasswordEncoder passwords() { return new BCryptPasswordEncoder(12); }
    @Bean SecretKeySpec key(@Value("${app.jwt-secret}") String secret) {
        byte[] bytes = secret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) throw new IllegalStateException("JWT_SECRET phải có ít nhất 32 byte");
        return new SecretKeySpec(bytes, "HmacSHA256");
    }
    @Bean JwtEncoder encoder(SecretKeySpec key) { return new NimbusJwtEncoder(new ImmutableSecret<>(key)); }
    @Bean JwtDecoder decoder(SecretKeySpec key) {
        var decoder = NimbusJwtDecoder.withSecretKey(key).macAlgorithm(MacAlgorithm.HS256).build();
        decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer("luatgt"));
        return decoder;
    }
    @Bean SecurityFilterChain filter(HttpSecurity http, AccountRepository accounts) throws Exception {
        return http.csrf(c -> c.disable()).sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(a -> a.requestMatchers("/api/auth/register", "/api/auth/login", "/actuator/health").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN").anyRequest().authenticated())
            .oauth2ResourceServer(o -> o.jwt(j -> j.jwtAuthenticationConverter(jwt -> {
                Account account;
                try { account = accounts.findById(UUID.fromString(jwt.getSubject())).orElseThrow(); }
                catch (RuntimeException e) { throw new InvalidBearerTokenException("Tài khoản không hợp lệ"); }
                if (!account.enabled || !(jwt.getClaim("ver") instanceof Number ver) || ver.intValue() != account.tokenVersion)
                    throw new InvalidBearerTokenException("Phiên đăng nhập đã hết hiệu lực");
                return new JwtAuthenticationToken(jwt, List.of(new SimpleGrantedAuthority("ROLE_" + account.role)));
            }))).httpBasic(b -> b.disable()).formLogin(f -> f.disable()).build();
    }
    @Bean ApplicationRunner bootstrap(AccountRepository accounts, BCryptPasswordEncoder passwords,
          @Value("${app.admin-email}") String email, @Value("${app.admin-password}") String password) {
        return args -> {
            if (email.isBlank() && password.isBlank()) return;
            if (!email.matches("[^@\\s]+@[^@\\s]+\\.[^@\\s]+") || password.length() < 12 || password.getBytes(StandardCharsets.UTF_8).length > 72)
                throw new IllegalStateException("ADMIN_EMAIL hợp lệ và ADMIN_PASSWORD từ 12 ký tự, tối đa 72 byte");
            String normalized = email.trim().toLowerCase(Locale.ROOT);
            var existing = accounts.findByEmail(normalized);
            if (existing.isPresent()) {
                if (!existing.get().role.equals("ADMIN")) throw new IllegalStateException("Email bootstrap đã thuộc tài khoản USER");
                return;
            }
            var admin = new Account(); admin.email=normalized; admin.name="Quản trị viên";
            admin.password=passwords.encode(password); admin.role="ADMIN"; accounts.save(admin);
        };
    }
}

