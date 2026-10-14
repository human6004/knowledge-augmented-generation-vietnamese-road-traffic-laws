# LuậtGT — Tra cứu luật giao thông và ôn thi lái xe

Ứng dụng web tiếng Việt để tra cứu luật có trích dẫn, tìm mức phạt, học biển báo và ôn thi lý thuyết. Quản trị viên nhập, kiểm duyệt và xuất bản nội dung.

## Tính năng

- **USER:** đăng ký/đăng nhập; hỏi luật, đọc nguồn và phản hồi; tra cứu mức phạt/biển báo; học theo chương, thi đề ngẫu nhiên hạng B và xem lịch sử.
- **ADMIN:** quản lý nội dung, tài khoản và phản hồi; xem KAG, graph SAMPLE, schema, Builder và dữ liệu đánh giá.

Một số phần giao diện còn ghi **Demo**, chỉ mô phỏng. Xem phạm vi từng chức năng trong [USER-GUIDE](docs/USER-GUIDE.md#phần-demo).

## Bắt đầu

1. [Cài đặt](docs/INSTALL.md): chuẩn bị Git, Docker, `.env` và token rồi khởi động.
2. Mở [WebApp](http://127.0.0.1:8081), đăng nhập ADMIN đã cấu hình hoặc đăng ký USER.
3. [Sử dụng](docs/USER-GUIDE.md); khi nâng phiên bản, làm theo [UPDATE](docs/UPDATE.md) để giữ dữ liệu.

Docker chạy **một project `luatgt`, 12 services, một `.env` chung**. Không cần cài Python/Java/Node trên máy người dùng.

**Cài mới không tự nạp nội dung, graph hoặc cấu hình mô hình.** Tra cứu/ôn thi cần dữ liệu đã duyệt; chatbot cần graph/vector, provider và bộ nguồn khớp nhau. Container `healthy` chưa chứng minh chatbot trả lời được. Builder mặc định bị chặn; chưa mở ghi graph production.

## Công nghệ

React/TypeScript; Spring Boot/Java; Python và OpenSPG KAG. MySQL lưu nghiệp vụ và metadata OpenSPG ở hai kho riêng; Neo4j lưu graph/vector; Redis giới hạn truy cập; MinIO lưu tệp/ảnh.

## Tài liệu bảo trì

- [Docker](docker/README.md), [WebApp](WebApp/README.MD), [frontend](WebApp/frontend/README.md), [backend](WebApp/backend/README.md).
- [Kiến trúc](docs/architecture.md), [runtime](docs/runtime.md), [runner](docs/runner.md), [backend identity](docs/backend-identity.md).
- [Mô hình miền](docs/domain_model.md), [schema](docs/schema.md), [retrieval](docs/retrieval-demo.md).
- [Dữ liệu](data/README.md), [datasheet](data/DATASHEET.md), [điều kiện sử dụng](data/LICENSE.md).
- [Benchmark](benchmark/README.md), [tests](tests/README.md): phục vụ phát triển, không phải bước khởi động.

## Giới hạn sử dụng

Không thay thế văn bản chính thức hoặc tư vấn pháp lý. Nội dung trích tự động cần kiểm duyệt; trích dẫn khớp nguồn không tự xác nhận hiệu lực. Không tìm được kết quả không có nghĩa không có quy định. Graph SAMPLE có phạm vi giới hạn; benchmark chính thức chưa hoàn thành.
