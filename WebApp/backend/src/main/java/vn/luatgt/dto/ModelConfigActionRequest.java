package vn.luatgt.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record ModelConfigActionRequest(@NotNull @Min(0) @Max(2147483646) Integer revision) {}
