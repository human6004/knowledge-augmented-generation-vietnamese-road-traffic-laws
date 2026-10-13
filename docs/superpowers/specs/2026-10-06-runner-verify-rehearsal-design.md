# D0.5–D0.7: runner, verify và rehearsal C4.3a

Ngày: 2026-10-06. Roadmap: sample-first. Baseline D0.4:
`c7c42de58368b0df98a7f845f0d59075d0437c71`.

Thiết kế phục vụ một CLI/runner dùng chung cho sample và production, kiểm tra
graph read-only và chứng minh resume trên C4.3a. Task này chỉ chạy rehearsal
sample bằng dữ liệu/vector có sẵn. Không gọi embedding API thật, không dựng
production graph, không tạo production project, không thay dataset/schema/C3/vendor.

## Quyết định và phương án

Chọn JSONL streaming + SQLite ledger trong run directory. Stdlib đáp ứng atomic
status, persisted batch state, index identity và resume; dùng lại checkpoint
SQLite của ResilientVectorizer. Không thêm package, broker hoặc service.

Phương án chỉ dùng file receipt cho từng batch có ít code lưu trữ ban đầu, nhưng
phải tự quản lý lookup/uniqueness và recovery nhiều file. SQLite đã có trong
builder và phù hợp kiểm exact identity cùng bounded vector memory.

Rehearsal chọn no-op trên sample hiện có: readback chứng minh payload/vector/
edge khớp trước khi ghi batch thành CONFIRMED_EXISTING. Không tạo bản sao sample
vì sample scope D0.4 gắn project ID 2; không thay policy đó trong task này.

## Entry point và code dùng chung

- Một CLI official: `python -m kag`, các command run/resume/verify gọi library.
- CLI bootstrap bằng `kag.bootstrap.initialize()` trước SDK import; library
  core/offline không tự tạo client/model. API về sau gọi chính library này.
- Runner dùng lại graph_plan, codec, mapping, TARGETS, ResilientVectorizer và
  NativeIntegerKGWriter. Không copy logic ánh xạ/codec/writer vào runner.
- Dùng graph writer SDK đã pin; verify dùng Neo4j HTTP với stdlib urllib và
  query cố định, parameterized. Neo4j driver chưa thuộc lock nên không thêm nó.
- Config official JSON ghi scope/profile/endpoint/database/paths/batch size/
  policy. Credential chỉ lấy env; không lưu secret trong config/status/log.

Các file production dự kiến: `kag/__main__.py`, `kag/runner.py`,
`kag/verify.py`, `kag/run_state.py`, một config example và tài liệu usage.
Regression/integration tests nằm trong tests; chỉ tách file khi có boundary
thực. Đây là dự kiến, không yêu cầu tạo abstraction hoặc factory mới.

## Config, scope và preflight

Scope mặc định DENY. Chỉ nhận sample C4.3a hoặc PRODUCTION đã qua D0.4.
Batch size positive native int. Profile host/container chọn explicit; không
fallback sang KAG global config hoặc đoán host. OpenSPG, Neo4j HTTP, Neo4j URI
và database cấu hình riêng. Auth endpoint không được chứa userinfo/query secret.

Preflight kiểm runtime/vendor/schema/contract, input artifact bytes và identity,
scope/project/endpoint/vector dimension trước vectorizer hoặc graph writer.
Production gọi đầy đủ discover_production_project, không chỉ offline validator.
Mọi mismatch BLOCK, kể cả resume sau khi input/config/target thay đổi.

Sample bind manifest ID 2, name VietRoadTrafficC43A10Pct, namespace
VietRoadTraffic, partition 5 và hash C4.3a hiện có. Node selection dùng partition
`int(sha256(doc_id.encode('utf-8')).hexdigest(),16) % 10`; edge là induced edge
có cả hai endpoint thuộc sample. Source payload đối chiếu C3 trước vector import.

Run directory bắt buộc ngoài repo, không overlap input/old evidence, không
symlink/path escape vào repo. Run ID không được chứa path traversal. C3 và C4
artifact lịch sử chỉ đọc; run sử dụng output/checkpoint riêng.

## Stage contract

Thứ tự: preflight → plan → vectorize → export-artifact → write-nodes →
verify-nodes → write-edges → verify → release. Không nhảy qua barrier.

1. preflight: kiểm đầy đủ cấu hình/identity, acquire lock, pin run identity.
2. plan: đọc C3 JSONL theo batch, chọn scope, lưu source spec vào SQLite hoặc
   JSONL có index. Complete source counts/hash phải khớp scope trước side effect.
