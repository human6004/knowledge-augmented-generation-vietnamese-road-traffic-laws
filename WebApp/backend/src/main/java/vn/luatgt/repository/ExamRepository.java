package vn.luatgt.repository;

import jakarta.persistence.LockModeType;
import java.util.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;
import vn.luatgt.model.Exam;

public interface ExamRepository extends JpaRepository<Exam,UUID> {
    long countByPassedTrue();
    @Lock(LockModeType.PESSIMISTIC_WRITE) @Query("select e from Exam e where e.id=:id and e.ownerId=:owner")
    Optional<Exam> owned(@Param("id") UUID id, @Param("owner") UUID owner);
    List<Exam> findTop20ByOwnerIdOrderByStartedAtDesc(UUID owner);
}
