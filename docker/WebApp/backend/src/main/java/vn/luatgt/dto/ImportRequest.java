package vn.luatgt.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.*;
import java.util.List;

public record ImportRequest(@NotEmpty @Size(max=5000) List<JsonNode> rows, boolean updateExisting) {}