3. vectorize: xử lý một batch, dùng lại ResilientVectorizer/checkpoint. Import
   existing vectors có byte hash, model/dimension/source/provenance khớp.
   Rehearsal chỉ replay-existing; thiếu vector/checkpoint BLOCK, không fallback
   sang provider. Direct/CHUNK_AGGREGATED giữ provenance đã được chứng minh.
4. export-artifact: JSONL UTF-8/LF theo batch, completeness/hash/provenance
   receipt được xác nhận trước bất kỳ write stage nào.
5. write-nodes: native writer cho write mode ở gate tương lai; rehearsal no-op
   chỉ xác nhận node đã khớp, không gửi graph write. Không tự sửa mismatch.
6. verify-nodes: đọc toàn bộ node của scope, kiểm exact identity/payload/vector,
   counts/extra/missing/duplicate, rồi mới mở full node barrier của writer.
7. write-edges: chỉ sau full node barrier; no-op xác nhận exact edge/property
   đã có; mismatch BLOCK, không tự upsert trong rehearsal.
8. verify: D0.6 full verification read-only, fingerprint và index contract.
9. release: ghi release/receipt ngoài repo chỉ khi tất cả stage PASS. Rehearsal
   release đánh dấu SAMPLE/NO_OP, không phải production release hoặc D_RELEASE_PASS.

Runner gọi to_subgraphs/write_subgraph theo batch; không gọi helper hiện tại
materialize toàn plan vectorized. Mỗi node/edge batch phải qua scope adapter.
Full plan completeness được chứng minh bằng ledger trước write, full node
readback barrier được mở từ kết quả verify thật, không từ counter tự khai.

## Streaming và bộ nhớ

Không list/tuple toàn bộ vectorized corpus. JSONL iterator → batch → checkpoint/
output; mỗi bước giữ tối đa batch vector. ResilientVectorizer.run được gọi với
một batch, không toàn corpus. Export/verify không tải lại file vector đầy đủ.
Identity/hash/progress có thể index SQLite; vectors lưu trên disk. C3 data-only
preflight hiện có được tái dùng; scale check chứng minh riêng bounded vector
consumption. Batch size cố định theo run identity để resume không đổi boundaries.

## Run state, receipt và exit codes

Mỗi run có status.json, events.jsonl, receipt.json, batches.jsonl và SQLite ledger.
status chứa run_id, scope, stage, state, done, total, started_at, updated_at,
heartbeat, error_code, sanitized_error. State: RUNNING/PASS/ERROR/BLOCKED.
Timestamp UTC ISO-8601; tài liệu/report người dùng dùng Asia/Saigon.

status/receipt ghi temp cùng run dir, flush/fsync rồi os.replace; không temp
trong repo. Heartbeat cập nhật cả trong batch lâu, có shutdown/join rõ ràng.
done/total là đơn vị của stage hiện tại, không cộng node/edge/vector lẫn nhau.

events và batches append-only, mỗi record có sequence, identity, previous_hash,
record_hash. SQLite là state authority, transaction/outbox cho batch confirmation
và event. Resume đối chiếu log đã append để không duplicate khi crash giữa append
và acknowledge. Tail malformed hoặc hash chain sai BLOCK; không truncate/rewrite
audit log. status có thể tái dựng từ ledger/log còn hợp lệ.

receipt atomic chứa scope/project/endpoints không credential, runtime/schema/input/
plan/artifact hashes, per-stage hashes, counters, verify fingerprint, embedding/
write/skip counts, hash chain cuối. PASS stage chỉ publish sau durable outputs.

Exit: 0 PASS, 1 ERROR do runtime/provider/transport, 2 BLOCKED do contract/scope/
lock/integrity. Raw exception/provider body/config secret không vào status/events;
error code allowlist + thông báo cố định, class đã sanitize.

## Resume và writer lock

Batch key bind run identity/stage/ordered source identities/source hash. Stage
PASS có receipt/output còn đúng không chạy lại. Batch CONFIRMED không resend.
Interruption sau external write nhưng trước checkpoint: resume readback trước;
nếu exact state đã có thì CONFIRMED_EXISTING, không gửi lại. Không đoán kết quả
timeout; state khác hoặc không xác định fail closed theo policy.

Lock common ngoài run dirs, theo physical Neo4j database identity đọc từ server;
metadata có endpoint, database name, OpenSPG project + namespace. Endpoint host
và DNS container phải resolve cùng database identity và dùng cùng lock root,
không được tạo hai lock chỉ vì endpoint alias khác nhau. Không chứng minh được
physical identity/common lock root thì BLOCK. Đây là conservative lock cả database
để tránh hai project cùng namespace/storage vô tình dùng hai lock. Chỉ một writer/no-op run
cho một database; có lock thì BLOCK. Lock tạo exclusive, giữ owner token và chỉ
owner xóa khi kết thúc. Lock root phải được chia sẻ với mọi runner cùng graph;
task triển khai single-machine host/container, không hứa distributed fencing.
Không tự phá stale lock; explicit recovery chỉ sau chứng
minh process không chạy và run identity đúng. Không heartbeat-expiry tự takeover.

