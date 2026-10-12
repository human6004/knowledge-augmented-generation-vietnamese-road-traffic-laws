# Schema kỹ thuật

Namespace **VietRoadTraffic**; nguồn corpus trong `data/`.
[VietRoadTraffic.schema](../kag/schema/VietRoadTraffic.schema) khai báo ba EntityType
`LegalDocument`, `LegalUnit`, `TrafficSign`, 69 node properties của dự án
(27/30/12), 10 predicates và 24 relation properties.

Ba EntityType kế thừa `id/name` từ OpenSPG `Thing`, không khai báo lại.
Contract có 75 logical properties (29/32/14), gồm sáu `id/name` kế thừa.
`description` built-in của server không thuộc contract miền hoặc mapping
logical/physical. [schema_contract.json](../kag/schema/schema_contract.json)
là nguồn máy đọc cho properties, codec, quan hệ, identity và inclusion policy.
Ngữ nghĩa pháp lý: [mô hình miền](domain_model.md); phiên bản SDK/runtime:
[runtime](runtime.md).

## Index nội dung

Schema khai báo `index: Vector` cho `LegalDocument.title`, `LegalUnit.text`,
`TrafficSign.ten`, `TrafficSign.moTa`. Parser chuyển metadata thành
`IndexTypeEnum.Vector`; không thêm property miền hoặc Text/Sparse index.
BatchVectorizer tạo `_title_vector`, `_text_vector`, `_ten_vector`,
`_mo_ta_vector` riêng, không tự kết hợp thành một retrieval field.

Identity `name=id`. Truyền `disable_generation` với `LegalDocument.name`,
`LegalUnit.name`, `TrafficSign.name`, `Entity.name`; mục cuối chặn fallback
upstream. Vectorizer nhận short labels. Không tạo `_name_vector` giả hoặc vector
hóa ID, provenance, ngày tháng hay penalty. `None`/chuỗi rỗng không tạo vector;
tên biển rỗng vẫn giữ mô tả nguồn để truy hồi.

Metadata index không chứng minh vector/model đã được cấu hình hoặc tồn tại.
Vectorizer kiểm giới hạn model trước ghi, không tự cắt text dài. Schema giữ
toàn bộ text; provider/dimension và live index được kiểm ở runtime/runner.

## Tên và quan hệ

Tên logical/source snake_case ánh xạ lowerCamelCase theo contract; `id/name`
và tên đơn giản giữ nguyên. Identifier property/predicate vật lý không dùng
underscore. `QCVN_Muc` là giá trị enum, không phải identifier.

```text
HAS_UNIT      → hasUnit       LegalDocument → LegalUnit (root)
HAS_CHILD     → hasChild      LegalUnit → LegalUnit
HAS_SIGN      → hasSign       LegalUnit → TrafficSign
CITES_UNIT    → citesUnit     LegalUnit → LegalUnit
EXCLUDES_UNIT → excludesUnit  LegalUnit → LegalUnit
CITES         → cites         LegalDocument → LegalDocument
AMENDS        → amends        LegalDocument → LegalDocument
REPEALS       → repeals       LegalDocument → LegalDocument
IMPLEMENTS    → implements    LegalDocument → LegalDocument
CONSOLIDATES  → consolidates  LegalDocument → LegalDocument
```

Không có inverse hoặc node Penalty/Evidence/QCVN riêng.

## Kiểu và codec

- `TEXT/OPTIONAL_TEXT` → Text; `INTEGER/OPTIONAL_INTEGER` → Integer.
  Chỉ `type(value) is int` hợp lệ: từ chối bool, string và số không nguyên.
  `NativeIntegerKGWriter` giữ int đã validate, gọi normalizer upstream rồi
  phục hồi int trước GraphClient serialization; KGWriter mặc định đổi int
  thành string. Không parse Text giống số.
- `BOOLEAN_ENCODING` → Text `"true"/"false"`, không native Boolean.
- `JSON_TEXT` → Text bằng canonical JSON: `ensure_ascii=False`, `sort_keys=True`,
  `separators=(",", ":")`. Giữ list order; không dùng Text[]/MultiValue.
- Bỏ null/missing khỏi payload, không gửi literal `"null"` cho unknown.
  Giữ 0, false và chuỗi rỗng; provenance bảo toàn khác biệt null/missing.
  Encode JSON_TEXT đúng một lần trước writer.
