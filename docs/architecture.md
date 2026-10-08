# Kiến trúc sản phẩm KAG luật giao thông

Core Python chuyển nguồn pháp lý thành graph có provenance, truy hồi evidence
và trả kết quả pháp lý có kiểm chứng nguồn. Evaluation đo Retriever/Solver
hiện tại. WebApp là ứng dụng nghiệp vụ React/Spring riêng, đã có HTTP client
nhưng chưa có query adapter Python để nối end to end.

Tài liệu mô tả code hiện hữu và policy đề xuất riêng. Production WRITE vẫn
BLOCKED. Bootstrap hiện xử lý initialize-first, preload-builder và preload local
solver; [regression import-order](../tests/runtime/test_bootstrap.py) kiểm origins/
registry và idempotence của cả ba thứ tự.
Implementation, offline checks, graph live và benchmark pháp lý là bằng chứng độc lập.

## Trách nhiệm package

| Package/module | Trách nhiệm và ranh giới |
| --- | --- |
| `kag/builder/` | Kiểm source/contract, deterministic graph plan, codec, scope; adapter writer và resilient vectorizer trên API upstream. Không tự cấp quyền production WRITE. |
| `kag/runner.py` | Điều phối bounded batches, replay/provider policy tường minh, barriers và run/verify. Public runner hiện chặn mọi WRITE. |
| `kag/run_state.py` | State, SQLite ledger/outbox, append-only evidence, resume và lock. Không blind resend INTENT chưa chắc hoàn tất. |
| `kag/backend_identity.py` | Session/proof live: project, route, container/network và physical database identity. Receipt không thay active authority. |
| `kag/verify.py` | Parameterized direct Neo4j readback và exact graph verification; có thể ghi verification artifacts ngoài repo. |
| `kag/retriever/` | Query embedding qua callable do caller cung cấp, bốn vector targets, exact hydration, bounded one-hop expansion. Không gọi Solver. |
| `kag/legal_solver.py` | Public legal answering, evidence/candidate binding, legal executors và safe generator; dùng orchestrator upstream. |
| `kag/legal_prompts.py` | Planning/deduction prompts, parser và validation legal candidate. Prompt nội dung giữ nguyên. |
| `kag/evaluation/` | Typed dataset, freeze/import, G1/G2, eligibility, metrics và báo cáo. Không tự tạo runtime/provider. |
| `kag/bootstrap.py` | Một boundary kiểm interpreter/vendor và ghép namespace local/upstream. |
| `kag/schema/`, `kag/config/` | Schema/contract chuẩn và config examples default DENY/NO_OP. Config không chứa proof cấp WRITE. |
| `WebApp/` | Nghiệp vụ, publication, auth, MySQL/Redis/MinIO, chat HTTP client; query adapter còn thiếu. |
| `vendor/KAG/` | Source OpenSPG KAG đã pin; không chỉnh sửa hoặc đặt code ứng dụng vào vendor. |

`benchmark/` và root `scripts/` là workspace reserved có tài liệu dẫn tới code
hoạt động; không phải bằng chứng evaluation/runtime chưa được triển khai.

## Luồng dữ liệu và transport

```text
data + schema/contract + protected relation inputs
  → source validation → deterministic graph plan
  → bounded runtime/state → vectorizer/writer adapters → OpenSPG → Neo4j
       [production WRITE currently BLOCKED]

question → pinned iterative planner/pipeline
            ├→ LegalRetrieverExecutor → Retriever → query embedding
            │                                    → direct Neo4j vector/readback
            │                                    → exact source evidence
            ├→ LegalDeduceExecutor → evidence-bound legal candidate
            └→ SafeLegalGenerator → AnswerResult / safe abstention

typed evaluation dataset → existing Retriever or public answer/aanswer
                         → eligible metrics + immutable reports outside repo

React → Spring monolith → KagClient → query HTTP adapter [absent] → legal API
```

