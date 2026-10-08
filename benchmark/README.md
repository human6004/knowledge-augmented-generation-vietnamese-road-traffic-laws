# Đánh giá và workspace benchmark

Evaluation Framework đã triển khai tại [`kag/evaluation`](../kag/evaluation/),
không nằm trong các thư mục reserved bên dưới:

- `datasets/`: reserved cho nguồn/version dataset và manifest.
- `runners/`: reserved; chưa có runner riêng.
- `results/`: reserved; kết quả thực chạy lưu ngoài repository.

Các thư mục reserved không chứa implementation và không cần README riêng.
Hướng dẫn dataset, runner và output được duy trì trong tài liệu này.

## Dataset và lifecycle

Validation, lifecycle và legacy importer tại [dataset.py](../kag/evaluation/dataset.py)
và [legacy.py](../kag/evaluation/legacy.py). Corpus/eval nguồn tại
[data](../data/README.md) được bảo vệ, không chuyển hoặc sửa tại đây;
eval không thuộc retrieval corpus. PROVISIONAL dành cho phát triển, giữ
uncertainty/missing labels; không tự bổ sung gold hoặc fields thiếu.
FROZEN khóa immutable version, canonical bytes và manifest hashes đã xác minh.

G1 gọi Legal Retriever; G2 gọi public `answer()`/`aanswer()` của Legal Solver.
Dataset PROVISIONAL và FROZEN phải được ghi riêng; FROZEN chỉ official khi
manifest được xác minh và chỉ định official tường minh. CLI freeze mặc định
và thực tế luôn nonofficial; report hiện luôn `PAPER_ELIGIBLE=NO`.
`COMPLETE` chỉ xác nhận mọi row được accounting, không phải chất lượng hoặc
legal-domain PASS. Freeze không tự cấp quyền publication.

## Runner và inference boundary

API hoạt động tại [evaluate.py](../kag/evaluation/evaluate.py):
`evaluate_g1`, `evaluate_g2`, `aevaluate_g2`. Retriever/pipeline được caller
cung cấp; G1 dùng `retrieve`, G2 dùng public `answer`/`aanswer`. Không cần tạo
runner khác. Không dùng Solver benchmark-only hoặc truyền QID/gold/category
vào inference. Gold/QID chỉ phục vụ evaluation accounting.

CLI [kag.evaluation](../kag/evaluation/__main__.py) chỉ xử lý dataset, không
có lệnh benchmark live. Judge chưa cấu hình không là correctness PASS.
Smoke synthetic/sample không thay thế official benchmark.

## Lệnh dataset offline

Lệnh offline từ root repository:

```sh
python -B -m kag.evaluation validate /evidence/eval_questions.jsonl
python -B -m kag.evaluation freeze /evidence/provisional.jsonl --output-root /runs/evaluation --dataset-version road-law-frozen-v1
python -B -m kag.evaluation import-legacy /evidence/legacy.json --output-dir /runs/evaluation/import-review --dataset-version road-law-provisional-v1
```

`/evidence/...` là input ngoài repo do operator cung cấp, không phải fixture
có sẵn. Các tác vụ freeze/import tạo output mới ngoài repo; không overwrite
gold/source. CLI không chạy inference G1/G2. Không tự chạy full benchmark,
judge, embedding hoặc provider. Xem [kiến trúc evaluation](../docs/architecture.md#evaluation-framework).

## Kết quả và evidence

Evaluation Framework nhận `output_dir` ngoài repository và ghi snapshots,
manifest, metrics cùng reports có hash; implementation tại
[report.py](../kag/evaluation/report.py). Không lưu secrets hoặc overwrite
source/gold trong workspace kết quả.

Giữ dataset/protocol/model identity và PROVISIONAL/FROZEN/official riêng trong
báo cáo. Metrics không đủ điều kiện phải là `null` kèm lý do, không thay bằng
zero/PASS. COMPLETE không phải quality PASS; PAPER_ELIGIBLE=NO là trạng thái
report hiện tại. Dataset/protocol/run manifest quyết định eligibility và
provenance, không đổi semantics Solver để khớp gold.

API tổng quan: [Evaluation Framework](../docs/architecture.md#evaluation-framework).
Kiểm thử offline: [tests](../tests/README.md). [README dự án](../README.md).
