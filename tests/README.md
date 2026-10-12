# Kiểm thử core Python

Các suite kiểm Builder, Retriever, Solver, runner, runtime/schema, HTTP API và Evaluation Framework bằng fixtures/doubles. Kết quả offline không xác nhận graph live, provider identity hoặc benchmark pháp lý chính thức.

## Runtime và cách chạy

Dùng **CPython 3.10.16/Linux amd64**, dependencies và vendor đúng pin theo [runtime](../docs/runtime.md). SDK parser cần `six`. Chạy từ root checkout; giữ source read-only, chặn mạng và để fixtures/output ngoài repo.

Mỗi suite chạy trong process riêng để tránh module fixture trùng tên và registry đã cache. Chọn suite phù hợp:

```sh
python -B -m unittest discover -s tests/evaluation -p "test_*.py" -v
python -B -m unittest discover -s tests/solver -p "test_*.py" -v
python -B -m unittest discover -s tests/retriever -p "test_*.py" -v
python -B -m unittest discover -s tests/runtime -p "test_*.py" -v
python -B -m unittest discover -s tests/schema -p "test_*.py" -v
python -B -m unittest discover -s tests/builder -p "test_*.py" -v
python -B -m unittest discover -s tests/runner -p "test_*.py" -v
python -B -m unittest discover -s tests/http_api -p "test_*.py" -v
```

Không gộp discovery toàn `tests/` trong một process. Python host khác version không thay thế runtime chuẩn.

## Trách nhiệm từng suite

- [Builder](builder/README.md): codec, input/mapping/graph plan, writer scope/barrier và vectorizer retry/checkpoint/chunk fallback.
- [Schema](schema/README.md): parser pinned, contract, inheritance, codec và SAFE_EDGE.
- [Retriever](retriever/): vector/index gates, exact ID/source hydration, bounded expansion và ranking trên synthetic read/embedding fixtures.
- [Solver](solver/): public answer/aanswer, planning/deduction, citations/spans, hiệu lực/applicability, conflicts và abstention với FakeLLM; audit hook chặn network.
- [Runtime](runtime/): bootstrap trong fresh subprocess, import origins, registry identity và SHA input.
- [Runner](runner/): ledger/outbox/resume, CLI, scope, backend identity và readback trên mocks.
- [HTTP API](http_api/): request/auth/admission, query/SSE, release/proof, SAMPLE inspection, read broker và provider budgets trên fixtures.
- [Evaluation](evaluation/): dataset/lifecycle/generation/import, G1/G2, metrics/eligibility/reports/CLI; không chạy bộ benchmark pháp lý hay paid judge.

Runner lock cần bind mount thật từ `D:/study/caoDATA-workspace/runs/.graph-locks` tới `/run/kag-locks`, đúng kiểm tra tại [runner.py](../kag/runner.py). Dùng identity fixture `physical-fixture-db`; không dùng database production, spoof mountinfo hoặc bypass `_shared_lock_root`. Xem [runner và lock](../docs/runner.md).

Nếu harness dùng audit hook chặn ghi, khi unlink symlink phải kiểm directory entry; không resolve sang target rồi chặn nhầm.

## WebApp

Java/H2 và MySQL kiểm thử riêng: [backend](../WebApp/backend/README.md#chạy). Frontend test/typecheck/build: [frontend](../WebApp/frontend/README.md#phát-triển-và-kiểm-thử). Kiểm tra Docker/API tạo tài khoản và state theo [WebApp](../WebApp/README.MD); cần phạm vi vận hành riêng.
