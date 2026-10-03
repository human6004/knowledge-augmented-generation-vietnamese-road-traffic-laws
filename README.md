# Knowledge-Augmented Generation cho luật giao thông đường bộ Việt Nam

Kho mã phục vụ nghiên cứu hỏi đáp và suy luận trên luật giao thông đường bộ
Việt Nam bằng Knowledge-Augmented Generation (KAG).

## Dataset và mô hình miền

Dataset chuẩn nằm tại `data/` và phải giữ nguyên. Xem [tài liệu dataset](data/README.md),
[datasheet](data/DATASHEET.md) và [giấy phép dữ liệu](data/LICENSE.md).
Dataset cung cấp văn bản, đơn vị nội dung, thuộc tính xử phạt,
biển báo và quan hệ pháp lý. Phạm vi graph gồm 91 văn bản, 55.597 đơn vị nội dung
và 887 bản ghi biển báo; dữ liệu eval không thuộc retrieval corpus.

Schema namespace `VietRoadTraffic` có ba EntityType `LegalDocument`,
`LegalUnit`, `TrafficSign` và mười predicate. 75 thuộc tính node logical gồm
69 thuộc tính khai báo trong schema và sáu thuộc tính `id/name` kế thừa OpenSPG
`Thing`. Penalty là thuộc tính của `LegalUnit`; evidence nằm trong provenance
cạnh. Xem [mô hình miền](docs/domain_model.md), [schema kỹ thuật](docs/schema.md),
[VietRoadTraffic.schema](kag/schema/VietRoadTraffic.schema) và
[contract máy đọc](kag/schema/schema_contract.json).

## Cấu trúc

- `data/`: corpus pháp lý và tài liệu dữ liệu.
- `kag/`: schema/contract và các package dành cho `builder`, `retriever`, `solver`, `config`.
- `vendor/KAG/`: framework upstream; không đặt mã riêng của dự án tại đây.
- `benchmark/`: thư mục dành cho dữ liệu, runner và kết quả đánh giá.
- `tests/`: kiểm thử theo từng thành phần dự án.
- `docs/`: tài liệu mô hình miền và contract runtime.
- `scripts/`: thư mục dành cho script pipeline Python.
- `docker/WebApp/`: ứng dụng LuậtGT React/Spring Boot và cấu hình Docker;
  xem [hướng dẫn WebApp](docker/WebApp/README.MD).

## Pipeline dự kiến

Luồng dự kiến, chưa vận hành:

```text
data → kag/schema → kag/builder → vendor/KAG → graph/index
     → kag/retriever → kag/solver → benchmark
```

## Framework upstream

Nguồn: [OpenSPG/KAG](https://github.com/OpenSPG/KAG), quản lý bằng Git submodule.
Commit pin: [`fdab15b3929d2ee40dfcdd388f90233096a6afc9`](https://github.com/OpenSPG/KAG/commit/fdab15b3929d2ee40dfcdd388f90233096a6afc9).

Sau khi clone kho mã, lấy đúng phiên bản đã pin bằng:

```sh
git submodule update --init vendor/KAG
```

## Trạng thái triển khai

Schema, contract máy đọc và kiểm thử schema offline có sẵn.
Builder, Retriever và Solver Python chưa triển khai; graph production chưa
được dựng, production ingestion và benchmark chưa chạy; benchmark runner chưa
triển khai. WebApp có frontend/backend riêng; tích hợp KAG phụ thuộc core Python.

Contract yêu cầu Builder kiểm tra trường bắt buộc, `unitType` và Integer,
thực hiện codec đọc/ghi, ghi node trước cạnh, gộp evidence/provenance xác định
và ghi đầy đủ thuộc tính cạnh. OpenSPG dùng tuple nguồn/predicate/đích làm
identity cạnh và cập nhật thuộc tính theo `LAST_WRITE_WINS`.
