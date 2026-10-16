package vn.luatgt.dto;

import jakarta.validation.constraints.*;

public record UserStatusRequest(Boolean enabled, @Pattern(regexp="USER|POLICE") String role) {}
