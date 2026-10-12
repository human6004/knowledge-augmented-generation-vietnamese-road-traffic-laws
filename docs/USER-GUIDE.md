# Sử dụng LuậtGT

Mở [LuậtGT](http://127.0.0.1:8081) trên máy chạy Docker.
[Cài đặt](INSTALL.md) và [cập nhật](UPDATE.md) dành cho người vận hành.
Chatbot hoạt động khi dịch vụ KAG sẵn sàng và dữ liệu nguồn đã được xuất bản.

## USER: đăng ký và đăng nhập

1. Trang `/login`: chọn **Chưa có tài khoản? Đăng ký**.
2. Nhập họ tên, email và mật khẩu từ 12 ký tự, tối đa 72 byte; chọn **Tạo tài khoản**.
   Tài khoản mới thuộc USER, không có quyền Admin.
3. Đã có tài khoản: chọn **Đã có tài khoản? Đăng nhập**, nhập email/mật khẩu và
   chọn **Đăng nhập**. USER vào `/chat`.

Thông báo lỗi hiển thị trên form. Phiên hết hạn thì đăng nhập lại.
Menu tài khoản có chức năng đăng xuất. Không chia sẻ mật khẩu hoặc token.

## USER: hỏi và đọc nguồn

Trang **Tra cứu luật** (`/chat`):

1. Nhập câu hỏi tiếng Việt vào **Câu hỏi luật giao thông**, tối đa 4.000 ký tự.
   Chọn **Gửi** hoặc Enter; Shift+Enter xuống dòng.
2. Chờ backend xử lý. **Dừng chờ** chỉ dừng chờ ở trình duyệt; backend có thể
   còn xử lý. Đọc lại lịch sử trước khi gửi lại câu hỏi.
3. Khi **Đã trả lời**, đọc câu trả lời; mở toàn bộ nếu nội dung dài.
4. Mở **Nguồn …** để đọc trích đoạn. Chọn **Đối chiếu chi tiết nguồn** để đọc
   số hiệu văn bản, loại đơn vị và kiểm trích đoạn với nội dung backend.
   **Toàn văn đơn vị nguồn** mở nội dung đầy đủ của unit.
5. Nếu cần, chọn **Hữu ích**, **Phản hồi sai**, **Thiếu căn cứ** hoặc **Hết hiệu lực**
   để gửi phản hồi cho Admin.

Trích đoạn khớp nguồn không tự xác nhận hiệu lực pháp luật hiện hành.
Câu trả lời có nhãn **Trích nội dung văn bản — không xác nhận hiệu lực hiện hành**
chỉ cung cấp nội dung nguồn. Chat hiện hiển thị căn cứ từ đơn vị văn bản đã
xuất bản; một số kết quả về thông tin văn bản hoặc biển báo chưa được hỗ trợ.

## Trạng thái trả lời và lịch sử

Lịch sử nằm cùng trang; **Tải lại lịch sử** đọc bản ghi đã lưu, không chạy lại
câu hỏi. Mỗi bản ghi có trạng thái để phân biệt:

- **Đang xử lý**: chưa có câu trả lời.
- **Đã trả lời**: đọc câu trả lời và trích dẫn bên dưới.
- **Chưa đủ căn cứ**: hệ thống hiển thị
  **Hiện tôi chưa tìm được đủ căn cứ pháp lý được xác minh để trả lời chính xác
  câu hỏi này.** Không có câu trả lời hoặc trích dẫn.
- **Dịch vụ chưa sẵn sàng**: hệ thống hiển thị **Dịch vụ tra cứu pháp luật hiện
  đang gặp sự cố hoặc chưa sẵn sàng. Vui lòng thử lại sau.** Đợi dịch vụ phục hồi
  hoặc báo người quản trị; không có câu trả lời hoặc trích dẫn.

Ứng dụng không tự gửi lại câu hỏi khi lỗi. Lịch sử giữ trạng thái đã lưu;
không tự đổi bản ghi lỗi cũ thành thiếu căn cứ.

Thiếu căn cứ không có nghĩa luật không tồn tại hoặc câu hỏi đã được xác định
ngoài phạm vi. SAMPLE không bao phủ mọi vấn đề pháp luật giao thông.

## USER: các trang khác

- **Tra cứu mức phạt** (`/tra-cuu`): tìm quy tắc phạt và căn cứ đã xuất bản.
- **Biển báo** (`/bien-bao`): đọc biển báo và nội dung đã xuất bản.
- **Ôn thi** (`/on-thi`, `/tien-do`): trả lời câu hỏi, xem giải thích và tiến độ học.
- **Thi thử** (`/exam`): tạo bài thi, lưu đáp án, nộp bài và mở lịch sử thi.

Các trang này phụ thuộc dữ liệu được Admin duyệt và xuất bản. Danh sách rỗng
hoặc chưa đủ câu hỏi nghĩa là dữ liệu hiện chưa đáp ứng tính năng tương ứng.

## ADMIN: quản lý dữ liệu WebApp

Đăng nhập bằng tài khoản ADMIN do người vận hành cấp; không có đăng ký Admin
công khai. ADMIN vào `/admin/dashboard`. Chọn trang ở menu bên trái hoặc
**Điều hướng quản trị** trên màn hình nhỏ.

- **Văn bản pháp luật**, **Đơn vị pháp lý**, **Ngân hàng câu hỏi**, **Biển báo**:
  tạo/sửa bản nháp, duyệt và xuất bản hoặc ngừng xuất bản. Kiểm nguồn trước khi
  xác nhận đã đối chiếu. Văn bản có tệp PDF nguồn; câu hỏi/biển báo có ảnh nguồn.
- **Nhập dữ liệu hàng loạt**: chọn loại dữ liệu, xem trước và xác nhận nhập.
  Kiểm mã nguồn và lựa chọn cập nhật bản ghi đã có trước khi ghi.
- **Mức phạt**: quản lý quy tắc phạt gắn với văn bản và unit làm căn cứ.
- **Nhật ký chat & phản hồi**: xem lịch sử, phản hồi và xử lý phản hồi cần duyệt.
- **Người dùng**: xem tài khoản, bật hoặc khóa tài khoản.

Những thao tác này ghi dữ liệu WebApp. Xuất bản nội dung WebApp không tự cập nhật
graph, release hoặc serving proof KAG. Nội dung dùng cho citations phải khớp bộ
nguồn/publication của release đang phục vụ.

## ADMIN: kiểm tra KAG

- **Tổng quan** (`/admin/dashboard`): số liệu nghiệp vụ và **Vận hành KAG SAMPLE**,
  gồm liveness, Query/Retrieval/Vector readiness, graph và ledger provider.
  **Kiểm tra KAG** không chạy inference.
- **Đồ thị tri thức** (`/admin/graph`): đọc graph SAMPLE, fingerprint, database/
  server identity. Tìm node theo mã/tên, đọc thuộc tính, evidence hash và quan hệ;
  chọn **Mở …** để chuyển node liên quan. Trang chỉ đọc.
- **Pipeline KAG** (`/admin/pipeline`): đọc slot runtime, request đang xử lý,
  draining và receipt SAMPLE. Chưa có telemetry tiến độ Builder hoặc nút chạy
  pipeline.
- **Hạ tầng** (`/admin/docker`): kiểm MySQL/Redis/MinIO và KAG capabilities.
  Liveness ALIVE khác readiness READY; release artifact không chứng minh serving.
- **Kiểm thử Retrieval**, ngay trong Hạ tầng: nhập **Nội dung truy xuất**, chọn
  1–10 kết quả, tùy chọn **Mở rộng graph context**, rồi **Chạy thử truy xuất**.
  Kết quả gồm source texts, score, vector provenance và relation context.
  Thao tác có thể tiêu thụ embedding provider/budget; chỉ chạy trong phạm vi được
  cấp. Retriever không đưa ra kết luận pháp luật.
- **Benchmark** (`/admin/benchmark`): đọc catalog dataset, validation/gold coverage
  và execution artifacts hợp lệ đã có. Metrics chưa đo giữ trống/null.
  Trang không khởi chạy benchmark chính thức.
- **Cấu hình KAG** (`/admin/config`): xem schema identity, thuộc tính/quan hệ và
  tải contract. Trang không đổi model/proof hoặc cấp quyền serving/production WRITE.

Pipeline, Graph và Benchmark là màn hình inspection. Phạm vi SAMPLE không chứng
minh graph toàn corpus, chất lượng benchmark chính thức hoặc production readiness.
Production WRITE giữ `BLOCKED`.

## Khi chưa có câu trả lời

Đọc thông báo UI và history trước gửi lại. Nếu phiên hết hạn, đăng nhập lại.
Nếu KAG đang bận, đợi request hiện tại kết thúc.

Admin mở Hạ tầng/Tổng quan để kiểm kết nối và khả năng phục vụ chatbot.
Lỗi dịch vụ hoặc cấu hình cần báo người vận hành xử lý theo
[hướng dẫn Docker](../docker/README.md).
