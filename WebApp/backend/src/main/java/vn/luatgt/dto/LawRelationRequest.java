package vn.luatgt.dto;
import jakarta.validation.constraints.*;
import java.time.LocalDate;
import java.util.UUID;
public record LawRelationRequest(@NotNull UUID predecessor,@NotNull UUID successor,@NotBlank @Pattern(regexp="REPLACES|AMENDS") String type,@NotNull LocalDate effectiveDate,@NotBlank @Size(max=1000) String note,@Min(0) long version) {}
