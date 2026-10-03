package vn.luatgt.repository;
import vn.luatgt.model.LegalUnit;
import java.util.*;
import org.springframework.data.jpa.repository.JpaRepository;
public interface LegalUnitRepository extends JpaRepository<LegalUnit,UUID> {
    Optional<LegalUnit> findByUnitId(String unitId);
    List<LegalUnit> findByDocumentIdOrderByUnitId(UUID documentId);
}
