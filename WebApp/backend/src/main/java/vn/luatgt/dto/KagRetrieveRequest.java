package vn.luatgt.dto;

import jakarta.validation.constraints.*;
import com.fasterxml.jackson.core.*;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import java.io.IOException;

public record KagRetrieveRequest(@NotBlank @Size(max=4000) String message,
    @JsonDeserialize(using=IntegerValue.class) @NotNull @Min(1) @Max(10) Integer top_k,
    @JsonDeserialize(using=BooleanValue.class) @NotNull Boolean expand) {
    public static class IntegerValue extends JsonDeserializer<Integer> {
        public Integer deserialize(JsonParser input,DeserializationContext context) throws IOException {
            if(input.currentToken()!=JsonToken.VALUE_NUMBER_INT) throw JsonMappingException.from(input,"top_k cần số nguyên");
            return input.getIntValue();
        }
    }
    public static class BooleanValue extends JsonDeserializer<Boolean> {
        public Boolean deserialize(JsonParser input,DeserializationContext context) throws IOException {
            if(input.currentToken()!=JsonToken.VALUE_TRUE&&input.currentToken()!=JsonToken.VALUE_FALSE) throw JsonMappingException.from(input,"expand cần boolean");
            return input.getBooleanValue();
        }
    }
}
