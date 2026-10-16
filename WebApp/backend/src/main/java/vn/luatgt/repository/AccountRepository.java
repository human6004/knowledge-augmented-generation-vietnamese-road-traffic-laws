package vn.luatgt.repository;

import java.util.*;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.*;
import vn.luatgt.model.Account;

public interface AccountRepository extends JpaRepository<Account,UUID> {
    Optional<Account> findByEmail(String email);
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = ?1")
    Optional<Account> findForUpdate(UUID id);
}
