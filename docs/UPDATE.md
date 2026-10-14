# Cập nhật LuậtGT, giữ dữ liệu

Chạy từ root repository, dùng project và `.env` của installation đang phục vụ. Cần thời gian bảo trì. Không tạo lại secrets, chép đè `.env`, dùng `down -v`, prune hoặc reset dữ liệu.

## Bước 1 — Chuẩn bị và sao lưu

```powershell
git status --short
docker compose ps -a
```

Git cho biết thay đổi local cần giữ; Compose cho biết installation hiện tại. Nếu source còn chỉnh sửa riêng, giải quyết chúng trước khi lấy phiên bản mới, không reset hay tự stash.

Thực hiện [sao lưu Docker](../docker/README.md#sao-lưu): dừng ghi/Builder, dừng toàn bộ services, sao lưu `.env`, Compose, state và **mọi volume đang mount**. Ghi lại phiên bản source/image và mapping volume → service/đường mount để có thể phục hồi đúng.

Kết quả: có bản sao ngoài repo và danh sách storage. **Chỉ tiếp tục khi sao lưu hoàn tất.** Installation còn hai projects cũ hoặc mapping khác source cần quy trình chuyển đổi riêng; không khởi động hai databases trên cùng volume.

## Bước 2 — Lấy phiên bản mới

Trên nhánh đang theo phiên bản cần cập nhật:

```powershell
git pull --ff-only
git submodule update --init vendor/KAG
```

Lệnh lấy source và KAG được phiên bản đó ghim. Nếu một lệnh lỗi hoặc nhánh phân kỳ, dừng xử lý; không force/reset hoặc dùng `submodule update --remote`.

## Bước 3 — Giữ cấu hình và storage

Mở `.env.example` mới để bổ sung biến cần thiết vào `.env` đang có. Giữ project, `KAG_STATE_DIR`, mọi mật khẩu/token và [biến mapping storage](../docker/README.md#storage-và-secrets). Đổi biến password không tự đổi password database/ADMIN.

Nếu release đổi Compose hoặc database image, đối chiếu tên volume **và đường mount từng service** với Bước 1; đọc hướng dẫn migration của release trước khi chạy. Không thay mapping bằng giá trị mặc định.

```powershell
docker compose config -q
```

Kết quả: cấu hình mới hợp lệ, không có lỗi. Lệnh này không chứng minh mapping hay migration tương thích; người vận hành vẫn cần đối chiếu storage. Không chia sẻ output đầy đủ của `compose config` vì có thể chứa secrets.

## Bước 4 — Chạy phiên bản mới

```powershell
docker compose up -d --build
docker compose ps -a
```

Lệnh build/recreate containers, dùng lại volumes đã giữ nguyên. Kết quả: 12 services khởi động, các healthcheck chuyển sang `healthy`. Nếu `up` lỗi, kiểm log trước khi tiếp tục; không dùng cờ đổi/xóa volume để xử lý.

## Bước 5 — Kiểm dữ liệu cũ

Mở WebApp tại cổng đang dùng, đăng nhập bằng tài khoản cũ. Kiểm nội dung đã xuất bản, ảnh/tệp, lịch sử chat/thi; ADMIN xem Hạ tầng, Graph SAMPLE và Builder theo [USER-GUIDE](USER-GUIDE.md#admin--kag-và-hạ-tầng).

Nếu chatbot đã chuẩn bị trước cập nhật, kiểm readiness và thử một câu trong phạm vi phục vụ; có thể phát sinh phí provider. Chatbot chưa cấu hình không được coi là sẵn sàng chỉ vì container healthy. Nếu nguồn/identity không khớp, kiểm [cấu hình chatbot](../docker/README.md#cấu-hình-chatbot), không sửa hash để ép READY.

Kết quả cần là dữ liệu cũ còn đọc được và chức năng đã cấu hình vẫn hoạt động. Giữ backup đến khi kiểm xong. Nếu cần phục hồi, dừng ghi và thử bản sao trên storage riêng; không import đè volume đang phục vụ. Hạ source/image không tự đảo ngược migration.

Quy trình giữ dữ liệu theo storage của Compose; **chưa xác minh cập nhật và phục hồi thực tế cho source hiện tại**.
