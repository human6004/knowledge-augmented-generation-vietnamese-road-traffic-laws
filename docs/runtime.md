# Runtime Python và upstream KAG

Runtime chuẩn: **CPython 3.10.16, Linux amd64**.
`.python-version` và bootstrap kiểm tra đủ ba thành phần version.
Windows dùng Docker Desktop Linux containers; không dùng Python 3.14 của host.
Không cần khởi động OpenSPG để kiểm tra import.

## Setup từ clone mới

Dùng checkout sản phẩm hiện tại có bootstrap, Dockerfile và dependency lock.
Không checkout baseline phase lịch sử để chạy setup. Build/install dưới đây
do operator chạy khi cần môi trường mới; build cần mạng tải packages, không
thuộc kiểm tra tài liệu hoặc khởi tạo graph.

```powershell
git clone https://github.com/human6004/knowledge-augmented-generation-vietnamese-road-traffic-laws.git
cd knowledge-augmented-generation-vietnamese-road-traffic-laws
git submodule update --init vendor/KAG
docker build --platform linux/amd64 -f docker/kag-runtime/Dockerfile -t vietroadtraffic-kag-runtime:local .
docker run --rm --platform linux/amd64 --network none --mount "type=bind,source=$($PWD.Path),target=/workspace,readonly" vietroadtraffic-kag-runtime:local
```

Trên Linux, thay `source=$($PWD.Path)` bằng `source=$(pwd)`.
Image môi trường dùng base OpenSPG Server **digest literal trong Dockerfile**, tạo venv riêng
`/opt/kag-venv` với `system-site-packages=false`, cài toàn bộ dependency pin
trong `requirements.txt`, rồi chạy `pip check`. Không dùng các package SDK
có sẵn trong base image. Build context chỉ chứa Dockerfile và requirements;
không đưa `.env.kag`, dataset hoặc source vào image. Source lấy từ checkout
bind mount chỉ đọc; giữ `.git` để kiểm tra commit và working tree submodule.

Lần build cần mạng tải package. Test chạy `--network none`, không credential,
không volume database, không khởi tạo embedding/model hoặc ghi graph.
CMD mặc định chạy `tests/runtime`: version dependency, nguồn import, registry/
init và SHA input. Ghi kết quả thực chạy; build thành công không tự là
Solver/legal-domain hoặc official benchmark PASS.

Nếu đã có CPython **3.10.16** trên Linux amd64, có thể dùng venv trực tiếp:

```sh
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -B -m unittest discover -s tests/runtime -v
.venv/bin/python -B -m unittest discover -s tests/schema -v
.venv/bin/python -B -m unittest discover -s tests/builder -v
```

## Một bootstrap cho mọi entry point thật

Entry point gọi đúng một hàm trước khi import thành phần SDK:

```python
from kag.bootstrap import initialize
initialize()

from kag.builder import codec                 # code project
from kag.builder.writer_adapter import NativeIntegerKGWriter
from kag.builder.component.writer.kg_writer import KGWriter
from kag.builder.component.vectorizer.batch_vectorizer import BatchVectorizer
from kag.common.tools.search_api.impl.openspg_search_api import OpenSPGSearchAPI
```

`kag.builder` ưu tiên project, rồi fallback sang vendor. Các package upstream
khác ưu tiên vendor; upstream entry point chạy init/registry nguyên bản.
Không chèn `sys.path` trong từng script, không copy code sang `/tmp`.
Các import builder offline hiện có giữ nguyên, không tự nạp SDK.

