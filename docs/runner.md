# Runner và verify KAG

Entry point duy nhất: `python -B -m kag`. CLI gọi `kag.runner.run` hoặc
`kag.runner.verify_run`; API tương lai dùng chính các hàm này. `--help` không
khởi tạo SDK. Command thật bootstrap CPython 3.10.16/Linux amd64 và vendor pin
trước import SDK; xem [runtime](runtime.md).

```sh
python -B -m kag run --config /evidence/sample.json --run-id sample-rehearsal
python -B -m kag resume --config /evidence/sample.json --run-id sample-rehearsal
python -B -m kag verify --config /evidence/sample.json --run-id sample-rehearsal
```

Exit 0 = PASS, 1 = ERROR runtime/transport/provider, 2 = BLOCKED
scope/lock/config/integrity. Lỗi lưu thông báo cố định; không lưu exception body,
source text lỗi hoặc credential. Xem status của run để biết stage/error_code.

## D0.8 source-only dry-run

`kag/config/source-only.example.json` là config riêng, explicit
`scope=SOURCE_ONLY_DRY_RUN`, `write_mode=NO_OP`. Điền byte SHA-256 của
`c3_manifest` và external `run_root`; example SHA toàn zero sẽ BLOCK.
Config này chỉ nhận scope/write_mode/paths/input_sha256/batch_size/heartbeat_seconds.
Endpoint, project, vector/provider/checkpoint hoặc WRITE fields đều bị từ chối.
Dùng cùng CLI `run`, `resume`, `verify`; source `verify` chỉ nhận run đã hoàn tất.

Luồng source: preflight → plan → source-nodes → source-edges → source-verify →
source-complete. Không tạo graph clients/provider/writer hoặc graph readback.
Receipt có `kind=SOURCE_ONLY_DRY_RUN`, `graph_verified=false`, các dispatch counters
zero; không có graph verify/release stage. Source PASS không phải graph release.
RunState/status/events/receipt/batches/ledger và controlled stop_after_batch dùng
cùng cơ chế official. Lock local theo run directory; không lấy graph database lock.
Source resume từ chối foreign graph stages/batches; đối chiếu ledger với durable
outbox bằng TEMP SQLite index, nhận cả chưa-flush intents. Mỗi key chỉ có một
INTENT → CONFIRMED; deleted/extra/changed/reconfirmed batches BLOCK trước replay.

C3 validation đọc JSONL từng record vào SQLite. Payload/identity/hash/endpoint
index trên đĩa, SQLite cache 2 MiB; index seal read-only và byte hash được bind
vào proof revalidation. Source mode giữ `source-validation.sqlite3` trong run;
callers không có run directory dùng temporary index ngoài repo (đặt TMPDIR vào
workspace). Semantic plan hash vẫn canonical JSON cùng năm fields như C3 cũ,
encoder phát từng record; không đổi golden/schema/input hoặc production proof.
Full production preflight giữ lazy disk mappings, không copy thành corpus dict.

Source batching giữ O(batch) payload; RSS gồm fixed Python/SDK/SQLite overhead.
Full source memory proof không chứng minh full production vector memory.
Production WRITE vẫn BLOCK độc lập với backend identity proof D0.10.

## Config

Copy `kag/config/runner.example.json` ra ngoài repo. Example mặc định DENY;
phải điền policy và SHA-256 thực trước chạy. Unknown fields bị từ chối.

- `scope`: `C4_3A_MANIFEST_SAMPLE` hoặc `PRODUCTION`; thiếu = DENY.
- `runtime_location`: `host` hoặc `container`; endpoint explicit, không fallback.
- `endpoints`: `openspg`, `neo4j_http`, `neo4j_uri`. Không userinfo/query/fragment.
  Profile host dùng loopback; sample localhost OpenSPG là yêu cầu C4 giữ nguyên.
- `database`, `project_id`, `project_name`, `namespace`: đúng metadata đã discovery.
  Sample chỉ ID 2, `VietRoadTrafficC43A10Pct`, `VietRoadTraffic`.
- `vector_dimensions`: native integer 3072. `batch_size`: positive native integer.
  `heartbeat_seconds`: positive finite number.
- `write_mode`: `NO_OP` hoặc `WRITE`; thiếu = DENY. Sample chỉ NO_OP.
- `vector_policy`: `replay-existing` hoặc `provider`; sample chỉ replay-existing.
- `model_identity`: credential-free `endpoint|model`. `embedding_model`: null
  khi replay; provider nhận đúng `{type: openai, base_url, model, timeout}`.
