# Sử dụng LuậtGT

Mở **http://127.0.0.1:8081** trên máy chạy Docker. Cài đặt và điều kiện SAMPLE:
[INSTALL](INSTALL.md). Cập nhật giữ dữ liệu: [UPDATE](UPDATE.md).

## USER: đăng ký và đăng nhập

1. Trang `/login`: chọn **Chưa có tài khoản? Đăng ký**.
2. Nhập họ tên, email và mật khẩu từ 12 ký tự, tối đa 72 byte; chọn **Tạo tài khoản**.
   Tài khoản mới thuộc USER, không có quyền Admin.
3. Tài khoản đã có: chọn **Đã có tài khoản? Đăng nhập**, nhập email/mật khẩu,
   chọn **Đăng nhập**. USER vào `/chat`.

Form đăng ký có trong source; lượt nghiệm thu này dùng USER có sẵn, không tạo
tài khoản mới. Nếu đăng nhập lỗi, đọc thông báo trên form; không chia sẻ mật khẩu.

## USER: hỏi và đọc nguồn

- Trang **Trò chuyện với trợ lý** (`/chat`): nhập câu hỏi tiếng Việt vào
  **Câu hỏi luật giao thông**, chọn **Gửi** hoặc Enter; Shift+Enter xuống dòng.
  Giới hạn 4.000 ký tự. Trong lúc xử lý, không gửi lại cùng câu hỏi.
- **Đã trả lời**: mở phần câu trả lời để đọc toàn bộ. Nhãn trích nội dung nguồn
  không xác nhận hiệu lực hiện hành; SAMPLE không đủ căn cứ cho mọi vấn đề pháp lý.
- Mở **Nguồn …** để đọc quote. Chọn **Đối chiếu chi tiết nguồn**: UI đọc unit từ
  backend và kiểm quote, hiện số hiệu/loại unit; mở **Toàn văn đơn vị nguồn** khi cần.
  Quote khớp nguồn không tự chứng minh luật còn hiệu lực.
- Lịch sử nằm cùng trang, gồm câu hỏi, câu trả lời/citations và trạng thái từ backend.
  **Tải lại lịch sử** đọc lại dữ liệu đã lưu, không chạy lại câu hỏi.
- Các nút **Hữu ích**, **Phản hồi sai**, **Thiếu căn cứ**, **Hết hiệu lực** gửi
  phản hồi cho Admin. Chỉ dùng khi muốn ghi phản hồi; nghiệm thu không gửi thử.

WebApp phân biệt ba trạng thái và lưu nguyên trạng thái trong lịch sử:

- `ANSWERED`: câu trả lời và citations đã qua validation hiện có.
- `KAG_ABSTAINED`: native KAG xác nhận thiếu căn cứ qua response contract đã
  kiểm chứng, kể cả native HTTP 503. UI hiển thị: **Hiện tôi chưa tìm được đủ
  căn cứ pháp lý được xác minh để trả lời chính xác câu hỏi này.** Không có câu
  trả lời/citations và không tự gửi lại inference.
- `UNAVAILABLE`: provider, runtime, API hoặc response gặp lỗi/không kiểm chứng
  được. UI hiển thị: **Dịch vụ tra cứu pháp luật hiện đang gặp sự cố hoặc chưa
  sẵn sàng. Vui lòng thử lại sau.** Không có câu trả lời/citations. Lỗi xử lý 5xx
  đọc lại history một lần, không chạy lại câu hỏi.

REST trả record `KAG_ABSTAINED`; SSE kết thúc bằng `done` chứa record thiếu căn cứ,
khác `done` ANSWERED có đáp án. Runtime/API lỗi qua SSE phát `error` và history
giữ UNAVAILABLE. Reload đọc trạng thái đã lưu. Các record UNAVAILABLE cũ giữ
nguyên; không tự đổi chúng sang abstention dựa trên câu hỏi/thông báo cũ.
Chưa có reason ngoài phạm vi đáng tin cậy trong contract hiện tại: không suy từ
retrieval rỗng thành ngoài phạm vi, không tự tuyên bố đã phân loại câu hỏi.
Không xem chưa trả lời là đáp án hoặc kết luận luật không tồn tại.

Bản sửa ngày 12/10/2026 đã triển khai; REST/SSE/history abstention qua kiểm thử
integration offline. Nghiệm thu mới nhất xác nhận **LIVE_PASS native abstention**
qua React REST → Spring → UI/history/reload cho đúng một câu negative SAMPLE
PROVISIONAL, answer rỗng và citations `[]`. ANSWERED/citations và runtime UNAVAILABLE
có bằng chứng riêng; chưa kiểm live SSE abstention hoặc mọi câu negative.
Planner RuntimeError lịch sử chưa xác định nguyên nhân gốc; một lượt abstention
thành công không chứng minh lỗi đó đã được sửa vĩnh viễn.

