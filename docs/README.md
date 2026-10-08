# Tài liệu dự án

- [Kiến trúc sản phẩm](architecture.md): trách nhiệm package, upstream, entrypoints,
  evaluation, nguồn chuẩn và chính sách tương thích HTTP đề xuất.
- [Runtime Python](runtime.md): interpreter/dependency/vendor pin, setup và kiểm tra offline.
- [Vận hành Builder](runner.md): run/resume/verify, config, ledger, outbox và lock.
- [Backend identity](backend-identity.md): chứng minh physical database và routing trước dispatch.
- [Writer scope](production-writer-scope.md): scope, preconditions và production WRITE còn khóa.
- [Mô hình miền](domain_model.md): identity, cây đơn vị, quan hệ pháp lý và phạm vi graph.
- [Schema kỹ thuật](schema.md): property/predicate, codec, SAFE_EDGE và yêu cầu runtime/Builder.
- [Retrieval và frozen slice](retrieval-demo.md): hợp đồng Retriever/exact ranking;
  kết quả sample được ghi rõ là lịch sử, không phải official benchmark.
- [Benchmark workspace](../benchmark/README.md): G1/G2, dataset lifecycle và nơi lưu reports.
- [Hạ tầng Docker](../docker/README.md) và [WebApp](../WebApp/README.MD).

[README dự án](../README.md) là điểm bắt đầu theo sản phẩm. Design trong
`superpowers/specs/` giữ quyết định và checkpoint lịch sử; tên scope, stage,
release/gate và đường dẫn input trong machine contracts vẫn ổn định. Các
báo cáo phase ngoài repo là bằng chứng tại thời điểm chạy, không tự xác nhận
runtime hay graph đang hoạt động hôm nay.