- `fallback_config`: cấu hình bounded của ResilientVectorizer. Aggregate replay
  phải khớp metadata cũ, gồm enabled/version/size/overlap/depth.
- `confirmation`: null cho sample; production dùng confirmation D0.4 exact.
  Production vẫn resolve name + namespace rồi kiểm ID độc lập và bind C3/schema/
  input bytes; xem [production scope](production-writer-scope.md).
  Runner hiện BLOCK mọi `WRITE`, kể cả khi backend identity đã PROVEN.
  Preflight yêu cầu [backend identity session](backend-identity.md) cùng writer và
  GraphLock; matching host/port/config không đủ. D1 phải re-prove production live
  và xét execution gate riêng. D0.4 vẫn bắt buộc; không có config flag mở WRITE.
- `paths`: absolute `c3_manifest`, `sample_manifest`, `vector_artifact`,
  `provenance`, `chunk_manifest`, `source_checkpoint`, `run_root`, `lock_root`.
  Provider có thể dùng null cho replay inputs; production sample_manifest có thể null.
  C3 JSONL và plan.sha256 nằm cạnh c3_manifest. Run không overlap repo/input cũ.
- `input_sha256`: SHA-256 cho từng non-null input path, không gồm hai root.
  Đây là byte hashes, không hash JSON đã parse. C3 checksums/schema/input chuẩn
  còn được validator hiện có kiểm riêng.
- `credential_env`: tên env `neo4j_username`, `neo4j_password`, `embedding_key`;
  không phải giá trị secret. Replay không cần embedding_key. Credential chỉ ở RAM.

Native host profile có endpoint sample `http://127.0.0.1:28887`,
`http://127.0.0.1:27474`, `bolt://127.0.0.1:27687`. Deployment hiện tại yêu cầu
runner Linux container với common lock mount đã chứng minh; host Python trực tiếp
sẽ BLOCK nếu không có mount này.

Container sample chia sẻ network namespace của `kag-openspg-server-1`:
OpenSPG `http://127.0.0.1:8887`, Neo4j HTTP `http://openspg-neo4j:7474`,
URI `bolt://openspg-neo4j:7687`, database `vietroadtraffic`.
Phải kiểm alias/network đúng trên deployment trước dùng.

```powershell
rtk docker run --rm --platform linux/amd64 --network container:kag-openspg-server-1 `
  --mount "type=bind,source=D:/study/knowledge-augmented-generation-vietnamese-road-traffic-laws,target=/workspace,readonly" `
  --mount "type=bind,source=D:/study/caoDATA-workspace,target=/external,readonly" `
  --mount "type=bind,source=D:/study/caoDATA-workspace/runs,target=/runs" `
  --mount "type=bind,source=D:/study/caoDATA-workspace/runs/.graph-locks,target=/run/kag-locks" `
  --mount "type=bind,source=D:/study/caoDATA-workspace/d0.5-d0.7-runner-verify-rehearsal,target=/evidence" `
  --env KAG_NEO4J_USERNAME --env KAG_NEO4J_PASSWORD `
  sha256:25190ba8f51e8d158db0910858e9de3de1e1324d29d8b236d4d120268fa7bf33 `
  -m kag run --config /evidence/sample.json --run-id sample-rehearsal
```

Prepare credentials trong environment riêng; không paste giá trị vào command/log.
Không recreate stack hoặc đổi volumes để chạy runner.

## Stage và bộ nhớ

Stage order cố định: preflight → plan → vectorize → export-artifact →
write-nodes → verify-nodes → write-edges → verify → release.

Preflight một identity; plan đếm source nodes + edges; vectorize đếm nodes;
export-artifact đếm vector batches; write-nodes/verify-nodes đếm nodes;
write-edges đếm edges; verify/release đếm một gate. Counters không cộng lẫn stage.

Source-only C3 validation giữ behavior D0.4. Vector JSONL đọc từng record vào disk
index; ResilientVectorizer chỉ nhận một source batch. Run-owned checkpoint và
batch files giữ vectors ngoài repo. Không list toàn corpus vectorized.
Memory vector bounded O(batch); cached/export objects có thể cùng tồn tại ở
batch boundary. Chưa cam kết peak live vector objects đúng một batch.
Replay kiểm source/model/dimension, provenance/chunk sidecar và checkpoint cũ
read-only trước import; missing job/vector BLOCK, không gọi provider fallback.
Provider dùng BatchVectorizer/OpenAIVectorizeModel đã pin, bỏ name generation.