OpenSPG SDK phục vụ project/schema và writer transport. Local
[`Neo4jRetrievalClient`](../kag/retriever/neo4j.py) kế thừa
[`Neo4jReadClient`](../kag/verify.py), POST trực tiếp tới Neo4j
`/db/{database}/tx/commit` với allowlisted read statements; không đi qua
OpenSPG Server cho mọi read. Hai stack Compose độc lập: OpenSPG có metadata
MySQL, Neo4j, MinIO; WebApp có MySQL nghiệp vụ, Redis, MinIO riêng.

Builder kiểm required/enum/native Integer, ghi node trước cạnh và gộp provenance
xác định. Writer giữ transport upstream nhưng phục hồi Integer và kiểm scope,
identity, vectors, source bytes, node barrier. Replay phải khớp provenance/
checkpoint; missing vector không tự chuyển sang provider. Source-only mode
không tạo graph/provider clients, vẫn tạo run artifacts ngoài repo.

Retriever dùng `LegalUnit.text`, `LegalDocument.title`, `TrafficSign.ten`,
`TrafficSign.moTa`; query vector 3072 giá trị hữu hạn, khác zero. Mỗi target
cần đúng một index ONLINE/3072/cosine. Evidence giữ ID, whole source fields,
vector provenance và graph context. Expansion mặc định off, một hop có giới
hạn. ANN membership phụ thuộc index/runtime; thứ tự tie trên candidates trả
về được xác định, không hứa candidate set bất biến qua mọi môi trường.

Legal Solver dùng evidence server-read-back, kiểm câu hỏi/as_of/fingerprint,
source span, authority, applicability, hiệu lực và conflict. Facts là
LegalUnit.text hoặc TrafficSign.moTa đủ điều kiện; support có thể là document/
sign metadata. Safe generator dựng answer từ quotes, không gọi thêm generic
LLM final-answer generator. Thiếu bằng chứng dẫn tới abstention hợp lệ.

## Upstream và namespace

