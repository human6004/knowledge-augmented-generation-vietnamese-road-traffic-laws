# D0.4 — Production writer scope

Chỉ triển khai code và test scope/validation. D0.4 không tạo production project,
không gọi embedding, không ghi graph. Production full build còn khóa đến
`DEMO_MACHINE_PASS`; xác nhận cấu hình dưới đây không thay thế gate roadmap.

## Scope và default

- `C4_1_SMOKE`: tên project và ID synthetic được discovery/verify; chỉ ID dưới
  prefix smoke, cleanup exact synthetic được phép.
- `C4_3A_MANIFEST_SAMPLE` (DEMO): giữ nguyên project `VietRoadTrafficC43A10Pct`,
  ID `2`, namespace `VietRoadTraffic`, partition `5`, node/edge identity manifest
  C4.3a. Không đổi hành vi sample đã PASS; không được delete dữ liệu thật.
- `PRODUCTION`: cấu hình riêng, target khác sample/smoke, C3 exact, không delete.
- Thiếu scope hoặc scope lạ: `DENY WRITE`. `WriterConfig` không tự chọn smoke.
  Caller smoke cũ phải truyền rõ `scope='C4_1_SMOKE'`.

## Gate trước side effect

`validate_production_scope(settings, contract, manifest_path)` chạy offline,
không nạp model/SDK client, không network. Phải gọi trước khi tạo/gọi vectorizer.
Không chỉ tin hash khai trong manifest: kiểm byte nodes/edges và tính lại
semantic plan hash bằng `graph_plan.plan_hash` hiện có.
Đây là phần kiểm input, chưa cấp quyền embedding/write. Caller production
phải hoàn tất cả `discover_production_project` trước khi tạo/gọi vectorizer;
missing/ambiguous/mismatch project phải chặn tại đó, không chờ đến write.

```text
nodes.jsonl  9a19e7e79a03c0ce339bf3da20d11db395c5662821178e5013d1f026fc8bea86
edges.jsonl  d419eca20055fac50d82dd872f489e8b514fba1befd5e19a848cae38f57b715b
plan hash    ee8b3709e89060b446c508f2c87bdcae7f401530976a30beecdd92935cdca917
schema       ec05cc76303b99c43f7d2d8ed662459daeafe69fa750b7ebbdbf975fb794c23c
contract     3a57fae7702e4f063b175d58e58a53d74b991b9c52f822c8cc769770687156c0
```

Manifest phải là C3, có đầy đủ input manifest, counts và `plan.sha256` UTF-8/LF.
Mỗi input source và ba canonical `xref_a3g2` được kiểm checksum từ file thật.
Đường dẫn input phải nằm trong project root; không absolute/path traversal.
Schema/contract local phải khớp pin và contract truyền vào. Binding này chứng
minh identity C3/local schema; schema đang cài trên server phải được preflight
production D1/readback xác minh riêng trước full build.

`discover_production_project` làm gate offline trước, rồi dùng read-only
`_rest_client.project_get()` để lọc exact `name + namespace`. Không dùng
`ProjectClient.get(name=...)` chọn kết quả đầu hoặc `get_all()` gộp namespace.
Phải có đúng một project, ID là positive int hoặc chuỗi thập phân exact, khớp
`expected_project_id`; đọc lại theo ID và kiểm cả ID/name/namespace. Không tạo
project khi missing/ambiguous, không fallback sang ID sample hoặc env SDK.
ID `2` reserved cho sample và bị chặn ngay gate offline, kể cả khi server đổi
tên project đó thành production. Production phải chọn ID khác qua discovery.

Production proof được gắn vào `WriterConfig`. `NativeIntegerKGWriter._invoke`
kiểm scope cho direct write và inherited `invoke/ainvoke`; staged write kiểm
toàn bộ plan trước node đầu tiên. Payload node/edge phải khớp C3, chỉ được thêm
vector đúng target schema với 3072 số hữu hạn. Content không rỗng phải có vector
trước write. Edge cần full C3 node readback barrier, không chỉ endpoint batch.
Mỗi write kiểm lại checksum file và contract; lỗi chặn trước GraphClient.

## Config host/container

Template official: `kag/config/writer_scope.example.json`. Không credential.
Chọn profile tường minh; không tự đoán từ host. Host dùng loopback port publish;
container dùng DNS mạng Docker. Endpoint phải có scheme/port, không userinfo,
query hoặc fragment. `neo4j_uri` là cấu hình phục vụ verify về sau, D0.4 không
khởi tạo Neo4j client. Auth lấy từ môi trường/runtime secret store khi cần.

```python
import json
from pathlib import Path
from kag.builder.production_scope import ProductionSettings, validate_production_scope

config = json.loads(Path('kag/config/writer_scope.example.json').read_text())
profile = 'host'  # 'container' khi chạy trong kag-runtime nối mạng stack
settings = ProductionSettings(scope=config['scope'],
    **config['profiles'][profile], **config['production'])
scope = validate_production_scope(settings, contract, c3_manifest_path)
# Entry point đã bootstrap SDK theo docs/runtime.md; client read-only đúng host.
from kag.builder.writer_adapter import discover_production_project
writer_config = discover_production_project(project_client, settings, contract,
                                           c3_manifest_path)
# Chỉ sau complete preflight này mới có thể khởi tạo vectorizer ở gate roadmap sau.
```

Template mặc định `DENY`, ID/confirmation rỗng, nên snippet từ chối. Khi gate
roadmap cho phép production, operator đặt scope `PRODUCTION`, name exact,
ID đã kiểm độc lập, và confirmation exact:

```text
CONFIRM_PRODUCTION:<project_name>:VietRoadTraffic:<expected_project_id>:ee8b3709e89060b446c508f2c87bdcae7f401530976a30beecdd92935cdca917
```

Confirmation gắn target và plan; không phải credential. Không ghi token/key/
password vào config repo. D0.4 tests chỉ dùng fake project metadata, không
gửi production graph request. Test fixture nhỏ dùng hash tính độc lập; evidence
ngoài repo kiểm thêm C3 golden thật.

## Kiểm thử và giới hạn

```sh
python -B -m unittest discover -s tests/schema
python -B -m unittest discover -s tests/builder
python -B -m unittest discover -s tests/runtime
```

Chạy từng suite process riêng vì builder/runtime đều có module `test_inputs`.
Môi trường chuẩn vẫn Docker runtime D0.2 CPython 3.10.16, không mạng, source chỉ
đọc. Rehash exact mỗi batch ưu tiên fail-closed; tối ưu khi runner có immutable
input snapshot. Không thêm runner/streaming hoặc state/release ở D0.4.

Bước tiếp theo: D0.5–D0.7 runner + verify + rehearsal C4.3a theo sample-first.
