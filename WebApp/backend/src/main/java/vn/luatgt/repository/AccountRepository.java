package vn.luatgt.repository;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import vn.luatgt.model.Account;

public interface AccountRepository extends JpaRepository<Account,UUID> { Optional<Account> findByEmail(String email); }
