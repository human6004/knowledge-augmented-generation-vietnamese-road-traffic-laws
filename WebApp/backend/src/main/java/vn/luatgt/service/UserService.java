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
    public void update(UUID id,Boolean enabled,String role) {
        if(enabled==null&&role==null) throw ApiErrors.bad("Cần trạng thái hoặc vai trò người dùng");
        var a=accounts.findForUpdate(id).orElseThrow(ApiErrors::missing);
        if(a.role.equals("ADMIN")) throw ApiErrors.bad("Không thay đổi ADMIN qua API này");
        if(enabled!=null) a.enabled=enabled;
        if(role!=null) a.role=role;
        a.tokenVersion++; accounts.save(a);
    }
}
