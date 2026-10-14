package vn.luatgt.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.io.IOException;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record BuilderRunRequest(@JsonProperty("run_id") @NotBlank
    @JsonDeserialize(using=StringValue.class)
    @Pattern(regexp="[A-Za-z0-9][A-Za-z0-9._-]{0,127}") String runId) {
    public static class StringValue extends JsonDeserializer<String> {
        public String deserialize(JsonParser input,DeserializationContext context) throws IOException {
            if(input.currentToken()!=JsonToken.VALUE_STRING)throw JsonMappingException.from(input,"run_id cần chuỗi");
            return input.getText();
        }
    }
}
