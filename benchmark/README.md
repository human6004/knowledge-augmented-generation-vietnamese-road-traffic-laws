# Đánh giá và benchmark

Framework nằm trong [kag/evaluation](../kag/evaluation/). `datasets/`, `runners/`, `results/` là thư mục dự trữ; chưa có runner riêng. Input và kết quả thực chạy được quản lý ngoài repository.

## Dataset và lifecycle

[dataset.py](../kag/evaluation/dataset.py) kiểm schema/lifecycle/manifest; [legacy.py](../kag/evaluation/legacy.py) chuyển dữ liệu cũ sang bản cần review. Corpus/eval tại [data](../data/README.md) được giữ nguyên; eval không thuộc nguồn truy xuất.

- `PROVISIONAL`: phục vụ phát triển, giữ các nhãn thiếu hoặc chưa chắc chắn.
- `FROZEN`: version bất biến, canonical bytes và manifest hashes phải được xác minh.
- `official_benchmark`: chỉ có khi được chỉ định tường minh trên manifest hợp lệ; freeze CLI luôn tạo nonofficial.

Bộ câu hỏi chính thức chưa hoàn thành. Synthetic hoặc SAMPLE không thay thế official benchmark. `COMPLETE` chỉ xác nhận đã ghi nhận mọi câu; report hiện giữ `PAPER_ELIGIBLE=NO`. Trạng thái dataset không tự cấp quyền xuất bản hoặc xác nhận chất lượng pháp lý. Không tự bổ sung gold.

## Tạo bộ câu hỏi từ nguồn

[generation.py](../kag/evaluation/generation.py) lấy nguồn trước, ghép draft với đoạn trích chính xác, chống trùng và yêu cầu review trước freeze. Assembler lấy quote/gold từ nguồn có SHA hợp lệ; không gọi model để lấy gold. Kiểm tra cấu trúc và nguồn không thay thế review ngữ nghĩa pháp lý.

Input cần source catalog `h1-source-catalog-1.0`, config `dataset_version`/`as_of`/`categories` và drafts có `qid`, `question`, `category`, `expected_abstain`, `expected_behavior`, `focus`, `rationale`, `evidence`. Evidence dùng `entity_type`, `entity_id`, `field`, `start`, `end`, `required`; offsets tính theo Unicode code points.

Positive dùng `EXTRACT_ONLY`; negative dùng `ABSTAIN`, gold rỗng và rationale giới hạn phạm vi. Multi-hop cần ít nhất hai Điều độc lập và rationale. Source thiếu được ghi `deferred`; không tạo gold giả. `as_of` là ngày đánh giá, không suy thành ngày hiệu lực.

Từ root repository, với input/output ngoài repo do operator cung cấp:

```sh
python -B -m kag.evaluation generate --catalog /evidence/source-catalog.json --drafts /evidence/drafts.json --config /evidence/config.json --output-dir /runs/new-dataset
python -B -m kag.evaluation validate-generated /runs/new-dataset/eval_questions.jsonl --catalog /evidence/source-catalog.json --generation-manifest /runs/new-dataset/generation-manifest.json
python -B -m kag.evaluation freeze /runs/new-dataset/eval_questions.jsonl --output-root /runs/reviewed --dataset-version reviewed-v1 --review /evidence/human-review.json
```

Review receipt cần `dataset_hash`, `reviewer`, `reviewed_at` UTC Z và `approved_qids` bao phủ đúng dataset. CLI kiểm coverage/hash, không xác thực danh tính reviewer. Generated dataset thiếu receipt bị chặn freeze.

## Thực thi G1/G2

[evaluate.py](../kag/evaluation/evaluate.py) có `evaluate_g1`, `evaluate_g2`, `aevaluate_g2`. Caller cung cấp retriever/pipeline, protocol, runtime và quyền execution:

- G1 gọi Legal Retriever `retrieve(question, top_k=..., expand=False)`.
- G2 gọi public Legal Solver `answer()` hoặc `aanswer()`.
- QID/gold/category chỉ dùng ghi nhận và chấm kết quả, không đưa vào inference.

Policy mặc định `1.0` giữ metric hiện hữu. Opt-in `EvaluationProtocol(metric_policy_version="1.1")` thêm source-span recall/precision/ranking, macro category means và accounting `ANSWERED`/`ABSTAINED`/`UNANSWERED`. Metric thiếu bằng chứng giữ `null` kèm lý do; judge/full-trace chưa đủ không được coi là correctness PASS. Không có composite score hoặc ngưỡng PASS tự đặt.

CLI chỉ xử lý dataset offline, chưa có lệnh chạy benchmark live. Không cần tạo Solver riêng để đánh giá hoặc đổi Solver cho khớp gold.

## Lệnh dataset offline

Từ root repository:

```sh
python -B -m kag.evaluation validate /evidence/eval_questions.jsonl
python -B -m kag.evaluation freeze /evidence/provisional.jsonl --output-root /runs/evaluation --dataset-version road-law-frozen-v1
python -B -m kag.evaluation import-legacy /evidence/legacy.json --output-dir /runs/evaluation/import-review --dataset-version road-law-provisional-v1
```

`/evidence/` và `/runs/` là đường dẫn ví dụ ngoài repository. Freeze/import tạo output mới, không overwrite source/gold. Generated dataset cần thêm `--review` như trên. Các lệnh không chạy inference G1/G2, judge hoặc provider.

## Kết quả và thông tin lần chạy

[report.py](../kag/evaluation/report.py) ghi snapshots, manifests, metrics và reports có hash vào `output_dir` ngoài repo. Giữ dataset/protocol/model identity, lifecycle và official eligibility trong báo cáo; không lưu secrets.

Runtime/source identity và quyền benchmark cần bằng chứng riêng. Dataset FROZEN hoặc run COMPLETE không tự xác nhận chất lượng, production readiness hay điều kiện công bố khoa học.

Kiểm thử framework offline: [tests](../tests/README.md). Kiến trúc: [Evaluation Framework](../docs/architecture.md#evaluation-framework).
