# Vận hành Builder, resume và verification

CLI `python -B -m kag` gọi `kag.runner.run` hoặc `kag.runner.verify_run`.
Legal answering và dataset CLI có entrypoints riêng trong
[kiến trúc](architecture.md#entrypoints-và-lệnh-ổn-định). `--help` không nạp SDK;
lệnh dùng SDK bootstrap theo [runtime](runtime.md).

```sh
python -B -m kag run --config /evidence/runtime.json --run-id sample-validation
python -B -m kag resume --config /evidence/runtime.json --run-id sample-validation
python -B -m kag verify --config /evidence/runtime.json --run-id sample-validation
```

`/evidence/runtime.json` là placeholder config ngoài Git; operator chuẩn bị inputs
và mounts trước chạy. `verify` đọc graph, ghi verification/receipt vào run directory
ngoài repo. Exit 0 = PASS, 1 = ERROR runtime/transport/provider, 2 = BLOCKED
scope/lock/config/integrity. Xem `stage/error_code` trong status; lỗi chỉ lưu thông
báo cố định, không exception body, source text hoặc credential.

## Source-only validation

[kag/config/source-only.example.json](../kag/config/source-only.example.json)
dùng `scope=SOURCE_ONLY_DRY_RUN`, `write_mode=NO_OP`. Điền SHA-256 byte thật của
`c3_manifest` và `run_root` ngoài repo; example SHA toàn zero sẽ bị chặn.
Chỉ nhận scope/write_mode/paths/input_sha256/batch_size/heartbeat_seconds;
endpoint, project, vector/provider/checkpoint hoặc WRITE fields bị từ chối.

Luồng: preflight → plan → source-nodes → source-edges → source-verify →
source-complete. Không tạo graph clients/provider/writer hoặc đọc graph.
Receipt có `kind=SOURCE_ONLY_DRY_RUN`, `graph_verified=false`, dispatch counters
zero; không có graph verify/release. `verify` chỉ nhận source run đã hoàn tất.
Lock theo run directory; không lấy database lock.

C3 JSONL validation dùng SQLite index trên disk, cache 2 MiB. Index seal
read-only, byte hash bind proof revalidation. Run giữ `source-validation.sqlite3`;
caller không có run directory dùng temporary index ngoài repo, đặt TMPDIR ở
workspace ngoài Git. Semantic plan hash giữ canonical JSON năm fields;
không đổi golden/schema/input hoặc production proof. Production preflight dùng
lazy disk mappings, không copy toàn corpus thành dict.

Source resume đối chiếu ledger/durable outbox qua TEMP SQLite index, kể cả intents
chưa flush. Mỗi key chỉ một INTENT → CONFIRMED; foreign graph stages, batch
deleted/extra/changed/reconfirmed đều bị chặn. O(batch) source payload không
chứng minh peak RSS hoặc bộ nhớ full production vectors.

## Config

Copy [runner.example.json](../kag/config/runner.example.json) ra ngoài repo.
Template mặc định DENY; điền scope, policy, inputs và SHA-256 thật. Unknown fields
bị từ chối.

- `scope`: `C4_3A_MANIFEST_SAMPLE`, `FRESH_SAMPLE` hoặc `PRODUCTION`; thiếu = DENY.
  C4.3a giữ ID 2, `VietRoadTrafficC43A10Pct`, namespace `VietRoadTraffic`,
  chỉ `NO_OP/replay-existing`. Runner chặn `PRODUCTION WRITE`.
  C4.3a chọn partition 5 theo `int(sha256(doc_id.encode('utf-8')).hexdigest(),16) % 10`;
  chỉ giữ edges có cả hai endpoints thuộc sample, đối chiếu exact manifest.
- `FRESH_SAMPLE`: chỉ target `FreshSample_*`, manifest C3 subset có 1–128 nodes
  và 1–256 edges, endpoints thuộc subset, batch ≤ 32, `replay-existing`.
  WRITE cần backend cô lập và manifest target khớp physical DB/runtime/volume
  theo [writer scope](production-writer-scope.md); không dùng scope này cho full graph.
- `runtime_location`: `host` hoặc `container`; endpoints explicit, không fallback.
  `endpoints` có đúng `openspg`, `neo4j_http`, `neo4j_uri`, không
  userinfo/query/fragment. OpenSPG sample bắt buộc loopback.
- `database`, `project_id`, `project_name`, `namespace`: khớp discovery.
  `vector_dimensions` là native integer 3072; `batch_size` là positive native int;
  `heartbeat_seconds` là positive finite number.
- `write_mode`: `NO_OP` hoặc `WRITE`; thiếu = DENY.
  `vector_policy`: `replay-existing` hoặc `provider`, với giới hạn sample ở trên.
  `model_identity` là `endpoint|model`, không credential.
  `embedding_model=null` khi replay; provider nhận đúng
  `{type: openai, base_url, model, timeout}`, khớp model_identity.
- `fallback_config`: cấu hình bounded của ResilientVectorizer; aggregate replay
  phải khớp enabled/version/size/overlap/depth trong provenance.
- `confirmation`: null cho C4.3a; production dùng exact confirmation scope.
  Preflight bind C3/schema/input bytes và
  [backend session/proof](backend-identity.md) với writer/GraphLock.
  Host/port/config khớp không thay live proof; proof không mở production WRITE.
- `paths`: absolute `c3_manifest`, `sample_manifest`, `vector_artifact`,
  `provenance`, `chunk_manifest`, `source_checkpoint`, `run_root`, `lock_root`.
  Provider có thể dùng null cho replay inputs; production sample_manifest có thể
  null. C3 JSONL và `plan.sha256` nằm cạnh c3_manifest; roots không overlap repo/inputs.
- `input_sha256`: đúng một byte hash cho từng non-null input, không gồm hai roots.
  C3/schema/input validator kiểm thêm các canonical checksums.
- `credential_env`: tên biến `neo4j_username`, `neo4j_password`, `embedding_key`,
  không phải giá trị secret. Replay không cần embedding key; credential chỉ ở RAM.

Host profile có endpoints mẫu `http://127.0.0.1:28887`,
`http://127.0.0.1:27474`, `bolt://127.0.0.1:27687`. Common lock guard hiện yêu cầu
Linux container và mount xác minh bên dưới; host Python trực tiếp không thay guard.

Container profile dùng OpenSPG loopback `http://127.0.0.1:8887` khi chia sẻ đúng
network namespace OpenSPG; Neo4j `http://openspg-neo4j:7474`,
`bolt://openspg-neo4j:7687`. Kiểm alias/network/database của deployment thật,
không dùng container ID hoặc receipt cũ làm cấu hình hiện tại.
Private stack cần transport private tin cậy được library caller truyền vào;
CLI JSON riêng không chọn transport private hoặc cấp backend proof.

Chuẩn bị credentials trong environment riêng; không paste vào command/log.
Không recreate stack hoặc đổi volumes để chạy runner.

## Stage và bộ nhớ

Thứ tự cố định: preflight → plan → vectorize → export-artifact → write-nodes →
verify-nodes → write-edges → verify → release.

Counters theo stage: preflight một identity; plan nodes + edges; vectorize nodes;
export-artifact vector batches; write-nodes/verify-nodes nodes; write-edges edges;
verify/release một gate. Không cộng các đơn vị khác nhau.

Vector JSONL vào disk index; ResilientVectorizer xử lý một source batch.
Checkpoint/batch/export thuộc run ngoài repo. O(batch) vectors không cam kết
chỉ một batch object tồn tại ở boundary. Replay kiểm source/model/dimension,
provenance/chunk sidecar và checkpoint trước import; thiếu job/vector thì BLOCK,
không fallback provider. Provider dùng BatchVectorizer/OpenAIVectorizeModel
đã pin, tắt name generation.

Export fsync và publish atomic JSONL/hash receipt trước graph stages.
NO_OP đọc lại exact từng batch, không tạo writer. WRITE được cho phép dùng scoped
NativeIntegerKGWriter, full node barrier và live backend guard.

Verifier không sửa graph/index. Kiểm identities/payload, native Integer sau
outer JSON decode, vectors hữu hạn 3072, duplicate/extra/missing, endpoints,
provenance và bốn content VECTOR indexes ONLINE. Hai scans/fingerprint phát hiện
graph đổi trong kiểm tra. Neo4j HTTP boundary bỏ đúng một outer JSON layer;
id/vectors giữ nguyên. Text giống số hoặc double encoding bị chặn; JSON Text
storage không được gọi là native Neo4j Integer. Fingerprint chỉ canonical hóa
signed zero (`-0.0/0.0`); component nonzero so exact, không tolerance/quantization.

## Resume, trạng thái và lock

`<run_root>/<run-id>` chứa ledger/expected SQLite, checkpoint, JSONL batches/export,
`status.json`, `events.jsonl`, `batches.jsonl`, `receipt.json`.
Status/receipt atomic, timestamps UTC. Heartbeat tiếp tục trong batch lâu;
publish lỗi được báo tại boundary kế tiếp. Stage result, PASS status và outbox
commit cùng transaction. Events/batches append-only có sequence/previous_hash/
record_hash; resume đối chiếu SQLite outbox. Tail sai/torn bị chặn, không truncate.

Resume giữ config/input/target/model/batch boundaries. CONFIRMED không gọi lại
vectorizer/writer nhưng output hash vẫn phải đúng. Completed stages kiểm durable
artifacts; node barrier/full verify đọc lại. Graph write INTENT chưa confirmed
chỉ đọc lại: exact existing state mới confirm; thiếu/khác/không chắc thì BLOCK,
không blind resend sau timeout.

`graph_writes/embedding_calls` đếm durable dispatch intents trước adapter,
giữ qua crash/resume. Timeout không xác nhận remote completion; crash giữa persist
intent và dispatch có thể đếm dư một. Counters không phải số ACK/remote mutations.
NO_OP/replay zero còn được guard không gọi writer/provider chứng minh.

Lock theo physical databaseID, không endpoint alias hoặc project counter.
Guard single-machine hiện chỉ nhận `/run/kag-locks`, bind exact
`D:/study/caoDATA-workspace/runs/.graph-locks` ngoài Git; kernel mountinfo phải
xác nhận filesystem 9p, drive D và đúng root. Đây là ràng buộc mã nguồn hiện tại,
không phải placeholder. Mọi runner cùng DB dùng mount này; layout khác BLOCK
đến khi common storage được chứng minh. Không phải distributed fencing.

Lock có owner token/PID/hostname/run/project/endpoint identity. Có lock thì BLOCK.
Handled exit chỉ owner release; hard crash giữ stale lock. Không force-unlock
hoặc heartbeat-expiry takeover; kiểm owner/process/run identity trước manual recovery.

Library `stop_after_batch=(stage, ordinal)` dùng test/rehearsal, ordinal từ 1.
Nó ghi ERROR/INTERRUPTED sau durable confirmation và release owned lock.
CLI không có skip-stage/force-unlock. Graph `verify` cần run đã export, chia sẻ
preflight/artifact checks, ghi `verification.json` và cập nhật receipt/audit anchors.

Release C4.3a là `SAMPLE/NO_OP`; fresh sample giữ `FRESH_SAMPLE/<write_mode>`.
Receipt chứa runtime/schema/C3/input/config hashes, counters, artifact/fingerprint
và audit chain anchors. Runner receipt không cấp serving authority hoặc quyền
production. Serving proof/rebind/provider budget theo [INSTALL](INSTALL.md) và
[UPDATE](UPDATE.md). Bối cảnh chọn ledger/rehearsal nằm ở
[thiết kế](superpowers/specs/2026-10-06-runner-verify-rehearsal-design.md).

## Regression offline

Lệnh suites, runtime canonical và mount cho tests nằm tại
[hướng dẫn kiểm thử](../tests/README.md). Chạy mỗi discovery trong process riêng,
network denied; network/provider dùng fixtures. Offline checks không tự chạy
sample live hoặc cấp quyền graph/provider.
