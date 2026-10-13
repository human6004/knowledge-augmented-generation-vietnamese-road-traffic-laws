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

## Authoring evidence-first từ phương pháp B2

[generation.py](../kag/evaluation/generation.py) kế thừa quy trình B2 của repo
`kag-legal-assistant`: chọn nguồn trước, viết/sửa draft, lấy gold từ exact span,
chống trùng và review trước freeze. Không có bằng chứng rằng repo cũ có một
LLM/template generator tự động; bước assemble/validate dưới đây là phần ADAPT.
Không gọi model để lấy gold. Draft có thể do người hoặc công cụ đề xuất;
deterministic validation không xác nhận semantics hoặc human legal review.

Input: source catalog `h1-source-catalog-1.0`; danh sách draft với `qid`,
`question`, `category`, `expected_abstain`, `expected_behavior`, `focus`,
`rationale`, `evidence`. Mỗi evidence gồm `entity_type`, `entity_id`, `field`,
`start`, `end`, `required`; offsets là Unicode code points. Không nhập quote
hoặc gold answer tự sinh: assembler lấy trực tiếp từ source có SHA hợp lệ.
Config gồm `dataset_version`, `as_of` ISO date, `categories`.
`expected_behavior=EXTRACT_ONLY` cho positive; negative dùng `ABSTAIN`,
gold rỗng và rationale giới hạn phạm vi thiếu authority. Không suy ngày đánh
giá thành ngày hiệu lực. Multi-hop cần ít nhất hai Điều độc lập và rationale;
hai Khoản cùng Điều không đủ. Cần người review sự cần thiết của các evidence.

```sh
rtk proxy python -B -m kag.evaluation generate --catalog /evidence/source-catalog.json --drafts /evidence/drafts.json --config /evidence/config.json --output-dir /runs/new-dataset
rtk proxy python -B -m kag.evaluation validate-generated /runs/new-dataset/eval_questions.jsonl --catalog /evidence/source-catalog.json --generation-manifest /runs/new-dataset/generation-manifest.json
rtk proxy python -B -m kag.evaluation freeze /runs/new-dataset/eval_questions.jsonl --output-root /runs/reviewed --dataset-version reviewed-v1 --review /evidence/human-review.json
```

Review receipt phải có `dataset_hash`, `reviewer`, `reviewed_at` UTC Z và
`approved_qids` bao phủ đúng toàn dataset. Operator cung cấp receipt sau review;
CLI không xác thực danh tính reviewer, không tự nâng official/paper authority.
Dataset generated thiếu receipt bị chặn freeze. Source thiếu trả `deferred`,
không tạo gold giả. Manifest ghi đủ mọi category với count0 khi chưa sinh câu;
count0 không chứng minh SAMPLE hỗ trợ category đó. Output mới, không overwrite.

Dataset chính thức sau này vẫn dùng schema1.0 và API G1/G2 hiện hữu, không cần
sửa evaluator. Phải validation nguồn và human review trước freeze; cấu hình
runtime, catalog identity và quyền execution riêng trước khi chạy benchmark.

Metric policy mặc định1.0 giữ semantics lịch sử. Opt-in
`EvaluationProtocol(metric_policy_version='1.1')` thêm `source_span.*`:
evidence recall, required recall, context precision, Hit@k, Recall@k và MRR
trên thứ tự mixed contexts trả về. Công thức kế thừa; support đổi sang đúng
public source identity và quote nguyên văn trong source field. Không đồng
nhất với matching structure/token-overlap0.8 của repo cũ, hoặc rank theo
channel của các metric G1 cũ. Policy1.1 thêm macro category means và native
ANSWERED/ABSTAINED/UNANSWERED accounting; blank nonabstained không được chấm
false answer/correct abstention. Judge/full-trace metrics vẫn null khi thiếu
bằng chứng; không có composite score hay threshold PASS tự đặt.

## Thực thi G1/G2

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
