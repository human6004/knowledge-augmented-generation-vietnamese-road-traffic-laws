# Quy tắc làm việc cho AI Agent — LuậtGT KAG

> Áp dụng cho mọi task trong repository. Đây là quy tắc phát triển phần mềm, **không phải** checklist nghiệm thu hoặc điều kiện khởi động ứng dụng.

## 1. Mục tiêu sản phẩm

Xây dựng và duy trì phần mềm tra cứu luật giao thông đường bộ Việt Nam bằng KAG/OpenSPG và WebApp. Người dùng cần **cài đặt, cập nhật, đăng nhập và hỏi luật** một cách thông thường; không phải hiểu các bước thử nghiệm nội bộ.

Giữ kiến trúc KAG upstream đang pin và chỉ tùy chỉnh cần thiết cho tiếng Việt, pháp luật, dữ liệu và giao diện. Không tự tái thiết kế framework.

## 2. Không overengineering

- Chỉ thực hiện đúng yêu cầu của task. Không tự phát triển tính năng tương lai, mở rộng phạm vi, hay tạo roadmap/audit mới nếu chưa được yêu cầu.
- **Ưu tiên sửa hoặc tái sử dụng code hiện có.** Trước khi tạo module, class, wrapper, adapter, config, endpoint hoặc script mới, tìm chức năng tương đương trong project và upstream.
- Chỉ tạo thành phần mới khi có nhu cầu chức năng cụ thể mà code hiện có không giải quyết hợp lý. Tránh các lớp trung gian chỉ chuyển tiếp dữ liệu, logic trùng lặp, cấu hình trùng lặp và abstraction cho một trường hợp duy nhất.
- Dùng khả năng chuẩn của Docker Compose, Spring Boot, FastAPI, KAG/OpenSPG trước khi tự xây giải pháp thay thế. Khi cần đối chiếu, ưu tiên tài liệu chính thức và **đúng phiên bản đang sử dụng**.
- Không thêm proof, receipt, hash, gate, lock, allowlist hay checker mới chỉ để chứng minh một lần kiểm thử đã PASS. Giữ các cơ chế thực sự bảo vệ dữ liệu và quyền truy cập.
- Không hardcode IP/container ID động, đường dẫn riêng của máy phát triển, tên SAMPLE hoặc kích thước graph nghiệm thu vào đường chạy chung, trừ khi đang triển khai rõ ràng một chế độ SAMPLE biệt lập.
- Nếu cách sửa yêu cầu thêm nhiều file hoặc nhiều tầng kiểm tra, hãy tìm phương án đơn giản hơn trước; nếu vẫn bắt buộc, giải thích ngắn gọn cho chủ dự án.

## 3. Ranh giới source và workspace

**Repository chính:** chứa source ứng dụng, cấu hình cần thiết, tài liệu sản phẩm và những tests chính thức đã tồn tại.

**Workspace ngoài repo trên máy hiện tại:** `D:\study\caoDATA-workspace` (máy khác dùng một thư mục ngoài repo tương đương).

- Mọi **test tạm, fixture tạm, logs, trace, debug dump, benchmark output, audit, report, backup, export, file sinh khi chạy thử** phải được tạo trong workspace ngoài repo. Không tạo chúng bên trong repository, kể cả file đã được `.gitignore`.
- Được chạy/tái sử dụng bộ tests chính thức đang có. **Không tự thêm file test mới vào repository**; nếu cần kiểm chứng mới, tạo kiểm thử tạm trong workspace. Chỉ thêm test lâu dài khi được yêu cầu hoặc chủ dự án duyệt rõ.
- Không tự tạo script kiểm tra/triển khai/helper, tài liệu kế hoạch hoặc thư mục artifacts mới trong repo chỉ để tiện một task. Nếu là thành phần cần thiết cho sản phẩm, nêu lý do trước.
- Không xóa các tests, assets, migrations hoặc dữ liệu được code sử dụng chỉ vì tên file cũ hay số lượng file nhiều.
- Không đưa các đường dẫn workspace máy hiện tại thành dependency của sản phẩm.

## 4. Vận hành phải đơn giản

- Quy trình người dùng: cấu hình cần thiết → `docker compose up` → mở WebApp. Quy trình cập nhật: backup phù hợp → lấy phiên bản mới → cập nhật Compose → giữ nguyên dữ liệu.
- Không yêu cầu chạy benchmark, regression, checker, receipt hoặc proof lịch sử trước mỗi lần startup/update thông thường.
- Dùng tên service Docker/DNS cho kết nối; IP/container ID động không phải định danh ổn định. Tách health/liveness khỏi khả năng thực sự trả lời luật.
- Không tự thay đổi Compose project, volumes, networks, credentials, image pins hoặc database schema khi task không liên quan.

## 5. Những bảo vệ bắt buộc phải giữ

- Authentication, authorization, quản lý secrets/token và network isolation cần thiết.
- Đúng phiên bản nguồn và cấu trúc pháp luật; kiểm căn cứ, hiệu lực/phạm vi áp dụng, trích dẫn chính xác; thiếu căn cứ thì abstain, lỗi dịch vụ thì unavailable.
- Giữ nguồn/corpus provenance, database identity, chống ghi nhầm hoặc ghi đồng thời, giới hạn chi phí provider.
- Không bỏ một safety gate chỉ vì nó gây phiền: nếu nghi ngờ overengineering, xác định nguy cơ và cách thay thế an toàn trước khi sửa.
- Không được xóa/ghi đè graph, embeddings, dữ liệu MySQL/Redis/MinIO, người dùng hoặc lịch sử chat; không chạy `down -v`, prune hay reset dữ liệu.

## 6. Quyền hành động
.
- Giữ các thay đổi local có sẵn; không sửa file ngoài phạm vi. Nếu phát hiện task có rủi ro dữ liệu, phá tương thích hoặc đòi hỏi mở rộng lớn, báo ngắn gọn và hỏi trước.
## 7. Cách thực hiện và báo cáo

1. Đọc yêu cầu và đúng phần code liên quan; tìm callers/dependencies thực tế. Không bắt đầu bằng một đợt audit toàn repo nếu task nhỏ.
2. Nêu giải pháp **đơn giản nhất**, ưu tiên sửa tại chỗ; triển khai tối thiểu đúng phạm vi.
3. Chạy kiểm tra mục tiêu cần thiết bằng công cụ/tests có sẵn; logs nằm ngoài repo. Không tự chạy toàn bộ suite nếu không cần.
4. Kết thúc bằng câu trả lời ngắn: **đã sửa gì, vì sao, kiểm tra gì, còn hạn chế gì**. Không tự sinh thêm report Markdown trừ khi task yêu cầu.

**Quy tắc cuối:** Phần mềm phải đơn giản hơn sau mỗi thay đổi, hoặc ít nhất không phức tạp hơn một cách không có lý do. Nếu không chứng minh được giá trị của code/cơ chế mới, đừng thêm nó.
