# WebApp LuậtGT

React cung cấp giao diện USER/ADMIN; Spring Boot quản lý nghiệp vụ, dùng MySQL, Redis, MinIO và gọi KAG Python.

- [INSTALL](../docs/INSTALL.md): cài và đăng nhập.
- [USER-GUIDE](../docs/USER-GUIDE.md): thao tác, dữ liệu thật và Demo.
- [UPDATE](../docs/UPDATE.md), [Docker](../docker/README.md): vận hành và giữ dữ liệu.
- [Frontend](frontend/README.md), [backend](backend/README.md), [rule.md](rule.md): phát triển và quy tắc dự án.

## Dữ liệu và nghiệp vụ

[`docs/imports/`](docs/imports/) giữ ngân hàng câu hỏi nháp/ZIP ảnh/metadata nguồn. Nhập không tự xuất bản; kiểm đáp án, điểm liệt, ảnh và nguồn trước khi duyệt. Nội dung xuất bản WebApp không tự đồng bộ graph KAG.

Thi thật hạng B dùng server và đáp án đã duyệt; các giới hạn học/thi, chatbot và Builder nằm trong USER-GUIDE. Bản thiết kế [`App-design/`](App-design/src/imports/README.md) là tham chiếu, bộ deploy đi kèm không phải installation sản phẩm.

## Nhập ngân hàng bằng script

Lựa chọn thay cho nhập UI, sau khi stack đã chạy. Từ root repository:

**Bước 1:** chạy công cụ có sẵn để nhập nháp và ghép ảnh, bỏ qua mã đã tồn tại:

```powershell
./WebApp/scripts/import-question-bank.ps1 -EnvFile .env
```

Kết quả: số thêm/bỏ qua và ảnh ghép. Cổng khác mặc định truyền `-BaseUrl` đúng API; dùng credentials ADMIN hiện tại.

**Bước 2:** mở Ngân hàng câu hỏi, kiểm nguồn/đáp án/điểm liệt/ảnh rồi xuất bản câu thật đủ điều kiện.

`scripts/verify-stack.ps1` là kiểm thử tùy chọn, tạo tài khoản/lịch sử thử; `-WithExam` cần dữ liệu đã xuất bản. Scripts chuẩn hóa ngân hàng có thể ghi lại assets/nháp. Đọc source và chọn môi trường thử riêng trước khi chạy; không phải điều kiện startup.
