package vn.luatgt.dto;

import jakarta.validation.constraints.*;

public record UserStatusRequest(@NotNull Boolean enabled) {}
