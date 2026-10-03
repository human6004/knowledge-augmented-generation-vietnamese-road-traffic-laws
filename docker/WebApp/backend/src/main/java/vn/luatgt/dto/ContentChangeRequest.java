package vn.luatgt.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.*;

public record ContentChangeRequest(@Min(0) long version,@NotNull JsonNode data) {}
