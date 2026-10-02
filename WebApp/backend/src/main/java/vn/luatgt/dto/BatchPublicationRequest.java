package vn.luatgt.dto;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.*;
public record BatchPublicationRequest(@NotEmpty @Size(max=600) List<@Valid Item> rows,@NotNull Boolean reviewed,@NotNull Boolean published) {
    public record Item(@NotNull UUID id,@Min(0) long version) {}
}
