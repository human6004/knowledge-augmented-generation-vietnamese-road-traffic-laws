# Bối cảnh thiết kế runner và verification

Tài liệu giữ quyết định thiết kế lịch sử của runner và rehearsal SAMPLE.
Hướng dẫn vận hành hiện tại: [runner](../../runner.md),
[backend identity](../../backend-identity.md),
[writer scope](../../production-writer-scope.md). Thiết kế không chứng minh
deployment đã sẵn sàng hoặc cấp quyền graph/provider.

## Quyết định và phương án

Chọn JSONL streaming + SQLite ledger ngoài repo. SQLite có lookup/uniqueness,
transaction và outbox cho batch confirmation/resume; dùng lại checkpoint
ResilientVectorizer. Phương án receipt riêng từng batch cần tự quản lookup và
recovery nhiều file; không mang lại lợi ích đủ để thay SQLite đã có.

CLI dùng library chung; runner tái sử dụng mapping/codec/vectorizer/writer.
Rehearsal chỉ đọc exact existing state với vectors có sẵn, không sửa mismatch.
Node readback barrier trước edge và export hoàn chỉnh trước graph stages
giữ thao tác graph gắn với expected source.

## Streaming và bộ nhớ

Payload/vectors xử lý theo batch; identity/checkpoint/artifacts trên disk.
Batch boundaries bind run identity. O(batch) không chứng minh peak RSS hoặc
full production vector memory; source và vector cần kiểm chứng riêng.

## Resume và writer lock

SQLite là state authority; outbox và append-only hash chains bảo vệ confirmation
qua crash. CONFIRMED không resend; INTENT chưa confirmed cần exact readback,
không đoán remote completion sau timeout. Lock theo physical databaseID và
common storage để endpoint aliases cạnh tranh cùng lock. Chỉ owner release;
single-machine lock không phải distributed fencing.

Chi tiết state, verify, recovery và gate đã chuyển thành contract trong các
runbook hiện tại ở trên. Offline tests/design không thay live proof hoặc
benchmark pháp lý chính thức.
