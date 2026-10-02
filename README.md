# Knowledge-Augmented Generation cho luật giao thông đường bộ Việt Nam

Kho mã mới phục vụ nghiên cứu suy luận trên luật giao thông đường bộ Việt Nam.
Dataset **LOCKED R2** và schema miền chính thức **v0.1** đã có.
Xem [mô hình miền](docs/domain_model.md), [schema kỹ thuật](docs/schema.md)
và [VietRoadTraffic.schema](kag/schema/VietRoadTraffic.schema).

Dataset chuẩn nằm tại `data/` và phải giữ nguyên. Xem [tài liệu dataset](data/README.md),
[datasheet](data/DATASHEET.md) và [giấy phép dữ liệu](data/LICENSE.md).

## Cấu trúc

- `kag/`: các package riêng của dự án, gồm `schema`, `builder`, `retriever`, `solver`, `config`.
- `vendor/KAG/`: framework upstream; không đặt mã riêng của dự án tại đây.
- `benchmark/`: bộ dữ liệu, bộ chạy và kết quả đánh giá trong tương lai.
- `tests/`: kiểm thử theo từng thành phần dự án.
- `scripts/`, `docker/`, `docs/`: vận hành, môi trường và tài liệu trong tương lai.

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

Builder, retriever, solver chưa triển khai; graph chưa build, chưa chạy production
ingestion OpenSPG hoặc benchmark. Ba nhóm xác nhận server còn bắt buộc trước ingestion.