- Thuộc tính server ngoài intrinsic `id` có outer JSON storage layer;
  read boundary decode đúng một lần, giữ vectors nguyên trạng.
  JSON_TEXT cần thêm semantic JSON decode. Integer sau outer decode phải
  vẫn là native int, kể cả 0; Text giống số/double encoding bị chặn.
- `NotNull` chỉ cho property bắt buộc; optional và penalty sparse không có
  NotNull. `required=true` của `id/name` thuộc contract, không khai báo
  NotNull riêng cho hai property kế thừa. Constraints server là
  **DECLARATIVE_ONLY**: Builder kiểm required fields và `unitType` thuộc
  `Dieu`, `Khoan`, `Diem`, `QCVN`, `QCVN_Muc`.

Cạnh cấu trúc giữ `sourceRecord`; cạnh văn bản thêm `evidence/note`.
Hai cạnh xref giữ `evidenceRecords`, `classificationProvenance`, `sourceRecord`
dưới Text/JSON_TEXT. Provenance chứa mọi record được duyệt, corpus/polarity,
scope, endpoint, fingerprint và locator. Gộp canonical JSON: chỉ dedup record
giống hệt, sort theo biểu diễn UTF-8; không mất evidence khác nhau cùng cạnh.

## Gate SAFE_EDGE bên ngoài

Runtime nhận path ledger từ config, không phụ thuộc đường dẫn máy cá nhân.
Contract pin `xref_a3g2_final_ledger.jsonl` và source xrefs:

```text
xrefs SHA256: 6ade2790faf6ee843b3a5ade34c5bbc09dd64ebd4cacb9b751a93b2329462188
ledger SHA256: 1dea69f2c2b3ac344478ef24b1844f06514c4150a069e1c6d5cc5f9ffe8fecb4
classification total: 17512
SAFE_EDGE records: 8144 = 7709 affirmative + 435 exclusion
join: EXISTING_RECORD_FINGERPRINT_SHA256_CANONICAL_JSON
```

Fingerprint dùng đủ **13 trường record xref nguồn**, kể cả `from_so_hieu`,
không normalize/trim hoặc đổi missing/null/rỗng:

```python
canonical = json.dumps(source_record, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")).encode("utf-8")
record_fingerprint = hashlib.sha256(canonical).hexdigest()
```

Số dòng là locator, không phải khóa join. Kiểm hai hash, full join 1:1 không
mơ hồ và exact counts. Chỉ SAFE_EDGE đi tiếp; hai endpoints thuộc production
whitelist, doc IDs khớp, `in_corpus=true`, evidence không rỗng.
Thiếu ledger/mismatch/conflict chặn xref; không thêm `downstream_use` vào nguồn.
SAFE_EDGE record count khác unique edge count sau gộp.

## Khóa cạnh ứng dụng

```python
tuple_fields = [fully_qualified_from_type, from_id, physical_predicate,
                fully_qualified_to_type, to_id]
canonical = json.dumps(tuple_fields, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
application_edge_key = hashlib.sha256(canonical).hexdigest()
```

Type fully qualified là `VietRoadTraffic.<EntityType>`; ID nguồn nguyên trạng.
Evidence không vào identity; citation/exclusion có predicates khác nên khóa
khác. Khóa phục vụ tái lập, logging, local dedup và tổng hợp evidence; không
điều khiển uniqueness server.

## Contract runtime và yêu cầu Builder

`runtime_contract` bind schema SHA-256:

```text
ec05cc76303b99c43f7d2d8ed662459daeafe69fa750b7ebbdbf975fb794c23c
```

Identity cạnh server là **(node nguồn, predicate vật lý, node đích)**,
`FROM_PREDICATE_TO_TUPLE`; đổi client edge ID không tạo cạnh mới.
Cập nhật properties là **LAST_WRITE_WINS**. Builder gộp provenance xác định
theo tuple rồi gửi đầy đủ properties cuối cùng; không ghi từng evidence để
tránh mất record. Ghi toàn bộ node thật trước cạnh, không dựa server tạo
endpoint ngầm. Runtime contract giữ text tới kích thước tối đa dataset hiện có;
gate scope và quyền vận hành vẫn kiểm riêng tại [writer scope](production-writer-scope.md).

## Kiểm thử offline

Tests dùng schema parser/model SDK thật với `with_server=False`; chỉ thay
Configuration/SchemaClient boundary để không network. Cần runtime canonical
và `six` trong dependency lock, xem [tests/schema](../tests/schema/README.md).
Kiểm parser/contract offline không chứng minh schema server đang cài hoặc
graph/vector live.
