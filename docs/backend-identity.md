# Backend identity

[BackendIdentitySession](../kag/backend_identity.py) xác minh đúng project và physical database trước runner/writer/GraphLock. Endpoint trùng hoặc receipt cũ không đủ cấp quyền.

## Xác minh đường đi và database

Session đọc catalog project từ SDK đã pin: đúng một `name + namespace`, ID duy nhất, đọc lại theo ID; `graph_store` phải có Neo4j URI/database explicit. Credentials chỉ trong RAM.

- **NativeBackendTransport:** đường container sản phẩm; driver Bolt đọc metadata trên URI project và đối chiếu catalog HTTP độc lập. Bind project/namespace/databaseID/serverID/endpoint, đọc lại trước ghi/resume. Không cần Docker CLI/socket; driver không thay KGWriter làm đường ghi.
- **Thử biệt lập:** cần `KAG_ISOLATED_BUILDER_PASSWORD`, grant độc lập, endpoints loopback và kernel namespace chỉ loopback. Manifest không cấp grant. `FRESH_SAMPLE/WRITE/replay-existing` giới hạn target; điều kiện đặc biệt cho `vietroadtraffic` không cấp quyền production. Serving Compose có mạng storage và không truyền grant nên bị chặn.
- **DockerBackendTransport:** host/legacy/tests; inspect/exec local, kiểm publish ports, alias/DNS và network, catalog từ OpenSPG độc lập verifier host. Layout 8887/7474/7687; route/TLS chưa chứng minh thì chặn.
- **DockerPrivateBackendTransport:** legacy/tests, GET inspection qua socket; bind Compose/container/image/network/Neo4j volume và đúng namespace OpenSPG. Serving không mount socket.

Deployment khác cần transport tin cậy trong process với bằng chứng route tương đương; JSON config không thay transport.

`SHOW DATABASES` trên `system` phải trả database ONLINE, canonical name không mơ hồ, databaseID duy nhất và serverID không rỗng. Backend/verifier khớp tên và IDs; native bind protocol/endpoints, legacy bind thêm container/network/image, private bind thêm volume. `database_identity()` vẫn trả string.

## Vòng đời proof

Chỉ proof bất biến do **session đang hoạt động** cấp được chấp nhận. `validate()` đọc lại config/route/hai catalog trước dispatch; proof copy/giả/sửa/đóng session bị chặn. `lastStartTime` không thay live validation.

Receipt chỉ giữ identity fields cho phép, không credentials/session token, không khôi phục quyền. Resume tạo session mới và chứng minh target lại; nonce/session token không vào run hash.

## Writer và lock

`WriterConfig` cần session/proof đúng target; constructor và `_invoke` giữ guard cho node/edge/inherited invoke/ainvoke. Không thay writer config/client/REST route/binding sau tạo. Scope/vector/full node readback barrier vẫn bắt buộc.

GraphLock xác minh cùng proof; lock key là SHA-256 physical databaseID nên aliases cùng DB cạnh tranh cùng khóa. Source-only chỉ khóa run directory. Mount/owner/crash recovery: [runner](runner.md#resume-trạng-thái-và-lock).

**Identity hợp lệ không mở PRODUCTION WRITE.** Chỉ FRESH_SAMPLE có manifest giới hạn và backend biệt lập mới được xét WRITE. Offline request capture chỉ kiểm serialization, không chứng minh live backend. Cấu hình/lệnh: [runner](runner.md#config).
