# LuậtGT - Chatbot luật giao thông đường bộ & hệ thống ôn thi lái xe

> Tài liệu thiết kế lịch sử nhập cùng UI; nội dung gốc giữ bên dưới để đối chiếu.
> Tính năng, thư mục đề xuất, dependencies và lệnh “dự kiến” không mô tả code hiện tại.
> Setup/routes hiện tại: [frontend](../../README.md), [WebApp](../../../README.MD),
> [kiến trúc sản phẩm](../../../../docs/architecture.md).
> HTTP query adapter chưa triển khai; H1/H2 NOT_STARTED, production WRITE BLOCKED.

Ứng dụng giúp người dùng **tra cứu luật giao thông đường bộ** bằng chatbot (có trích dẫn căn cứ pháp lý) và **ôn luyện thi sát hạch giấy phép lái xe** (học theo chương, biển báo, thi thử). Chatbot dùng **KAG** (Knowledge Augmented Generation) trên đồ thị tri thức luật để trả lời chính xác, có suy luận nhiều bước.

## Tính năng

**Người dùng**
- Chat hỏi đáp luật: mức phạt, trừ điểm, hình thức bổ sung, kèm trích dẫn Điều/Khoản/Điểm và ngày hiệu lực.
- Tra cứu mức phạt theo phương tiện và hành vi.
- Thư viện biển báo, ôn thi theo chương và theo hạng GPLX, thi thử có đồng hồ, câu điểm liệt.
- Chatbot nhận ngữ cảnh trang (đang ở câu hỏi/biển báo nào) để giải thích đúng nội dung.
- Thống kê tiến độ, điểm yếu theo chương.

**Quản trị**
- Quản lý văn bản pháp luật và phiên bản (hiệu lực, thay thế, sửa đổi).
- Chạy pipeline dựng tri thức KAG, kiểm duyệt trước khi xuất bản, thử truy vấn.
- Quản lý ngân hàng câu hỏi thi, nhật ký chat, câu hỏi chưa trả lời được, phản hồi của người dùng.

## Kiến trúc

```
React (FE) --REST/SSE--> Spring Boot (BE) --HTTP--> KAG Service (Python)
                           |   |                        |
                     MySQL Redis            Graph DB + Vector/Search
```

| Thành phần | Công nghệ |
|---|---|
| Frontend | React, TypeScript, Vite, React Router, TanStack Query, Tailwind |
| Backend | Spring Boot (Web, Security + JWT, Data JPA, Validation), Resilience4j |
| Tri thức / chatbot | KAG (OpenSPG) bọc thành dịch vụ HTTP, LLM + embedding |
| Dữ liệu | MySQL, Redis, lưu trữ đối tượng cho ảnh/tài liệu |

Spring Boot đóng vai gateway: xác thực, giới hạn tốc độ, lưu lịch sử chat, proxy streaming (SSE) sang dịch vụ KAG.

## Cấu trúc thư mục (đề xuất)

```
luatgt/
├─ backend/            # Spring Boot (modules: auth, chat, law, learning, exam, progress, admin, integration)
├─ frontend/           # React app (user + admin)
├─ kag-service/        # Dịch vụ KAG (schema, builder, solver, API)
├─ docs/               # Thiết kế, schema tri thức, API
└─ docker-compose.yml
```

## Thiết kế UI

Bản thiết kế giao diện nằm trong canvas thiết kế đi kèm, gồm 4 màn hình: User - Chat tra cứu luật, User - Thi thử, Admin - Tổng quan, Admin - Văn bản và tri thức KAG.

## Chạy thử (dự kiến)

```bash
# 1. Hạ tầng
docker compose up -d mysql redis

# 2. Dịch vụ KAG
cd kag-service && pip install -r requirements.txt && uvicorn app.main:app --port 8000

# 3. Backend
cd backend && ./mvnw spring-boot:run

# 4. Frontend
cd frontend && npm install && npm run dev
```

Biến môi trường chính (ví dụ): `DB_URL`, `REDIS_URL`, `JWT_SECRET`, `KAG_BASE_URL`, `LLM_API_KEY`.

## Lộ trình

1. **MVP**: nạp 1-2 văn bản cốt lõi vào KAG, chat có trích dẫn, tra cứu mức phạt, ôn thi cơ bản.
2. **Giai đoạn 2**: thi thử, thống kê điểm yếu, chat theo ngữ cảnh trang, pipeline cập nhật luật cho admin.
3. **Giai đoạn 3**: biển báo/sa hình tương tác, spaced repetition, đa phương thức, đánh giá chất lượng tự động.

## Lưu ý

- Nội dung chatbot mang tính tham khảo, không thay thế tư vấn pháp lý chính thức.
- Luôn kiểm tra hiệu lực văn bản trước khi xuất bản; dùng nguồn văn bản chính thống.
- Câu hỏi thi dùng đáp án cố định từ ngân hàng đề; AI chỉ giải thích, không tự quyết đáp án.
