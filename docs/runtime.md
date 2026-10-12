# Runtime Python và upstream KAG

Runtime chuẩn: **CPython 3.10.16, Linux amd64**. `.python-version` và bootstrap
kiểm đủ ba thành phần version. Windows dùng Docker Desktop Linux containers;
Python khác version trên host không thay thế runtime này.

Upstream **KAG 0.8.0** lấy từ submodule `vendor/KAG`, commit
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`. Dependency pin nằm trong
[requirements.txt](../requirements.txt); không cài thêm wheel KAG cạnh source.

## Setup từ clone mới

```powershell
git clone https://github.com/human6004/knowledge-augmented-generation-vietnamese-road-traffic-laws.git
cd knowledge-augmented-generation-vietnamese-road-traffic-laws
git submodule update --init vendor/KAG
docker build --platform linux/amd64 -f docker/kag-runtime/Dockerfile -t vietroadtraffic-kag-runtime:local .
docker run --rm --platform linux/amd64 --network none --mount "type=bind,source=$($PWD.Path),target=/workspace,readonly" vietroadtraffic-kag-runtime:local
```

Trên Linux, thay `source=$($PWD.Path)` bằng `source=$(pwd)`. Không cần khởi động
OpenSPG để kiểm tra import. Build cần mạng tải packages; lệnh run trên chạy
offline, không credential, database volume, embedding hoặc graph write.

[Dockerfile](../docker/kag-runtime/Dockerfile) pin base OpenSPG Server bằng digest,
tạo venv `/opt/kag-venv` với `system-site-packages=false`, cài requirements và
chạy `pip check`. SDK có sẵn trong base image không thay dependency của venv.
Build context chỉ đưa Dockerfile và requirements; không đưa source, dataset
hoặc `.env.kag` vào image. Source bind mount chỉ đọc, giữ `.git` để bootstrap
kiểm submodule. CMD mặc định chạy `tests/runtime`.

Nếu có đúng CPython **3.10.16** trên Linux amd64, có thể dùng venv trực tiếp:

```sh
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -B -m unittest discover -s tests/runtime -v
```

Build thành công hoặc import pass chỉ chứng minh môi trường tương ứng; không
chứng minh graph live, Solver hoặc benchmark pháp lý.

## Một bootstrap cho mọi entry point thật

Entrypoint dùng SDK gọi một hàm trước SDK imports:

```python
from kag.bootstrap import initialize
initialize()

from kag.builder.writer_adapter import NativeIntegerKGWriter
from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
from kag.common.tools.search_api.impl.openspg_search_api import OpenSPGSearchAPI
```

`kag.builder` ưu tiên project rồi fallback vendor; các package upstream khác
ưu tiên vendor. Bootstrap chạy initializer/registry upstream; không chèn
`sys.path` trong từng script hoặc copy SDK sang thư mục tạm. Core builder
offline không tự nạp SDK.

Bootstrap từ chối Python sai version, submodule thiếu/sai commit, vendor bẩn
hoặc SDK khác đã nạp trong `knext`, `kag.common`, `kag.interface`. Khi local
`kag.solver` đã nạp, bootstrap reload initializer upstream sau ghép namespace,
giữ module object và không reload interfaces/registry/submodules. Gọi lại
`initialize()` không đăng ký lại.

Kiểm working tree chuẩn hóa CRLF như Git Windows, bỏ executable bit của NTFS;
file sửa hoặc untracked vẫn bị từ chối. Không xóa package/init để né bootstrap.
`KAG_DEBUG_DUMP_CONFIG=0` ngăn upstream dump config chứa secret khi import.
Nguồn import và namespace: [bản đồ mã nguồn](architecture.md#bản-đồ-mã-nguồn).

## Input và bằng chứng hash

Ba input chuẩn được version trong `artifacts/inputs/xref-a3g2/`.
`manifest.json` ghi tên, kích thước, SHA-256 và provenance; máy mới không cần
workspace nguồn ngoài Git. `.gitattributes` giữ byte qua clone Windows/Linux.

Truyền đúng các file này vào `load_inputs`, không fallback sang file khác.
`kag.builder.inputs.ARTIFACT_HASHES` và tests runtime kiểm SHA-256 exact:

```text
xref_a3g2_final_ledger.jsonl
1dea69f2c2b3ac344478ef24b1844f06514c4150a069e1c6d5cc5f9ffe8fecb4
xref_a3g2_final_audit.json
2a130da7f4c6ad0bb673366e9bb6e390f3e481cb5381003933f3195eb23e1fb3
xref_a3g2_downstream_policy.json
dcd12c131a9033efaf8f93703cf5423d59e3827f242249a5727759cb49d42b0e
```

C3/C4.3a trong manifest là tên contract/artifact được consumers dùng. Setup
không đổi path, tái tạo plan hoặc sửa golden. Scope và quyền ghi kiểm riêng
tại [writer scope](production-writer-scope.md).

## Images OpenSPG

`docker-compose.kag.yml` pin literal digest cho server/MySQL/Neo4j.
MinIO phải chọn image tương thích qua `STEP8_MINIO_IMAGE`; API dùng image riêng
qua `STEP8_API_IMAGE`. Pin runtime không yêu cầu recreate stack hoặc đổi volumes.
Triển khai và serving proof: [cài đặt](INSTALL.md), [cập nhật](UPDATE.md).

## Kiểm tra offline

Chạy mỗi suite trong process riêng để tránh tên fixture/registry trùng; source
chỉ đọc, network denied, output/fixtures ngoài repo. Lệnh và common lock mount
cho runner tests nằm tại [hướng dẫn tests](../tests/README.md). Host checks,
source-only validation và live graph proof có phạm vi kiểm chứng khác nhau.

CLI builder/verify: `python -B -m kag`, xem [runner](runner.md).
CLI dataset: `python -B -m kag.evaluation`, xem
[Evaluation Framework](architecture.md#evaluation-framework). Kiểm setup không
cần provider, graph live hoặc full benchmark.
