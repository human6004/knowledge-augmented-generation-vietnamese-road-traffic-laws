package vn.luatgt.dto;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import jakarta.validation.constraints.*;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record LLMCredentialsChangeRequest(
    @JsonDeserialize(using=KagRetrieveRequest.IntegerValue.class)
    @NotNull @Min(0) @Max(2147483646) Integer revision,
    JsonNode chat, JsonNode embedding) {
    @Override public String toString() { return "LLMCredentialsChangeRequest[redacted]"; }
}
