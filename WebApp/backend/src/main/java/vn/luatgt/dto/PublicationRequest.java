package vn.luatgt.dto;

import jakarta.validation.constraints.*;

public record PublicationRequest(@Min(0) long version,@NotNull Boolean published) {}