USER truy cập `/admin/*` bị chuyển về trang USER; API Admin trả 403.
Các trang tra cứu mức phạt/biển báo/ôn thi/thi thử có routes, nhưng SAMPLE hiện
thiếu dữ liệu biển báo, câu hỏi và mức phạt; không suy trang mở được thành dữ
liệu nghiệp vụ đầy đủ.

## ADMIN: đọc trạng thái hiện có

Đăng nhập bằng tài khoản `ADMIN_EMAIL`/`ADMIN_PASSWORD` do người vận hành cấp;
không có đăng ký Admin công khai. ADMIN vào `/admin/dashboard`. Dùng menu
**Điều hướng quản trị** để chọn trang.

- **Tổng quan** (`/admin/dashboard`): số liệu tài khoản/nội dung/chat/bài thi,
  phần **Vận hành KAG SAMPLE** có liveness, Query/Retrieval/Vector readiness,
  graph counts và ledger provider. **Kiểm tra KAG** đọc trạng thái, không inference.
- **Đồ thị tri thức** (`/admin/graph`): đọc 32 nodes/22 cạnh/42 vectors SAMPLE,
  fingerprint, database/server identity. Tìm node theo mã/tên, chọn node để đọc
  thuộc tính, evidence hash và quan hệ; chọn **Mở …** để chuyển node liên quan.
  Trang chỉ đọc, không chỉnh graph hoặc chạy Cypher tùy ý.
- **Pipeline KAG** (`/admin/pipeline`): slot runtime, request đang xử lý/draining
  và receipt SAMPLE. Chưa có telemetry tiến độ Builder, batch progress hoặc thời
  gian build; không có nút thực thi pipeline.
- **Hạ tầng** (`/admin/docker`): kết nối MySQL/Redis/MinIO và KAG capabilities.
  Liveness ALIVE khác readiness READY; artifact-only không chứng minh serving.
  **Kiểm thử Retrieval** nằm ngay trang này, không có route riêng.
- **Kiểm thử Retrieval**: nhập **Nội dung truy xuất**, chọn 1–10 kết quả và tùy
  chọn **Mở rộng graph context**, chọn **Chạy thử truy xuất**. Hiện source texts,
  vector provenance, score và relation context. Đây là retriever, không chạy
  Solver hoặc cho kết luận pháp luật. Có thể tiêu thụ embedding provider/budget;
  chỉ chạy khi operator cho phép, credentials và readiness hợp lệ.
- **Benchmark** (`/admin/benchmark`): đọc catalog dataset, validation/gold coverage
  và execution artifacts có sẵn. Dataset 71 câu ban đầu không eligible cho SAMPLE;
  hai câu PROVISIONAL riêng có kết quả exploratory, chưa human review.
  Metrics lịch sử không là lượt benchmark vừa chạy. Không có chức năng chạy
  benchmark chính thức từ trang này.
- **Nhật ký chat & phản hồi** (`/admin/chatlogs`): đọc lịch sử/phản hồi cần xử lý.
  Thao tác xử lý phản hồi là ghi dữ liệu; không nhầm với kiểm tra KAG chỉ đọc.
- **Cấu hình KAG** (`/admin/config`): xem schema identity; không dùng để cấp
  serving authority, đổi model/proof hoặc mở production WRITE.

Trang có số 0/danh sách rỗng nghĩa là chưa có dữ liệu tương ứng. Pipeline/Graph/
Benchmark là màn hình inspection, không phải bộ điều khiển build/deployment.

## Khi hệ thống chưa trả lời

Admin kiểm Hạ tầng: dịch vụ WebApp kết nối được, KAG ALIVE, các capability READY,
release/graph/source tương thích. Trong query, `CONCURRENCY_LIMIT` có thể xuất
hiện; chờ query xong rồi kiểm lại trạng thái, không lặp inference.
Provider 403/timeout hoặc publication hết hạn cần người vận hành giải quyết;
không đổi model, sửa proof hoặc bỏ authentication để ép thành công.

SAMPLE chỉ là bộ dữ liệu nhỏ đã kiểm chứng nội dung/nguồn. Hai câu kiểm thử không
chứng minh độ chính xác pháp lý toàn corpus, benchmark chính thức hoặc production.
