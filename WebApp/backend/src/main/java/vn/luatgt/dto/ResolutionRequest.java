package vn.luatgt.dto;
import jakarta.validation.constraints.*;
public record ResolutionRequest(@NotBlank @Size(max=1000) String note) {}
