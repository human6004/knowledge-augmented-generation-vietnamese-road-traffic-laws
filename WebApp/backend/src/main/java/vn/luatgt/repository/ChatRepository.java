package vn.luatgt.repository;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import vn.luatgt.model.ChatMessage;

public interface ChatRepository extends JpaRepository<ChatMessage,UUID> {
    List<ChatMessage> findTop50ByOwnerIdOrderByCreatedAtDesc(UUID owner);
    List<ChatMessage> findTop100ByOrderByCreatedAtDesc();
    @Query("select c from ChatMessage c where c.resolved=false and (c.state<>'ANSWERED' or (c.feedback is not null and c.feedback<>'HELPFUL')) order by c.createdAt desc")
    List<ChatMessage> pending(org.springframework.data.domain.Pageable page);
    @Query("select count(c) from ChatMessage c where c.resolved=false and (c.state<>'ANSWERED' or (c.feedback is not null and c.feedback<>'HELPFUL'))")
    long pendingCount();
}

