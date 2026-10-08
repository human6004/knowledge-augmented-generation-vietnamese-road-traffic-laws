# Kiểm thử core Python

Các suite hiện có kiểm Builder, Retriever, Solver, runner, bootstrap/schema và
Evaluation Framework. Đây là kiểm thử offline bằng fixtures/doubles; PASS
không xác nhận graph live, provider identity hoặc benchmark pháp lý official.

## Runtime và cách chạy

Chạy từ root checkout, với **CPython 3.10.16/Linux amd64**, đủ dependencies và
vendor đúng pin theo [setup runtime](../docs/runtime.md). Solver/runtime import
SDK thật; Python host khác version không thay thế runtime chuẩn. Schema parser
cần `six`. Giữ source read-only, network denied; fixtures/output nằm ngoài repo.

Mỗi suite chạy trong process riêng để tránh module fixture cùng tên và registry
đã cache. Chọn suite cần kiểm tra; các lệnh dưới đây không là yêu cầu chạy lại
toàn bộ test hay full benchmark:

```sh
python -B -m unittest discover -s tests/evaluation -p 'test_*.py' -v
python -B -m unittest discover -s tests/solver -p 'test_*.py' -v
python -B -m unittest discover -s tests/retriever -p 'test_*.py' -v
python -B -m unittest discover -s tests/runtime -p 'test_*.py' -v
python -B -m unittest discover -s tests/schema -p 'test_*.py' -v
python -B -m unittest discover -s tests/builder -p 'test_*.py' -v
python -B -m unittest discover -s tests/runner -p 'test_*.py' -v
```

## Trách nhiệm từng suite

- **Builder:** [hướng dẫn riêng](builder/README.md), codec/mapping/graph plan,
  writer scope, retry/checkpoint và embedding chunk fallback trên fixtures.
- **Schema:** [hướng dẫn riêng](schema/README.md), parser/contract, inheritance,
  codec và SAFE_EDGE.
- **Retriever:** [test_retriever.py](retriever/test_retriever.py) kiểm vector/index
  gates, exact ID/source hydration, bounded expansion và mocked read transport;
  [test_evaluation.py](retriever/test_evaluation.py) kiểm frozen slice/exact ranking.
  ReadFixture và embedding callable dùng dữ liệu synthetic, không graph/model live.
- **Solver:** [test_legal_solver.py](solver/test_legal_solver.py) dùng pinned SDK,
  FakeLLM và retrieval fixtures; kiểm planning/deduction, public answer/aanswer,
  citations/spans, hiệu lực/applicability, conflicts và safe abstention. Network
  bị audit hook chặn; không thay public Solver bằng implementation benchmark-only.
- **Runtime:** [test_bootstrap.py](runtime/test_bootstrap.py) dùng fresh subprocess
  cho initialize-first/preload-builder/preload-solver, kiểm idempotence,
  origins và registry identity; [test_inputs.py](runtime/test_inputs.py) kiểm SHA input.
- **Runner:** [tests](runner/) kiểm ledger/outbox/resume, CLI, scope, physical
  backend identity và readback trên mocks. Suite lock cần canonical bind mount
  thật mà [run_state.py](../kag/run_state.py) xác minh; xem
  [runner và lock](../docs/runner.md). Dùng lock root ngoài repo cho identity
  fixture `physical-fixture-db`, không dùng production database; không spoof
  mountinfo hoặc bypass `_shared_lock_root` để làm test PASS. Audit hook cho
  symlink unlink phải xét directory entry, không resolve rồi chặn nhầm target.
- **Evaluation:** [tests](evaluation/) kiểm dataset/lifecycle/import, G1/G2,
  metrics/eligibility/reports/CLI trên fixtures. Đây là kiểm framework, không
  chạy bộ benchmark nguồn hoặc paid judge.

## WebApp

Java/H2 và database MySQL kiểm thử riêng: [backend](../WebApp/backend/README.md#chạy).
Frontend test/typecheck/build: [frontend](../WebApp/frontend/README.md#phát-triển-và-kiểm-thử).
Kiểm tra Docker/API thật tạo state: [WebApp](../WebApp/README.MD), thực hiện theo
quyền vận hành riêng. Production WRITE vẫn BLOCKED; H1/H2 NOT_STARTED.
