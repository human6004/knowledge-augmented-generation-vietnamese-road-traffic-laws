package vn.luatgt.repository;
import vn.luatgt.model.PenaltyRule;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
public interface PenaltyRepository extends JpaRepository<PenaltyRule,UUID> {}