## Verify read-only

Expected spec/provenance nhập theo batch vào SQLite index. Neo4j scan theo batch
có stable cursor vật lý, không chỉ id vì duplicate id cũng phải phát hiện.
Namespace/type được whitelist từ contract; parameters cho identity/cursor.
Query chỉ đọc, không CREATE/MERGE/SET/DELETE hoặc procedure ghi.

Node: counts theo type, identity/name, duplicate/unexpected/missing, required
property, exact decoded payload, Integer native, vector presence với nonempty
target, dimension 3072, finite vector; cấm degraded/stub và name vector.
Edge: counts theo predicate, exact five-field tuple, payload/provenance properties,
duplicate/missing/unexpected, orphan và degraded endpoint.
Scan cả relations chạm namespace để không bỏ sót edge tới type/namespace ngoài
contract. Unrelated namespace không được coi thuộc target graph.

Index: đúng bốn content targets của schema, VECTOR ONLINE, dimensions 3072;
không lấy index name bất kỳ hoặc _name_vector làm bằng chứng. Provenance artifact
phải là DIRECT/CHUNK_AGGREGATED phù hợp source/model/dimension; chunk metadata
khớp sidecar/hash, không suy luận provenance chỉ từ vector graph.

Fingerprint gồm sorted node identities, sorted edge tuples, decoded semantic
payload/vector hashes, schema và provenance identity. So với expected scope và
kiểm ổn định counts/fingerprint trong verify; divergence BLOCK. Kết quả không sửa
graph, không tạo index hay schema. Restore có thể gọi cùng verify API với scope
và expected release/artifact identity.

## Tests và rehearsal gates

TDD: từng contract có RED trước code, rồi GREEN với SDK behavior thật và boundary
fake chỉ cho network/provider. Tests không gọi embedding API hoặc production write.
237 baseline tests phải tiếp tục PASS trong CPython 3.10.16/runtime image D0.2.

Runner regression: stage order/barrier, bounded iterator/batch, resume stage/
batch/ambiguous ack, artifact mutation, hash chain, atomic status, heartbeat,
sanitized error, exit codes, graph lock contention/stale lock, D0.4 production
negative cases. CLI integration kiểm cùng library và process exit/status files.

Verify regression: positive nodes/edges/vector/index/fingerprint; missing/extra/
duplicate, orphan/stub/degraded, required fields, wrong/NaN vector, missing/offline/
wrong-dimension index, semantic/provenance/hash mismatch, read-only boundary.

Chỉ sau offline unit/integration PASS mới live read-only rehearsal C4.3a:
7.495 nodes (14 documents/7.040 units/441 signs), 8.180 edges, 7.936 candidates,
7.858 required nonempty, 78 skipped empty TrafficSign.ten, 14 CHUNK_AGGREGATED.
Existing artifact/checkpoint/provenance được kiểm hash trước dùng. Baseline và
postrun fingerprint/count phải khớp; embedding API calls 0, graph writes 0.

Mô phỏng interruption ở durable batch boundary ngoài graph, resume cùng run ID;
chứng minh confirmed work không resend qua batch counters/events/readback.
Run process thứ hai cùng graph lock phải exit 2. Release/status/events/receipt
và hash chains kiểm exact, không chỉ kiểm file tồn tại.

Evidence/probe/log/report/run ngoài repo tại
`D:/study/caoDATA-workspace/d0.5-d0.7-runner-verify-rehearsal/` và
`D:/study/caoDATA-workspace/runs/<run-id>/`. Không dùng repo/.cache.
Không chạy Retrieval/Solver/API/WebApp, full production, reset DB hoặc xóa volume.

## Tiêu chí hoàn tất

D0.5 PASS khi runner/streaming/state/resume/lock/fail-closed/exit tests PASS.
D0.6 PASS khi verify node/edge/vector/index/fingerprint/provenance positive và
negative cases PASS, read-only được chứng minh.
D0.7 PASS chỉ sau live sample no-op/verify/resume/lock và exact expected counts,
hashes, zero embedding/write, production untouched. Chưa chạy live không gọi PASS.
Final report theo mẫu user, phân loại permanent/evidence, git status cuối.
Sau PASS chỉ nêu bước roadmap tiếp theo, không tự chạy.
