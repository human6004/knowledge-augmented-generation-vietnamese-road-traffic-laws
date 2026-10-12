# Frontend LuậtGT

React/TypeScript/Vite/Tailwind. Giao diện người dùng và quản trị gọi API Spring Boot. Quy tắc thiết kế: [rule.md](../rule.md).

## Phát triển và kiểm thử

Dùng Node 24 và pnpm 10.11.0 như [Dockerfile](../../docker/frontend/Dockerfile). Từ `WebApp/frontend/`:

```powershell
pnpm install --frozen-lockfile
pnpm dev --port 5174
pnpm test
node node_modules/typescript/bin/tsc --noEmit
pnpm build
```

Vite chuyển `/api` đến `http://127.0.0.1:8080`. Docker/Nginx phục vụ UI ở `http://127.0.0.1:8081`; hướng dẫn stack và nhập dữ liệu tại [WebApp](../README.MD).

## Mã nguồn

- [App.tsx](src/App.tsx): route và phân vai USER/ADMIN.
- [pages/server/](src/pages/server/): chat, tra cứu, ôn/thi và quản trị đang sử dụng.
- [api.ts](src/api.ts), [auth.tsx](src/auth.tsx): API, JWT và phiên đăng nhập.
- [admin/](src/admin/): UI quản trị và đọc dữ liệu nhập.
- [imports/](src/imports/README.md): ảnh thiết kế tham chiếu.
- `tests/`: kiểm tra auth, import, API, chat và KAG inspection.

JWT lưu trong sessionStorage; vai trò lấy từ `/auth/me`, server kiểm phân quyền. Logout/401 xóa phiên và bài thi đang chọn. Backend lỗi thì UI hiển thị lỗi; không thay bằng dữ liệu demo.

Nhập dữ liệu đi qua preview/confirm server, giữ bản nháp trước kiểm duyệt. Đáp án JSON bắt đầu từ 0; CSV/XLSX dùng 1–4. ZIP ảnh nhận PNG/JPEG theo mã.

Chat dùng REST; backend có SSE. Admin Graph/Pipeline/Benchmark đọc API SAMPLE và cho kiểm tra Retrieval giới hạn; không điều khiển Docker/build/benchmark. SAMPLE chưa phải production, bộ câu hỏi benchmark chính thức chưa hoàn thành. Xem [hợp đồng HTTP](../../docs/architecture.md#hợp-đồng-http-và-chính-sách-tương-thích).
