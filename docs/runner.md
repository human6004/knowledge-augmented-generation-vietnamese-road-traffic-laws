# Builder và runner

Runner dựng/kiểm graph theo batch, giữ tiến độ để dừng và tiếp tục an toàn. Không chạy lúc startup. [Runtime](runtime.md) quy định Python/SDK; [schema](schema.md) và [backend identity](backend-identity.md) quy định dữ liệu/target.

## Điều khiển từ Pipeline ADMIN

Spring Boot kiểm ADMIN, gửi control token riêng tới `openspg-server:8010`; BuilderControl chạy Runner trong một thread, không dùng Docker Socket.

Phần **Dựng đồ thị & vector · Builder thật** có status/tiến độ/mã lỗi. Build/Stop/Resume chỉ mở khi backend cho phép. Stop đợi batch/readback/checkpoint; Resume cùng run ID sau stop sạch. Delete vô hiệu hóa; chưa có stream log/lịch sử job đầy đủ. Catalog Demo không chạy Runner.

**Mặc định Builder BLOCKED.** Worker nhận `FRESH_SAMPLE/WRITE/replay-existing` với grant biệt lập, hoặc `PRODUCTION/WRITE` với confirmation gắn project/namespace/ID/plan đã pin. Runner vẫn kiểm nguồn, vector, identity và GraphLock trước ghi; trạng thái quyền đã cấu hình không chứng minh ghi thành công.

Trong **Đầu vào & điều kiện Build**, **Kiểm tra nguồn** xác thực C3 manifest, checksum, schema, ID và quan hệ; trả số node/cạnh và hash kế hoạch. Kết quả bị hủy khi nguồn hoặc cấu hình đổi. Kiểm nguồn không gọi provider/graph, không xác minh target và không bật Build. **Tải lại đầu vào** đọc trạng thái kiểm hiện tại; preflight target/vector chỉ do Runner thực hiện. API kiểm nguồn chỉ nhận ADMIN, không nhận file, đường dẫn hoặc quyền từ trình duyệt.

Snapshot đầu vào chỉ kiểm file có mặt, không hash vector lớn trong request HTTP; `NOT_CHECKED` nghĩa là chưa kiểm checksum. Kiểm nguồn chạy nền và chỉ xác thực nguồn C3, còn vector được Runner kiểm trước Build. Cache giao diện theo cấu hình và metadata inode/kích thước/mtime/ctime; sau phục hồi bảo toàn metadata, bấm **Kiểm tra nguồn** lại. Runner luôn kiểm checksum thật trước dispatch, không dùng cache giao diện làm quyền ghi.

## Config

Copy [runner.example.json](../kag/config/runner.example.json) ra ngoài repo; template mặc định DENY, cần inputs/hashes/target thật. [runner.py](../kag/runner.py) là nguồn chuẩn validator, từ chối unknown fields.

