# Schema kỹ thuật

Namespace: **VietRoadTraffic**. Nguồn dữ liệu: `data/`. KAG pin:
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`.

[VietRoadTraffic.schema](../kag/schema/VietRoadTraffic.schema) khai báo đúng
`LegalDocument`, `LegalUnit`, `TrafficSign`, 69 thuộc tính node của dự án
(27/30/12), 10 predicate và 24 khai báo thuộc tính cạnh.
Ba EntityType kế thừa `id/name` từ OpenSPG `Thing`, không khai báo lại.
`id/name` vẫn là thuộc tính logical của dự án: `logical_property_count = 75`
(29/32/14), `declared_project_property_count = 69`; sáu thuộc tính logical
`id/name` được kế thừa. `description` cũng là built-in server của `Thing`,
nhưng không thuộc contract miền của dự án hoặc mapping logical/physical.
[schema_contract.json](../kag/schema/schema_contract.json) là contract máy đọc
cho toàn bộ property, codec, quan hệ, identity và inclusion policy.
Ngữ nghĩa miền: [domain_model.md](domain_model.md).

## Index nội dung

C1.1 khai báo `index: Vector` cho `LegalDocument.title`, `LegalUnit.text`,
`TrafficSign.ten` và `TrafficSign.moTa`. Parser pinned chuyển metadata này
thành `IndexTypeEnum.Vector`; không thêm property miền. Counts vẫn là
75 logical / 69 declared node properties / 24 relation properties.
BatchVectorizer tạo riêng `_title_vector`, `_text_vector`, `_ten_vector`,
`_mo_ta_vector`; không tự kết hợp các vector thành một retrieval field.
Không thêm Text/Sparse index vì C1.1 chỉ quyết định dense content targets.

Identity `name=id` giữ nguyên. C4 truyền `disable_generation`:
`LegalDocument.name`, `LegalUnit.name`, `TrafficSign.name`, `Entity.name`.
Mục cuối chặn fallback `Entity` của upstream; dùng short labels trước vectorizer.
Không tạo `_name_vector` giả để né embedding. Không vector hóa provenance,
ID, ngày tháng hoặc giá trị penalty. `None`/chuỗi rỗng không tạo vector;
156/887 tên biển rỗng vẫn có `moTa` để truy hồi. Contract không sửa dữ liệu.

`LegalUnit.text` dài tối đa 757.423 ký tự. C4 phải kiểm giới hạn đầu vào của
model được chọn sau này trước khi ghi, không tự cắt text. Metadata không
chứng minh model/server đã được cấu hình hoặc vector đã tồn tại. C1.1 không
chọn provider/model, dimension hoặc gọi embedding. Chi tiết probe và
thống kê nằm trong báo cáo ngoại vi `builder-preflight/c1_1/`.

## Tên và quan hệ

Tên logical/source snake_case ánh xạ sang lowerCamelCase theo `schema_contract.json`;
`id`, `name` và tên đơn giản giữ nguyên. Không dùng underscore trong identifier
property/predicate vật lý. `QCVN_Muc` là giá trị enum, không phải identifier.

```text
HAS_UNIT     → hasUnit       LegalDocument → LegalUnit (root)
HAS_CHILD    → hasChild      LegalUnit → LegalUnit
HAS_SIGN     → hasSign       LegalUnit → TrafficSign
CITES_UNIT   → citesUnit     LegalUnit → LegalUnit
EXCLUDES_UNIT→ excludesUnit  LegalUnit → LegalUnit
CITES        → cites         LegalDocument → LegalDocument
AMENDS       → amends        LegalDocument → LegalDocument
REPEALS      → repeals       LegalDocument → LegalDocument
IMPLEMENTS   → implements    LegalDocument → LegalDocument
CONSOLIDATES → consolidates  LegalDocument → LegalDocument
```

Không khai báo inverse hoặc node Penalty/Evidence/QCVN riêng.

## Kiểu và codec

- `TEXT`, `OPTIONAL_TEXT` → `Text`; `INTEGER`, `OPTIONAL_INTEGER` → `Integer`.
  Builder phải nhận int thật (`type(value) is int`), từ chối bool, string và
  mọi giá trị không nguyên. Project-local `NativeIntegerKGWriter(KGWriter)`
  giữ các property Integer đã validate, gọi normalization upstream rồi phục hồi
  native int trước `GraphClient` serialization. Upstream KGWriter mặc định đổi
  int thành string; không dùng hành vi đó cho Integer của dự án. Không parse
  Text giống số. Sau JSON decode thuộc tính server, giữ kiểu integer, kể cả 0.
- `BOOLEAN_ENCODING` → `Text`, chỉ `"true"`/`"false"`; không native Boolean.
- `JSON_TEXT` → `Text`: `json.dumps(value, ensure_ascii=False, sort_keys=True,
  separators=(",", ":"))`. List giữ thứ tự. Không `Text[]` hoặc MultiValue.
- Bỏ null/missing khỏi payload; không gửi literal `"null"` cho unknown.
  Giữ 0, false và chuỗi rỗng. Source provenance bảo toàn khác biệt null/missing.
  Encode JSON_TEXT trước writer đúng một lần; codec implementation thuộc builder.
- Server JSON-serialize thuộc tính trừ intrinsic `id`: khi đọc dùng `json.loads`.
  Với JSON_TEXT, decode thêm JSON bên trong khi cần giá trị semantic.
- `NotNull` chỉ cho property thực sự bắt buộc; optional và toàn bộ penalty
  sparse không có NotNull. `unitType` có Enum đủ năm giá trị miền.
  `required=true` của logical `id/name` là yêu cầu contract; không khai báo
  `NotNull` riêng cho hai thuộc tính kế thừa trong schema EntityType.
  Server constraints chỉ **DECLARATIVE_ONLY**; Builder phải kiểm tra required
  fields và `unitType` thuộc `Dieu`, `Khoan`, `Diem`, `QCVN`, `QCVN_Muc`.

Cạnh cấu trúc giữ `sourceRecord`; cạnh văn bản thêm
`evidence`, `note`. Hai cạnh xref giữ `evidenceRecords`,
`classificationProvenance`, `sourceRecord` dưới Text/JSON_TEXT.
Các array provenance chứa đủ record đã duyệt, cờ corpus/polarity, scope,
endpoint, fingerprint và locator. Gộp bằng canonical JSON: chỉ bỏ record giống
hệt, sắp xếp theo biểu diễn UTF-8; không mất các evidence khác nhau cùng cạnh.

## Gate SAFE_EDGE bên ngoài

Runtime nhận đường dẫn ledger qua cấu hình; không phụ thuộc đường dẫn Windows.
Artifact: `xref_a3g2_final_ledger.jsonl`, chứa classification của các record xref.

```text
xrefs SHA256: 6ade2790faf6ee843b3a5ade34c5bbc09dd64ebd4cacb9b751a93b2329462188
ledger SHA256: 1dea69f2c2b3ac344478ef24b1844f06514c4150a069e1c6d5cc5f9ffe8fecb4
classification total: 17512
SAFE_EDGE records: 8144 = 7709 affirmative + 435 exclusion
join: EXISTING_RECORD_FINGERPRINT_SHA256_CANONICAL_JSON
```

Fingerprint dùng **đủ 13 trường record xref nguồn**, kể cả
`from_so_hieu`, không normalize/trim hoặc đổi missing/null/rỗng:

```python
canonical = json.dumps(source_record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
record_fingerprint = hashlib.sha256(canonical).hexdigest()
```

Số dòng chỉ phục vụ locator, không phải khóa join. Phải kiểm tra hai hash,
join đầy đủ 1:1 không mơ hồ và đúng counts. Chỉ SAFE_EDGE đi tiếp; hai endpoint
phải là unit production, doc IDs khớp, `in_corpus=true`, evidence không rỗng.
Thiếu ledger, mismatch hoặc conflict → chặn cạnh xref. Không thêm
`downstream_use` vào xrefs nguồn. Phân biệt SAFE_EDGE record và cạnh sau gộp.

## Khóa cạnh ứng dụng

```python
tuple_fields = [fully_qualified_from_type, from_id, physical_predicate,
                fully_qualified_to_type, to_id]
canonical = json.dumps(tuple_fields, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
application_edge_key = hashlib.sha256(canonical).hexdigest()
```

Type fully qualified dùng `VietRoadTraffic.<EntityType>`, ID nguồn nguyên trạng.
Evidence không nằm trong identity; citation và exclusion có predicate khác
nên khóa khác. Giữ khóa ứng dụng cho tái lập, logging, truy vết, dedup cục bộ
và tổng hợp evidence xác định; khóa này không điều khiển uniqueness server.

## Contract runtime và yêu cầu Builder

Schema tương thích với runtime OpenSPG/KAG đã pin. `runtime_contract` trong
contract máy đọc gắn yêu cầu runtime với SHA-256 của schema:

```text
ec05cc76303b99c43f7d2d8ed662459daeafe69fa750b7ebbdbf975fb794c23c
```

OpenSPG cung cấp `id/name` qua `Thing`. Constraints schema là khai báo
**DECLARATIVE_ONLY**; Builder kiểm tra trường bắt buộc, enum `unitType` và
Integer trước khi ghi. Chỉ `type(value) is int` hợp lệ cho Integer; bool,
string và giá trị không nguyên bị từ chối. None/missing được bỏ khỏi payload;
chuỗi rỗng, 0 và false được giữ theo codec ở trên.

Khi đọc, thuộc tính server ngoài intrinsic `id` cần JSON decode; JSON_TEXT
cần thêm một lần decode semantic JSON. Builder encode JSON_TEXT xác định
đúng một lần trước writer. Runtime hỗ trợ kích thước text của dataset hiện tại,
bao gồm payload text lớn nhất trong dữ liệu nguồn.

Identity cạnh OpenSPG là **(node nguồn, predicate vật lý, node đích)**
(`FROM_PREDICATE_TO_TUPLE`). Ghi lặp hoặc đổi client edge ID không tạo cạnh trùng.
Cập nhật thuộc tính cạnh là **LAST_WRITE_WINS**: gộp evidence/provenance xác định
theo tuple trước khi ghi, rồi gửi đầy đủ thuộc tính cạnh cuối cùng.
Ghi toàn bộ node thật trước cạnh; không dựa vào server tạo endpoint ngầm.
Khóa cạnh ứng dụng là khóa cục bộ riêng, không thay thế tuple identity server.

## Kiểm thử offline

Parser offline chấp nhận schema bằng source/model thật của KAG đã pin,
`with_server=False`. Test dùng boundary Configuration/SchemaClient trong bộ
kiểm thử để tránh khởi tạo SDK/network; không giả lập parser hoặc model.
Chạy từ root với Python có `six` của SDK upstream:

```sh
python -B tests/schema/test_schema_contract.py
python -B -m unittest discover -s tests/schema -p "test_*.py" -v
```

Trạng thái triển khai các thành phần nằm tại [README](../README.md).
