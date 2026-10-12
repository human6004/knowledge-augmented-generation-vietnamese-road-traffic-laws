# KAG luật giao thông đường bộ Việt Nam

Dự án xây dựng ứng dụng tra cứu luật giao thông và trả lời câu hỏi có căn cứ từ văn bản pháp luật, đơn vị nội dung và biển báo. LuậtGT là giao diện web; hệ thống KAG phía sau tổ chức dữ liệu thành đồ thị tri thức, tìm nguồn liên quan và kiểm tra căn cứ trước khi trả lời.

## Tính năng

- Hỏi chatbot, đọc trích dẫn và đối chiếu với nội dung nguồn.
- Tra cứu văn bản, biển báo và mức phạt đã được quản trị viên kiểm duyệt.
- Ôn tập, thi thử hạng B và xem lịch sử.
- Quản lý nội dung, đơn vị pháp lý, tài khoản và phản hồi qua trang ADMIN.
- Xây dựng đồ thị tri thức; truy hồi theo vector và quan hệ pháp lý.
- Tạo, kiểm tra và quản lý bộ câu hỏi đánh giá; đo truy hồi và câu trả lời qua API Python.

Khi thiếu căn cứ, chatbot thông báo chưa thể trả lời. Kết quả trích nội dung văn bản không tự xác nhận quy định còn hiệu lực. Ứng dụng hỗ trợ tra cứu, không thay thế văn bản chính thức hoặc tư vấn pháp lý.

## Công nghệ

React và TypeScript cung cấp giao diện. Spring Boot xử lý tài khoản, nội dung, ôn thi và tích hợp chatbot. Python kết hợp OpenSPG KAG với các bộ truy hồi và kiểm tra căn cứ pháp lý của dự án. Neo4j lưu đồ thị cùng vector; MySQL lưu dữ liệu nghiệp vụ. Redis hỗ trợ giới hạn truy cập, MinIO lưu tệp và ảnh.

Xem [kiến trúc](docs/architecture.md) để hiểu luồng dữ liệu và trách nhiệm từng thành phần.

## Bắt đầu

Mã nguồn chính nằm trên nhánh `main`. Repository chứa ứng dụng, schema, dữ liệu nguồn, cấu hình mẫu và định nghĩa Docker. Để phục vụ chatbot, người vận hành còn cần chuẩn bị cấu hình dịch vụ mô hình, secrets, dữ liệu graph và bộ tệp xác minh phục vụ ngoài Git.

1. Làm theo [hướng dẫn cài đặt](docs/INSTALL.md).
2. Đọc [hướng dẫn sử dụng](docs/USER-GUIDE.md) cho USER và ADMIN.
3. Khi nâng cấp, dùng [hướng dẫn cập nhật](docs/UPDATE.md) để giữ dữ liệu.

Hệ thống hỗ trợ vận hành với graph SAMPLE có phạm vi giới hạn. Ghi graph production vẫn bị khóa trong runtime; bộ câu hỏi benchmark chính thức chưa hoàn thành. Có đủ mã nguồn không đồng nghĩa đã có graph đầy đủ hoặc dịch vụ sẵn sàng.

## Cấu trúc repository

```text
kag/         Core Python: builder, retriever, solver, evaluation và HTTP API
WebApp/      Frontend React, backend Spring Boot và công cụ nhập nội dung
data/        Nguồn pháp luật, dữ liệu xử lý và dữ liệu đánh giá
docker/      Images và công cụ vận hành hạ tầng
tests/       Kiểm thử Python theo thành phần
benchmark/   Hướng dẫn đánh giá và thư mục làm việc
docs/        Hướng dẫn sử dụng, cài đặt và tài liệu kỹ thuật
vendor/KAG/  OpenSPG KAG dưới dạng Git submodule
```

Hai file Compose tại root triển khai hạ tầng KAG và WebApp riêng. Code ứng dụng nằm ngoài vendor; các lệnh runtime và đánh giá được cung cấp trực tiếp qua package `kag`.

## Dữ liệu và đánh giá

Dữ liệu graph gồm văn bản pháp luật, các đơn vị nội dung và biển báo. Dữ liệu đánh giá được quản lý riêng, không đưa vào nguồn truy hồi. Xem [mô tả dữ liệu](data/README.md), [datasheet](data/DATASHEET.md) và [điều kiện sử dụng](data/LICENSE.md).

Framework đánh giá có G1 cho truy hồi và G2 cho câu trả lời, trích dẫn, khả năng từ chối trả lời. Bộ câu hỏi thử nghiệm và kết quả SAMPLE không phải benchmark chính thức. Quy trình chuẩn bị dataset, điều kiện đánh giá và API nằm trong [hướng dẫn benchmark](benchmark/README.md).

## Phát triển

- [WebApp](WebApp/README.MD), [frontend](WebApp/frontend/README.md), [backend](WebApp/backend/README.md): phát triển và kiểm thử ứng dụng.
- [Runtime Python](docs/runtime.md): phiên bản phụ thuộc, submodule và khởi tạo SDK.
- [Kiểm thử Python](tests/README.md): cách chạy từng nhóm kiểm thử và chuẩn bị fixtures.
- [Docker](docker/README.md): services, mạng, cổng và cấu hình vận hành.

Sau khi chuẩn bị [runtime Python](docs/runtime.md), từ root repository có thể xem các lệnh được hỗ trợ:

```sh
python -B -m kag --help
python -B -m kag.evaluation --help
```

## Tài liệu kỹ thuật

- [Kiến trúc](docs/architecture.md): thành phần, luồng câu hỏi và hợp đồng HTTP.
- [Mô hình miền](docs/domain_model.md) và [schema](docs/schema.md): định danh, thuộc tính và quan hệ pháp lý.
- [Builder và runner](docs/runner.md): cấu hình, chạy, tiếp tục và xác minh.
- [Backend identity](docs/backend-identity.md) và [phạm vi ghi graph](docs/production-writer-scope.md): điều kiện truy cập và bảo vệ dữ liệu.
- [Retrieval](docs/retrieval-demo.md): tìm nguồn, xếp hạng và chuẩn bị tập kiểm tra.
