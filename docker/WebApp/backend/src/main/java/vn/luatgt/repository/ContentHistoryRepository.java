package vn.luatgt.repository;
import vn.luatgt.model.ContentHistory;
import java.util.*;
import org.springframework.data.jpa.repository.JpaRepository;
public interface ContentHistoryRepository extends JpaRepository<ContentHistory,UUID> {
    List<ContentHistory> findByContentIdOrderByChangedAtDesc(UUID id);
}
