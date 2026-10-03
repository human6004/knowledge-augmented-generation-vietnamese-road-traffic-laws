package vn.luatgt.dto;
import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.*;
import java.util.UUID;
public record PenaltyRequest(@NotNull UUID documentId,@NotNull JsonNode data,@NotNull Boolean published,@Min(0) long version) {}
