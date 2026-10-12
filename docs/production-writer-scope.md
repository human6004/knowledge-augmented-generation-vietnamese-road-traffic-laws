# Writer scope và execution authority

Writer scope bind target, source payload và quyền dispatch. Public runner chặn
`PRODUCTION WRITE`; config hợp lệ, source-only PASS hoặc backend identity PROVEN
không mở gate. `FRESH_SAMPLE` là nhánh WRITE giới hạn trên backend cô lập, không
cấp quyền full production build.

## Scope và default

- `C4_1_SMOKE`: project/ID synthetic được discovery và verify; chỉ ID dưới
  prefix smoke. Cleanup chỉ được xóa exact synthetic objects.
- `C4_3A_MANIFEST_SAMPLE`: exact project `VietRoadTrafficC43A10Pct`, ID `2`,
  namespace `VietRoadTraffic`, partition `5`, node/edge identities theo manifest
  C4.3a. Public runner chỉ `NO_OP/replay-existing`; không delete dữ liệu thật.
- `FRESH_SAMPLE`: subset C3 theo sealed manifest, 1–128 nodes, 1–256 edges,
  endpoints thuộc subset; project `FreshSample_*`, replay-existing, batch ≤ 32.
  Target phải khớp project/namespace/database/physical ID/runtime identity.
  Backend private cô lập phải bind đúng volume `kag-s8-*_openspg-neo4j-data`;
  database `vietroadtraffic` bắt buộc volume revision `-fresh-*`.
  Không delete hoặc đổi source payload; không dùng scope này để ghi full graph.
- `PRODUCTION`: target khác sample/smoke, exact C3, không delete.
- Thiếu scope hoặc scope lạ: DENY WRITE. `WriterConfig` không tự chọn smoke;
  caller synthetic phải truyền `scope='C4_1_SMOKE'`.

C3/C4 là tên machine contracts được mã nguồn dùng; không thay theo tên sản phẩm.
Chi tiết enforcement: [writer_adapter.py](../kag/builder/writer_adapter.py),
[runner](runner.md).

## Gate trước side effect

`validate_production_scope(settings, contract, manifest_path)` chạy offline,
không model/SDK client/network. Kiểm byte nodes/edges, schema/contract/input và
tính lại semantic plan hash bằng `graph_plan.plan_hash`; không chỉ tin manifest.

```text
nodes.jsonl  9a19e7e79a03c0ce339bf3da20d11db395c5662821178e5013d1f026fc8bea86
edges.jsonl  d419eca20055fac50d82dd872f489e8b514fba1befd5e19a848cae38f57b715b
plan hash    ee8b3709e89060b446c508f2c87bdcae7f401530976a30beecdd92935cdca917
schema       ec05cc76303b99c43f7d2d8ed662459daeafe69fa750b7ebbdbf975fb794c23c
contract     3a57fae7702e4f063b175d58e58a53d74b991b9c52f822c8cc769770687156c0
```

C3 manifest phải có input manifest, counts và `plan.sha256` UTF-8/LF. Kiểm file
thật của từng source input và ba canonical `xref_a3g2`; input paths thuộc
project root, không absolute/traversal. Schema/contract local phải khớp pin và
contract caller truyền vào. Gate này chứng minh input/local schema; schema
server cần kiểm live riêng trước bất kỳ execution authority tương lai nào.

Caller production phải hoàn tất `discover_production_project` trước tạo/gọi
vectorizer: offline validator → exact discovery → backend proof. Discovery dùng
read-only `_rest_client.project_get()`, lọc `name + namespace`; không chọn kết quả
đầu theo name hoặc gộp namespace bằng `get_all()`. Cần đúng một project,
positive ID khớp `expected_project_id`, rồi đọc lại theo ID và kiểm ID/name/namespace.
ID được trả về phải là native int hoặc chuỗi thập phân exact.

Missing/ambiguous/mismatch bị chặn trước embedding/write; không tạo project,
fallback sang sample hoặc env SDK. ID `2` dành cho C4.3a, production bị chặn
ngay offline dù server đổi tên project đó.

`WriterConfig` giữ C3 scope và [backend session/proof](backend-identity.md).
Constructor và `NativeIntegerKGWriter._invoke` kiểm target và revalidate live
trước dispatch, kể cả inherited `invoke/ainvoke`. Writer không được đổi config,
client hoặc route sau discovery. Proof hợp lệ vẫn không mở runner production WRITE.

Staged write kiểm toàn plan trước node đầu tiên. Node/edge payload phải khớp C3;
chỉ thêm vector đúng schema target, 3072 số hữu hạn, khác vector zero. Content
không rỗng cần vector. Ghi node trước; edge cần full C3 node readback barrier,
không chỉ endpoints của một batch. Rehash files/contract mỗi write; lỗi chặn trước
GraphClient. Fresh sample áp dụng cùng vector và barrier contract trên subset
manifest, đồng thời kiểm source node/edge hashes và isolated backend target.

## Config host/container

Template [writer_scope.example.json](../kag/config/writer_scope.example.json)
không credential, mặc định `DENY`, ID/confirmation rỗng. Chọn profile explicit:
host dùng loopback port publish; container dùng DNS mạng Docker. Endpoint cần
scheme/port, không userinfo/query/fragment. `neo4j_uri` bind identity/verifier;
offline validator không tạo Neo4j client. Auth lấy từ môi trường/secret store.

Production config cần scope `PRODUCTION`, exact name, namespace `VietRoadTraffic`,
ID đã kiểm độc lập và confirmation:

```text
CONFIRM_PRODUCTION:<project_name>:VietRoadTraffic:<expected_project_id>:ee8b3709e89060b446c508f2c87bdcae7f401530976a30beecdd92935cdca917
```

Confirmation bind target và plan, không phải credential hoặc quyền mở WRITE.
Không ghi token/key/password vào config repo. Entrypoint SDK dùng
[bootstrap runtime](runtime.md); runner config và mounts theo [runner](runner.md).

## Kiểm thử và giới hạn

Scope tests dùng project metadata fixtures, không gửi production graph request.
Lệnh suites nằm tại [tests](../tests/README.md); chạy từng process, runtime
canonical, source chỉ đọc, network denied. Offline contract tests không chứng
minh schema/backend live hoặc cấp quyền chạy production build.
