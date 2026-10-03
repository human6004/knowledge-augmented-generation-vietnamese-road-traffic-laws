package vn.luatgt.repository;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import vn.luatgt.model.Content;

public interface ContentRepository extends JpaRepository<Content,UUID> {
    long countByKind(String kind);
    long countByKindAndPublishedTrue(String kind);
    @Lock(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE)
    @Query("select c from Content c where c.kind='documents' order by c.id")
    List<Content> lockDocuments();
    Optional<Content> findByKindAndExternalId(String kind, String externalId);
    List<Content> findByKindOrderByExternalId(String kind);
    List<Content> findByKindAndPublishedTrueOrderByExternalId(String kind);
}