- `scope`: `C4_3A_MANIFEST_SAMPLE` chỉ NO_OP/replay trên manifest đã pin; `FRESH_SAMPLE` chỉ subset 1–128 nodes, 1–256 edges, batch ≤32, replay. `PRODUCTION` dùng toàn corpus đã pin; WRITE cần confirmation gắn đúng project/namespace/ID/plan, backend identity và GraphLock. Không dùng SAMPLE cho full graph.
- `runtime_location`, `endpoints`, `database`, project/name/namespace: explicit và khớp discovery; không fallback endpoint hoặc dùng ID/container cũ. Container dùng OpenSPG loopback và DNS Neo4j theo deployment. Điều kiện thử biệt lập: [backend identity](backend-identity.md#xác-minh-đường-đi-và-database).
- `write_mode`: NO_OP/WRITE; `vector_policy`: replay/provider trong giới hạn scope. `model_identity=endpoint|model`, dimension 3072; replay không fallback provider. Provider config/fallback phải khớp provenance.
- `paths`: inputs và run/lock roots tuyệt đối; roots ngoài repo, không chồng inputs. `input_sha256` bind đúng bytes từng non-null input, không gồm roots. C3 JSONL/`plan.sha256` nằm cạnh manifest.
- `credential_env`: tên biến secrets, không phải giá trị; credentials chỉ trong RAM. Confirmation/proof không tự mở quyền production.

Trong Compose: config `/builder-input/runner.json`, run root `/builder-runs`, lock `/run/kag-locks`; giữ mounts theo [Docker](../docker/README.md#storage-và-secrets).

## Chạy CLI

**Bước 1:** chuẩn bị config/inputs/credentials và mounts ngoài Git, dùng runtime chuẩn. `/external/runner.json` bên dưới là đường ví dụ, thay bằng config đã chuẩn bị.

**Bước 2:** chọn đúng thao tác:

```sh
python -B -m kag run --config /external/runner.json --run-id sample-run
python -B -m kag resume --config /external/runner.json --run-id sample-run
python -B -m kag verify --config /external/runner.json --run-id sample-run
```

Kết quả: status/artifacts trong run directory. `verify` không sửa graph/index nhưng ghi verification/receipt. Exit 0: hoàn tất; 1: lỗi runtime/transport/provider; 2: bị chặn scope/lock/config/integrity. Đọc `stage/error_code`; không log credentials/source/exception body.

## Source-only validation

[source-only.example.json](../kag/config/source-only.example.json) dùng `SOURCE_ONLY_DRY_RUN/NO_OP`; thay hash zero bằng byte hash thật và đặt run root ngoài repo. Chỉ nhận fields trong template, không endpoints/provider/WRITE.

Luồng source: preflight → plan → source-nodes → source-edges → source-verify → source-complete. Không mở graph/provider/writer; `graph_verified=false`, counters zero. `verify` chỉ nhận source run đã hoàn tất; lock theo run directory.

Validation/resume dùng disk SQLite index, không nạp toàn corpus vào dict. Đặt TMPDIR ngoài repo nếu caller không có run directory. Kiểm semantic hashes/input/golden; không sửa nguồn để qua gate. O(batch) payload không phải cam kết peak RAM của full production vectors.

## Stage và readback

Graph: preflight → plan → vectorize → export-artifact → write-nodes → verify-nodes → write-edges → verify → release. Không cộng counters các stage dùng đơn vị khác nhau.

- Replay kiểm model/dimension/source, provenance/chunk sidecar/checkpoint; thiếu job/vector thì chặn. Provider dùng vectorizer upstream, tắt name generation.
- Export fsync/publish atomic trước ghi. NO_OP không tạo writer; WRITE dùng scoped NativeIntegerKGWriter, node barrier và live backend guard.
- Verify kiểm IDs/payload, native Integer sau outer decode, vectors hữu hạn, duplicate/extra/missing/endpoints/provenance và bốn VECTOR indexes ONLINE. Hai scans/fingerprint phát hiện graph đổi; chỉ canonical signed zero, không làm tròn vectors.

## Resume, trạng thái và lock

Run chứa ledger/expected SQLite, checkpoint, batches/export, `status.json`, `events.jsonl`, `batches.jsonl`, `receipt.json`. Status/receipt atomic, audit append-only có hash chain/outbox; tail hỏng/torn bị chặn, không truncate.

Resume giữ config/input/target/model/batch boundaries, kiểm artifacts và đọc lại node barrier/graph. Batch CONFIRMED không gửi lại writer/vectorizer. Graph INTENT chưa confirmed chỉ đọc lại; thiếu/khác/không chắc thì BLOCKED, **không resend mù sau timeout**.

`graph_writes/embedding_calls` đếm durable dispatch intents, không phải ACK hay số mutations. Crash có thể đếm dư một; timeout không xác nhận remote completion.

GraphLock khóa theo **physical databaseID**, mọi writer cùng DB trên một host dùng chung volume local `KAG_GRAPH_LOCK_VOLUME`. Kernel kiểm mount disk writable đúng root volume; private directory/tmpfs/readonly bị chặn. Không phải distributed fencing, không chặn admin/writer ngoài cơ chế.

Chỉ owner release khi thoát sạch; crash giữ stale lock. Không force-unlock hoặc takeover theo heartbeat. Trước phục hồi thủ công, kiểm owner/process/run/target và tình trạng ghi; không sửa ledger/receipt/hash để ép tiếp tục.

Receipt ghi identity/counters/artifact/audit anchors, không cấp serving authority hoặc quyền production. Resume tạo session mới và xác minh target live. Bảo trì giữ run/state/lock theo [UPDATE](UPDATE.md); [tests](../tests/README.md) kiểm offline bằng fixtures.