Export fsync + atomic publish JSONL hoàn chỉnh/hash receipt trước graph stages.
NO_OP exact readback mỗi batch, không tạo graph writer. Dispatch nội bộ dùng scoped
NativeIntegerKGWriter với full node barrier và live backend guard; public WRITE
vẫn BLOCK theo execution gate ở trên.
Verify không sửa graph hoặc tạo index: exact identities/payload/3072 finite vectors,
duplicate/extra/missing, native Integer, endpoints, provenance và bốn content
VECTOR indexes ONLINE. Hai scans/fingerprint phát hiện graph đổi trong kiểm tra.
Neo4j HTTP boundary bỏ đúng một outer JSON layer của OpenSPG storage; id/vectors
giữ nguyên. Integer phải là native int sau layer này, Text số hoặc double encoding
vẫn BLOCK. Không tuyên bố JSON Text storage là native Neo4j Integer.
Vector fingerprint canonical hóa riêng signed zero (`-0.0`/`0.0`); mọi component
nonzero vẫn so exact, không tolerance hoặc quantization.

## Resume, trạng thái và lock

Run ở `/runs/<run-id>` gồm `ledger.sqlite3`, `expected.sqlite3`, checkpoint, JSONL batch/export,
`status.json`, `events.jsonl`, `batches.jsonl`, `receipt.json`.
Status/receipt ghi atomic; timestamps UTC. Heartbeat tiếp tục khi batch lâu.
Lỗi publish heartbeat được báo main tại boundary kế tiếp, không im lặng PASS.
Stage result/PASS status/PASS outbox commit cùng transaction. Lệnh verify cập
nhật receipt để audit anchors khớp tail logs.
Events/batches append-only, sequence + previous_hash + record_hash, SQLite outbox
đối chiếu khi resume. Sai/torn tail BLOCK, không truncate log.

Resume phải cùng config/input/target/model/batch boundaries. CONFIRMED batches
không gọi lại vectorizer/writer; output hash còn phải đúng. Completed stages kiểm
durable artifacts; node barrier/full verify đọc lại để tránh release graph đã đổi.
INTENT của graph write chưa confirmed chỉ readback: exact existing state thì
confirm, thiếu/khác/không chắc thì BLOCK; không blind resend sau timeout.
`graph_writes`/`embedding_calls` đếm durable dispatch intents trước gọi adapter,
giữ nguyên khi crash/resume. Remote completion có thể chưa chắc sau timeout;
crash giữa persist intent và dispatch có thể đếm dư một, không biến call cũ thành 0.
Không coi counters này là số ACK/remote mutations chính xác. NO_OP/replay zero
được chứng minh thêm bằng guard không gọi writer/provider.

Lock theo server physical databaseID, không theo endpoint alias/project counter.
Deployment single machine hiện tại chỉ nhận `/run/kag-locks`, bind exact
`D:/study/caoDATA-workspace/runs/.graph-locks`; kernel mountinfo phải xác nhận 9p
drive D và đúng root. Mọi runner cùng DB phải dùng mount này. Layout khác BLOCK
cho đến khi common storage được chứng minh; đây không phải distributed fencing.
Lock có owner token, PID/hostname/run/project/endpoint identity. Có lock thì BLOCK.
Handled exit chỉ owner release; hard crash giữ stale lock. Không force-unlock hoặc
heartbeat-expiry takeover. Điều tra owner/process/run identity trước manual recovery.

Library `stop_after_batch=(stage, ordinal)` chỉ dùng test/rehearsal; ordinal từ 1.
Nó ghi ERROR/INTERRUPTED sau durable confirmation và release owned lock. CLI không
có skip-stage/force-unlock flag. `verify` cần run đã export; chia sẻ preflight,
artifact checks và read-only verifier, ghi `verification.json` ngoài repo.

Release sample là `SAMPLE/NO_OP`; không phải production release hoặc D_RELEASE_PASS.
Receipt chứa runtime/schema/C3/input/config hashes, counters, artifacts/fingerprint
và audit chain anchors. Production deployment/remote schema gate vẫn thuộc D1;
task D0.5–D0.7 không cho phép chạy production thật.

## Regression offline

Trong runtime digest trên, mount repo read-only và common lock như ví dụ, dùng
`--network none`; chạy riêng từng discovery process để tránh fixture collision:

```sh
python -B -m unittest discover -s tests/runner -v
python -B -m unittest discover -s tests/schema -v
python -B -m unittest discover -s tests/builder -v
python -B -m unittest discover -s tests/runtime -v
```

Tests dùng fixture network/provider; không socket/embedding API thật hoặc production
graph. Logs/probes/reports ngoài repo. Chỉ live C4.3a NO_OP sau toàn bộ offline PASS.
