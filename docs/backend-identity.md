# Backend identity và physical database proof

`BackendIdentitySession` xác minh target đang chạy trước khi runner, writer hoặc
GraphLock dùng graph. Session đọc toàn bộ danh sách project từ SDK đã pin,
yêu cầu đúng một kết quả theo `name + namespace` và đúng một ID, rồi đọc lại
độc lập theo ID. `graph_store` phải khai báo Neo4j URI và database; không lấy
database mặc định từ runtime. Credential chỉ nằm trong bộ nhớ transport.

Mã nguồn: [backend_identity.py](../kag/backend_identity.py).

## Xác minh đường đi và database

Transport phải chứng minh request đi tới URI của project. Hai adapter Docker
phục vụ hai kiểu kết nối:

- `DockerBackendTransport`: cần Docker CLI, quyền inspect/exec local và layout
  HTTP/Bolt `8887/7474/7687`. Kiểm container đang chạy, port publish, network
  chung, alias và DNS từ bên trong OpenSPG; đọc catalog tại namespace OpenSPG
  độc lập với verifier host. Thiếu quyền, đổi port, TLS hoặc route chưa chứng
  minh đều bị chặn.
- `DockerPrivateBackendTransport`: đọc Docker socket bằng GET inspection,
  không cần publish port quản trị. Runner phải dùng đúng network namespace
  OpenSPG; kiểm Compose project/service, container/image/network và volume
  Neo4j đã bind. Serving containers không mount socket này.

Deployment khác cần transport tin cậy trong cùng process, cung cấp bằng chứng
route tương đương. JSON config và receipt không thể thay transport hoặc mở WRITE.

Catalog được đọc bằng `SHOW DATABASES` trên `system`, với parameters. Tên khác
hoa/thường chỉ được chấp nhận khi có đúng một hàng canonical. Database phải
ONLINE, `databaseID`/`serverID` không rỗng và physical databaseID duy nhất.
Backend và verifier phải khớp tên canonical, physical ID và serverID.
Proof còn bind identity container/image/network; adapter private bind cả volume.
`database_identity()` vẫn trả string.

## Vòng đời proof

Chỉ đúng instance proof bất biến do session đang hoạt động cấp được chấp nhận.
`validate()` đọc lại project config, route và hai catalog trước dispatch.
Proof sao chép, giả, sửa, hết hiệu lực hoặc thuộc session đã đóng đều bị chặn.
`lastStartTime` không dùng làm gate freshness; giá trị null không thay thế
xác minh live.

Receipt chỉ lưu các trường identity được cho phép, không lưu credential hoặc
session token. Receipt không khôi phục quyền vận hành. Resume phải tạo session
mới và chứng minh lại target live; nonce/session token không vào run hash.

## Writer và lock

Production discovery kiểm scope/C3 offline trước. `WriterConfig` cần session và
proof đúng target. Constructor và `_invoke` dùng chung guard cho native write,
inherited `invoke/ainvoke`, node và edge. Writer đã tạo không được thay config,
client, REST route hoặc backend binding. Scope, vector và full node readback
barrier vẫn bắt buộc; xem [writer scope](production-writer-scope.md).

GraphLock xác minh cùng proof khi tạo và acquire. Tên lock là
SHA-256(physical databaseID), nên các alias đã được chứng minh cạnh tranh cùng
một lock. Source-only mode chỉ dùng lock theo run directory.

Backend identity hợp lệ không mở `PRODUCTION WRITE`. Runner chỉ cho phép WRITE
trong `FRESH_SAMPLE` với manifest giới hạn và backend cô lập đã được chứng minh.
Không dùng sample project/physical ID làm mặc định production. Offline capture
request writer chỉ kiểm serialization trước HTTP; không chứng minh backend live.
Quy trình chạy và resume: [runner](runner.md).