Source upstream: git submodule `vendor/KAG`, commit
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`, version source `0.8.0`.
Runtime chuẩn CPython 3.10.16/Linux amd64; dependency lock tại
[`requirements.txt`](../requirements.txt). Source upstream mới là origin SDK
được bootstrap chọn; không cài thêm wheel KAG để thay pin.

[`initialize()`](../kag/bootstrap.py) preload local `kag`/`kag.builder`, đặt
vendor root đầu `sys.path`, vendor `kag` đầu root `__path__`, append vendor
builder sau local builder rồi exec vendor init để giữ registry upstream.
Builder local-first giữ codec/input/plan/adapters; solver/interfaces/common
được tìm từ vendor theo path đã ghép. Nếu solver đã preload từ đúng local marker,
bootstrap dùng `importlib.reload()` sau thiết lập vendor namespace, trước vendor
root initializer; giữ module object và chạy solver initializer upstream.
Không reload interface, registry hoặc các solver submodules. `kag.__file__` có thể vẫn local; cần
module origin, class source và registry ABC/class identity để chứng minh thực tế.

Composition hiện tại:

- `NativeIntegerKGWriter` subclass upstream `KGWriter`, gọi normalizer và
  `_invoke` upstream rồi thêm Integer/safety guards.
- `ResilientVectorizer` wrap upstream `BatchVectorizer` trên clone và giữ local
  retry/checkpoint/fallback policy; không tương đương toàn bộ default behavior.
- `build_pipeline()` dùng chính upstream `KAGIterativePlanner` và
  `KAGIterativePipeline`, default max_iteration=5 và Finish upstream.
- Local `LegalRetrieverExecutor`, `LegalDeduceExecutor`, legal prompts và
  `SafeLegalGenerator` dùng interfaces upstream; không dùng generic retrieval
  hoặc generic Deduce/final-answer behavior thay cho legal contracts.

### Vì sao legal adapters nằm ở kag root

[`legal_solver.py`](../kag/legal_solver.py) và
[`legal_prompts.py`](../kag/legal_prompts.py) là application-local names tránh
tranh namespace `kag.solver` do vendor cung cấp. `legal_solver` initialize
trước các SDK imports. Move vào `kag/solver` có thể đổi resolution, cache hoặc
registry identity. Lỗi lịch sử `ModuleNotFoundError: No module named 'kag.solver.prompt'`
khi package local được nạp trước initialize đã được xử lý trong bootstrap bằng
upstream solver initializer. Root placement hiện có là
compatibility boundary, không phải bằng chứng file bị đặt sai.

Giữ tất cả `__init__.py`, kể cả package markers một byte. Ba import paths đã có
regression coverage không chứng minh deletion/move package an toàn.
Không xóa/đổi `kag/solver` hoặc đảo namespace order. Lazy cycles/private methods
cần gate riêng, không giải bằng documentation cleanup.

## Entrypoints và lệnh ổn định

Chạy từ root checkout, trong runtime chuẩn. Các path `/evidence/...`, `/runs/...`
là external inputs/outputs do operator chuẩn bị; không phải files có sẵn.

```sh
python -B -m kag --help
python -B -m kag.evaluation --help
```

Runtime library: `kag.runner.run`, `kag.runner.verify_run`; CLI templates:

```sh
python -B -m kag run --config /evidence/runtime.json --run-id source-validation
python -B -m kag resume --config /evidence/runtime.json --run-id source-validation
python -B -m kag verify --config /evidence/runtime.json --run-id source-validation
```

Config examples default DENY hoặc source-only NO_OP; phải dùng đúng scope,
external roots và hashes thực. `verify` read-only đối với graph nhưng cập nhật
receipt/log ngoài repo. Exit 0/1/2 là PASS/ERROR/BLOCKED của command/gate đó,
không là benchmark quality hoặc production release. Xem [runner](runner.md).

Library answering: `kag.legal_solver.build_pipeline(retriever, llm)`,
`answer(question, pipeline=..., as_of=...)`, `await aanswer(...)`.
Retriever là `kag.retriever.retriever.Retriever.retrieve`.
Đây là library API cần dependencies/backend do caller cung cấp; không có
HTTP query server hoặc lệnh `serve` hiện hữu.

Evaluation CLI chỉ xử lý dataset; lệnh validate/freeze/import-legacy và quy ước
workspace được duy trì tại [benchmark](../benchmark/README.md#lệnh-dataset-offline).

Freeze/import ghi output mới, không overwrite input. Library G1/G2 nhận runtime
được caller cung cấp; commands trên không chạy inference, judge hoặc full150.
WebApp setup nằm trong [hướng dẫn riêng](../WebApp/README.MD), không tự ingest
graph khi start Compose.

## Evaluation Framework

[`kag/evaluation`](../kag/evaluation/__init__.py) cung cấp `load_dataset`,
`validate_dataset`, `freeze_dataset`, `import_legacy`, `evaluate_g1`,
`evaluate_g2`, `aevaluate_g2`, `summarize`, `write_report`.

- **G1 retrieval** dùng Retriever hiện tại, exact identities và ranking theo
  channel; gold/QID/category nằm trong evaluation accounting, không gửi vào retrieval.
- **G2 legal answer** gọi public answer/aanswer, yêu cầu as_of cho row đủ điều
  kiện; đo answer/citations/abstention theo typed gold và protocol. Không thay
  bằng benchmark-only Solver. Judge cần cấu hình/hiệu chuẩn riêng.
- **PROVISIONAL** giữ uncertainty/missing labels; không tự bổ sung gold hoặc
  suy luận fields thiếu. Legacy importer ghi rejected/manual mapping riêng.
- **FROZEN** là immutable version + canonical bytes + manifest hashes. Chỉ
  official khi manifest được xác minh và `official_benchmark=true` tường minh;
  CLI freeze không có official flag và luôn nonofficial.
- Report hiện luôn `PAPER_ELIGIBLE=NO`; release identity chưa attested không
  được nâng thành official legal-domain PASS. `COMPLETE` chỉ đủ accounting.
  Ineligible/judge unavailable metrics là null với lý do, không thay bằng zero/PASS.

[`kag/retriever/evaluation.py`](../kag/retriever/evaluation.py) có stable
frozen-slice/exact-ranking helpers; [`metrics.py`](../kag/evaluation/metrics.py)
tái sử dụng rank evaluator. Hai modules có trách nhiệm khác nhau, không merge
hoặc delete. [Sample retrieval contract](retrieval-demo.md) giữ kết quả lịch sử
zero eligible gold riêng với framework G1/G2 của sản phẩm.

## Nguồn chuẩn và identity

| Nguồn | Quyền quyết định |
| --- | --- |
| [`data/`](../data/README.md) và checksums | Corpus/eval nguồn; không dùng eval làm retrieval evidence. |
| [`VietRoadTraffic.schema`](../kag/schema/VietRoadTraffic.schema), [`schema_contract.json`](../kag/schema/schema_contract.json) | Node/edge/property/codec/identity. Java Maven package trực tiếp các file này, không tạo schema authority riêng. |
| [`artifacts/inputs/xref-a3g2/manifest.json`](../artifacts/inputs/xref-a3g2/manifest.json) | Canonical relation inputs + byte hashes; tên/path lịch sử là machine contract phải giữ. |
| External graph plan/provenance/checkpoint manifests | Exact source/plan/model bindings; graph hiện hữu phải được readback kiểm riêng. |
| Physical DB/session proof | Routing và database identity live; host/name/hash receipt không tự cấp WRITE. |
| Server-read-back source + current request | Authority cho legal evidence/citations; model output không tự trở thành nguồn pháp lý. |
| WebApp publication tables | Nội dung nghiệp vụ được duyệt và hiệu lực mà ChatService kiểm; không tự chứng minh đồng bộ với graph. |
| Dataset/protocol/run manifest | Eligibility, dataset lifecycle và evaluation provenance; không sửa Solver behavior để khớp gold. |

Config/template không chứa credential thật; secrets ở môi trường/local config
ngoài version control. Root README là product entry, tài liệu này là bản đồ
architecture; source và machine contracts quyết định khi prose lệch. Designs
trong `docs/superpowers/specs/` và Git giữ lịch sử. Product-facing names là
Builder, Retrieval, Legal Answering, Evaluation, Runtime Verification; serialized
scope/stage/gate names như `C4_3A_MANIFEST_SAMPLE`/`SOURCE_ONLY_DRY_RUN` không đổi.

## Hợp đồng HTTP và chính sách tương thích đề xuất

**Hiện hữu:** Java `KagClient` POST `/v1/query` hoặc `/v1/query/stream` tới
`KAG_BASE_URL` (mặc định local8000/Compose host.docker.internal8000). Request
là `{user_id,message,context_id,schema_contract:{namespace,schema_sha256,contract_sha256}}`.
REST cần answer nonblank≤20000 và 1..20 citations `{doc_id,unit_id,quote}`.
ChatService kiểm toàn bộ: document published/effective, unit published thuộc
đúng doc, quote nonblank exact substring `LegalUnit.text`. SSE upstream chỉ
delta/done; done mang full REST result. Unknown/error event hoặc thiếu done
bị reject; Java tự tạo downstream error. Frontend hiện dùng REST.

**Native:** `AnswerResult` có answer, tuple Citation, abstained và reason.
`to_dict()` hiện xuất answer/citations/abstained, không xuất reason. Citation
giữ doc_id, optional unit_id/sign_id, evidence_id, field, start/end và quote.
Abstention có empty citations; document/sign support có thể không có unit_id
hoặc quote thuộc field khác text. Toàn miền kết quả này không tương thích
Java unit-only contract. Native answer cũng có thể vượt Java size/count bounds.

**Policy đề xuất, chưa triển khai:**

1. Giữ public Solver/metrics/prompts nguyên trạng; adapter là projection được
   kiểm chứng, không sửa semantics để Java chấp nhận. So khớp schema identity
   trước inference; user_id/context_id không tự là authorization/evidence authority.
2. Legacy v1 chỉ trả success nếu native non-abstained và **mọi** citation là
   LegalUnit.text có unit/doc mapping, exact quote và whole-field span hợp lệ,
   được WebApp xác nhận publication/effectivity; answer/citations không vượt bounds.
   Không drop support citation, gán giả unit_id, truncate nguồn hoặc rerun để ép PASS.
3. Abstained, unsupported citation kind/source mismatch hoặc vượt bounds phải
   fail closed toàn câu trả lời. Đề xuất adapter trả non-2xx có code riêng;
   Java hiện gộp non-2xx thành 503/UNAVAILABLE, không có trạng thái abstention.
   Đây là giới hạn compatibility có chủ ý, chưa phải hành vi adapter hiện hữu.
4. Để hỗ trợ đầy đủ kết quả native, một contract version tiếp theo cần typed
   answered/abstained/unavailable và citation kinds/source snapshots có kiểm chứng.
   Chỉ triển khai sau quyết định H1 riêng với Java/frontend tests; không đổi v1 im lặng.
5. SSE chỉ phát nội dung đã validated; không stream unverified LLM candidates.
   Legacy stream chỉ delta/done, done bắt buộc; không thêm upstream error event
   mà Java chưa hiểu. Health/auth/context/as_of policy cần chốt riêng; adapter
   health path hiện chưa tồn tại, không suy readiness từ actuator/MySQL/Redis/MinIO.

Source references: [`KagClient`](../WebApp/backend/src/main/java/vn/luatgt/integration/KagClient.java),
[`ChatService`](../WebApp/backend/src/main/java/vn/luatgt/service/ChatService.java),
[`LegalUnitService`](../WebApp/backend/src/main/java/vn/luatgt/service/LegalUnitService.java),
[`native Solver`](../kag/legal_solver.py), [`schema packaging`](../WebApp/backend/pom.xml).
OpenSPG cổng28887 không cung cấp các query endpoints này. **H1/H2 NOT_STARTED.**

## Giới hạn kiểm chứng và structural debt

Source xác nhận orchestrator/interface composition theo pinned source. Fresh
canonical 3.10.16/Linux amd64 checks xác nhận local codec/writer adapter,
vendor SDK origins và identity của sáu registry entries (writer, vectorizer,
planner, pipeline, deduce executor, generic generator) trong initialize-first
và preload-builder; init idempotent. Đó là bằng chứng cleanup trước import-order
fix; lỗi preload local solver lịch sử đã được sửa như trên.
Đây là source/registry proof cho paths được kiểm, không là full behavior parity.

Cleanup ban đầu chạy 17 canonical tests PASS (runtime3, schema12, evaluation CLI2),
chưa chạy đủ 46 evaluation +429 regression definitions. Báo cáo import-order
fix tiếp theo ghi 46/46 evaluation và 429/429 regression (475 tests) PASS trong canonical
runtime/network denied, cùng origins/registry của cả ba import orders.
Đây là bằng chứng offline đã lưu ngoài repo, không kiểm lại live ở đây.
Host, canonical subset, graph live và
official legal-domain benchmark không được gộp thành PASS. Xem
[runtime checks](runtime.md#kiểm-tra-offline).

Hướng dẫn chạy và ràng buộc fixtures: [tests](../tests/README.md).
Debt còn lại: lazy import cycles; shared vector
contract đặt trong resilient vectorizer; private upstream coupling; index
verifier/retriever gates khác nhau; Solver metadata support và G2 field allowlist
khác nhau; native answer/Java contract gap. Không xử lý các thay đổi behavior
hoặc package trong cleanup tài liệu. Data/schema/gold/prompts/vendor giữ nguyên;
production WRITE BLOCKED độc lập với mọi documentation/import/smoke result.
