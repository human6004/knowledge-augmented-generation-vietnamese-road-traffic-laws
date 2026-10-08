# Bộ chạy đánh giá

Thư mục này chưa có runner riêng. API hoạt động đã triển khai ở
[`kag/evaluation/evaluate.py`](../../kag/evaluation/evaluate.py):
`evaluate_g1`, `evaluate_g2`, `aevaluate_g2`. Runtime Retriever/pipeline được
caller cung cấp; G1 dùng `retrieve`, G2 dùng public `answer`/`aanswer`.

CLI [`kag.evaluation`](../../kag/evaluation/__main__.py) chỉ có validate,
freeze và import-legacy; không có lệnh chạy benchmark live. Không thay bằng
solver benchmark-only hoặc truyền QID/gold/category vào inference. Xem
[entrypoints](../../docs/architecture.md#entrypoints-và-lệnh-ổn-định).
