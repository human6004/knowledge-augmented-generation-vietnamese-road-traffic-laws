# Runtime KAG khóa tại D0.2

Runtime chuẩn: **CPython 3.10.16, Linux amd64**, cùng interpreter đã PASS C4.
`.python-version` và bootstrap kiểm tra đủ ba thành phần version.
Windows dùng Docker Desktop Linux containers; không dùng Python 3.14 của host.
Không cần khởi động OpenSPG để kiểm tra import.

## Setup từ clone mới

Checkout revision chứa D0.2 đã được nhóm chốt; baseline C4 `470b326` chưa chứa
các file D0.2. Không tự checkout baseline để chạy hướng dẫn này.

```powershell
git clone https://github.com/human6004/knowledge-augmented-generation-vietnamese-road-traffic-laws.git
cd knowledge-augmented-generation-vietnamese-road-traffic-laws
git checkout <revision-chua-D0.2>
git submodule update --init vendor/KAG
docker build --platform linux/amd64 -f docker/kag-runtime/Dockerfile -t vietroadtraffic-kag-runtime:d0.2 .
docker run --rm --platform linux/amd64 --network none --mount "type=bind,source=$($PWD.Path),target=/workspace,readonly" vietroadtraffic-kag-runtime:d0.2
```

Trên Linux, thay `source=$($PWD.Path)` bằng `source=$(pwd)`.
Image môi trường dùng base OpenSPG Server **digest D0.1**, tạo venv riêng
`/opt/kag-venv` với `system-site-packages=false`, cài toàn bộ dependency pin
trong `requirements.txt`, rồi chạy `pip check`. Không dùng các package SDK
có sẵn trong base image. Build context chỉ chứa Dockerfile và requirements;
không đưa `.env.kag`, dataset hoặc source vào image. Source lấy từ checkout
bind mount chỉ đọc; giữ `.git` để kiểm tra commit và working tree submodule.

Lần build cần mạng tải package. Test chạy `--network none`, không credential,
không volume database, không khởi tạo embedding/model hoặc ghi graph.
Smoke kiểm tra version dependency, nguồn import, registry/init thật và SHA input.

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
vendor bẩn và SDK khác đã nạp trước. Gọi lại `initialize()` không đăng ký lại.
Kiểm working tree chuẩn hóa CRLF như Git Windows và bỏ qua executable bit
của bind mount NTFS; nội dung sửa và file untracked vẫn bị từ chối.
`KAG_DEBUG_DUMP_CONFIG=0` ngăn upstream dump config chứa secret khi import.

Source chuẩn: `vendor/KAG` commit
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`, version upstream **0.8.0**.
Wheel `openspg-kag==0.8.0.20250703.2020` là SDK môi trường C4 lịch sử;
không cài thêm wheel này cạnh source đã pin. Lock lấy dependency thực được
nạp bởi registry C4 và closure metadata, kiểm lại bằng venv sạch.
Lock này phục vụ builder/import hiện tại; dependency optional cho component
chưa dùng cần review và pin khi component đó được triển khai.

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

Manifest còn ghi hash C3/C4.3a để đối chiếu artifact tham chiếu; D0.2 không
tái tạo plan, không đổi golden hoặc artifact cũ. Việc chạy graph nằm ở gate sau.

## Images OpenSPG

`docker-compose.kag.yml` pin literal digest D0.1 cho server/MySQL/Neo4j;
không còn override `OPENSPG_*_IMAGE` hoặc default `latest`.
MinIO giữ Dockerfile pin nguồn hiện có. Pin không yêu cầu recreate stack
đang chạy. D0.2 không chạy Compose up/down hoặc thao tác volume.

D0.2 đã bao gồm pin image và version input của D0.3; không làm lại D0.3.
Production scope D0.4 chỉ code/test fail-closed, chưa được ghi production;
xem [contract writer scope](production-writer-scope.md).

CLI builder/verify chính thức: `python -B -m kag`; xem [runner và resume](runner.md).
