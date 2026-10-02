package vn.luatgt.dto;
import jakarta.validation.constraints.*;
public record FeedbackRequest(@NotBlank @Pattern(regexp="HELPFUL|WRONG|NO_BASIS|OUTDATED") String feedback,@Size(max=1000) String note) {}
