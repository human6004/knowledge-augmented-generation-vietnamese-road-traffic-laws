package vn.luatgt.repository;

import java.util.*;
import org.springframework.data.jpa.repository.*;
import vn.luatgt.model.StudyAttempt;

public interface StudyAttemptRepository extends JpaRepository<StudyAttempt,UUID> { List<StudyAttempt> findByOwnerId(UUID owner); }