Bootstrap từ chối Python sai version, submodule thiếu/sai commit, working tree
vendor bẩn và preloaded SDK khác trong `knext`, `kag.common`, `kag.interface`.
Preload từ đúng local `kag/solver/__init__.py` được bootstrap xử lý bằng reload
solver initializer upstream sau ghép namespace, trước upstream root initializer.
Giữ module object, không reload SDK interfaces/registry/submodules. Regression
kiểm initialize-first, preload-builder và preload-solver; lỗi lịch sử thiếu
`kag.solver.prompt` đã được sửa. Không xóa package/init để né bootstrap.
Gọi lại `initialize()` không đăng ký lại.
Kiểm working tree chuẩn hóa CRLF như Git Windows và bỏ qua executable bit
của bind mount NTFS; nội dung sửa và file untracked vẫn bị từ chối.
`KAG_DEBUG_DUMP_CONFIG=0` ngăn upstream dump config chứa secret khi import.

Source chuẩn: `vendor/KAG` commit
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`, version upstream **0.8.0**.
Không cài thêm wheel KAG cạnh source đã pin. Dependency hiện tại khóa trong
`requirements.txt`; optional components mới cần review/pin riêng khi được dùng.
Builder writer/vectorizer adapters và legal planner/pipeline dùng cùng bootstrap.
Chi tiết origin/registry: [kiến trúc](architecture.md#upstream-và-namespace).

## Input và bằng chứng hash

Ba input chuẩn nằm trong `artifacts/inputs/xref-a3g2/`, được version cùng
checkout. `manifest.json` ghi tên, kích thước, SHA-256 và nguồn lịch sử
`D:/study/caoDATA-workspace/reports/`. Máy mới không cần workspace lịch sử.
`.gitattributes` giữ nguyên byte qua clone Windows/Linux.

Truyền đường dẫn canonical này vào `load_inputs` hiện có; không fallback sang
file khác. `kag.builder.inputs.ARTIFACT_HASHES` và test runtime kiểm SHA exact:

```text
xref_a3g2_final_ledger.jsonl
1dea69f2c2b3ac344478ef24b1844f06514c4150a069e1c6d5cc5f9ffe8fecb4
xref_a3g2_final_audit.json
2a130da7f4c6ad0bb673366e9bb6e390f3e481cb5381003933f3195eb23e1fb3
xref_a3g2_downstream_policy.json
dcd12c131a9033efaf8f93703cf5423d59e3827f242249a5727759cb49d42b0e
```

Manifest còn ghi hash C3/C4.3a để đối chiếu artifact tham chiếu. Đây là tên
input/identity lịch sử vẫn có consumers; không đổi path, tái tạo plan hoặc sửa
golden từ thao tác setup. Production WRITE vẫn BLOCKED.

## Images OpenSPG

`docker-compose.kag.yml` pin literal digest cho server/MySQL/Neo4j;
không còn override `OPENSPG_*_IMAGE` hoặc default `latest`.
MinIO giữ Dockerfile pin nguồn hiện có. Pin không yêu cầu recreate stack
đang chạy. Setup interpreter và offline tests không yêu cầu Compose up/down
hoặc thao tác volume.

## Kiểm tra offline

Trong interpreter canonical đã có đủ dependencies, source read-only và network
denied, chạy từng suite ở process riêng để tránh tên fixture trùng. Lệnh và
ràng buộc lock/fixtures được duy trì tại [hướng dẫn tests](../tests/README.md).
Lịch sử canonical cleanup/import-order checks giữ tại
[giới hạn kiểm chứng](architecture.md#giới-hạn-kiểm-chứng-và-structural-debt).
Host checks, synthetic smoke, source-only validation và live graph proof báo riêng.

Không chạy provider/live graph/full benchmark để kiểm tra setup. Scope, backend
proof và runner vẫn fail closed; xem [writer scope](production-writer-scope.md).

CLI builder/verify chính thức: `python -B -m kag`; xem [runner và resume](runner.md).
CLI dataset: `python -B -m kag.evaluation`; xem [Evaluation Framework](architecture.md#evaluation-framework).
Wheel/version/phase receipts cũ là bằng chứng lịch sử, không được dùng để
tuyên bố môi trường đang chạy đã PASS.
