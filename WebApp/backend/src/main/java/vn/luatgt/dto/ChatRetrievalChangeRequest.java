package vn.luatgt.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import jakarta.validation.constraints.*;

public record ChatRetrievalChangeRequest(
    @JsonDeserialize(using=KagRetrieveRequest.IntegerValue.class) @NotNull @Min(0) @Max(2147483646) Integer revision,
    JsonNode values) {}
