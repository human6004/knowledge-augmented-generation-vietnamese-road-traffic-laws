package vn.luatgt.service;

import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.luatgt.exception.ApiErrors;
import vn.luatgt.repository.AccountRepository;

@Service
public class UserService {
    private final AccountRepository accounts;
    public UserService(AccountRepository accounts) { this.accounts=accounts; }
    public List<Map<String,Object>> list() { return accounts.findAll().stream().map(a -> { var p=new LinkedHashMap<>(AuthService.profile(a)); p.put("enabled",a.enabled); return (Map<String,Object>)p; }).toList(); }
    @Transactional
    public void status(UUID id,boolean enabled) {
        var a=accounts.findById(id).orElseThrow(ApiErrors::missing);
        if(a.role.equals("ADMIN")) throw ApiErrors.bad("Không khóa ADMIN qua API này");
        a.enabled=enabled; a.tokenVersion++; accounts.save(a);
    }
}
