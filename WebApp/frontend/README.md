# Frontend LuậtGT

React/TypeScript/Vite, giao diện kem/nâu theo App-design.zip và rule.md.

## Phát triển và kiểm thử

Từ thư mục gốc repository:

```powershell
cd WebApp/frontend
pnpm install --frozen-lockfile
pnpm dev --port 5174
pnpm test
node node_modules/typescript/bin/tsc --noEmit
pnpm build
```

Vite chuyển `/api` đến `http://127.0.0.1:8080`. Compose gốc build FE/Nginx ở `http://127.0.0.1:8081`, proxy đến backend trong mạng Docker; không cần cấu hình CORS hoặc token trong URL.

Các route sử dụng `src/pages/server/` và API thật: đăng nhập/đăng ký, biển báo, ôn tập/tiến độ, thi hạng B, tra cứu mức phạt, quản trị văn bản/câu hỏi/biển báo, nhập CSV/XLSX/JSON + ZIP ảnh, tài khoản, phản hồi, báo cáo và kiểm tra hạ tầng. Mã các trang demo từ ZIP còn lưu để tham khảo, không được nối vào App.tsx.

Tài khoản ADMIN lấy từ `.env`, người học tự đăng ký USER. JWT chỉ lưu sessionStorage, vai trò lấy từ `/auth/me`; mọi API có phân quyền server. Logout/401 xóa phiên và bài thi đang chọn. Không có tài khoản demo hoặc dữ liệu mẫu thay thế trong luồng đang chạy. Backend chưa chạy thì UI báo lỗi kết nối.

Nhập dữ liệu dùng chuẩn hóa client và preview/confirm server. JSON đáp án bắt đầu từ 0, CSV/XLSX cột answer dùng 1–4. PNG/JPEG qua ZIP theo mã, không nhận WebP/SVG. Nhập lưu nháp; câu hỏi chỉ xuất bản sau xác nhận kiểm duyệt đáp án/điểm liệt/ảnh. 600 câu và ZIP ảnh có tại docs/imports.

Chat đang dùng REST của backend; HTTP query adapter KAG chưa có thì không có câu trả lời giả. Backend đã có SSE, UI chưa hiển thị stream. Core Python đã có Builder, Retriever/Solver và evaluation; trang pipeline/graph/benchmark còn chờ management integration. Trang cấu hình KAG đã đọc schema identity/contract từ API thật. Trang hạ tầng chỉ kiểm tra MySQL/Redis/MinIO, không điều khiển Docker hoặc chứng minh KAG readiness. Xem [kiến trúc và gap HTTP](../../docs/architecture.md#hợp-đồng-http-và-chính-sách-tương-thích-đề-xuất).

Hướng dẫn chạy hệ thống, nhập dữ liệu và kiểm thử Docker thật: [README WebApp](../README.MD).

[App.tsx](src/App.tsx) là nguồn route hiện tại; [pages/server](src/pages/server/)
chứa trang hoạt động. [README thiết kế nhập từ ZIP](src/imports/README.md)
giữ ý tưởng/lộ trình lịch sử, không dùng làm hướng dẫn setup hiện tại.
