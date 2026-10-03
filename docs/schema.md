# Schema kỹ thuật v0.1

Namespace: **VietRoadTraffic**. Dataset: **LOCKED R2**. KAG pin:
`fdab15b3929d2ee40dfcdd388f90233096a6afc9`.

[VietRoadTraffic.schema](../kag/schema/VietRoadTraffic.schema) khai báo đúng
`LegalDocument`, `LegalUnit`, `TrafficSign`, 72 thuộc tính node của dự án
(28/31/13), 10 predicate và 34 khai báo thuộc tính cạnh.
Ba EntityType kế thừa `id/name` từ OpenSPG `Thing`, không khai báo lại.
`id/name` vẫn là thuộc tính logical của dự án: `logical_property_count = 78`
(30/33/15), `declared_project_property_count = 72`; sáu thuộc tính logical
`id/name` được kế thừa. `description` cũng là built-in server của `Thing`,
nhưng không thuộc contract miền của dự án hoặc mapping logical/physical.
[schema_contract.json](../kag/schema/schema_contract.json) là contract máy đọc
cho toàn bộ property, codec, quan hệ, identity và inclusion policy.
Ngữ nghĩa miền: [domain_model.md](domain_model.md).

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
  Integer nhận int thật, từ chối bool; writer upstream gửi chuỗi thập phân,
  coercion/query số phải được xác nhận trên server.
- `BOOLEAN_ENCODING` → `Text`, chỉ `"true"`/`"false"`; không native Boolean.
- `JSON_TEXT` → `Text`: `json.dumps(value, ensure_ascii=False, sort_keys=True,
  separators=(",", ":"))`. List giữ thứ tự. Không `Text[]` hoặc MultiValue.
- Bỏ null/missing khỏi payload; không gửi literal `"null"` cho unknown.
  Giữ 0, false và chuỗi rỗng. Source provenance bảo toàn khác biệt null/missing.
  Encode JSON_TEXT trước writer đúng một lần; codec implementation thuộc builder.
- `NotNull` chỉ cho property thực sự bắt buộc; optional và toàn bộ penalty
  sparse không có NotNull. `unitType` có Enum đủ năm giá trị miền.
  `required=true` của logical `id/name` là yêu cầu contract; không khai báo
  `NotNull` riêng cho hai thuộc tính kế thừa trong schema EntityType.
  Parser ghi nhận constraint; chưa xác minh server enforcement.

Cạnh cấu trúc giữ `sourceRecord`, `datasetVersion`; cạnh văn bản thêm
`evidence`, `note`. Hai cạnh xref giữ `evidenceRecords`,
`classificationProvenance`, `sourceRecord`, `datasetVersion` dưới Text/JSON_TEXT.
Các array provenance chứa đủ record đã duyệt, cờ corpus/polarity, scope,
endpoint, fingerprint và locator. Gộp bằng canonical JSON: chỉ bỏ record giống
hệt, sắp xếp theo biểu diễn UTF-8; không mất các evidence khác nhau cùng cạnh.

## Gate SAFE_EDGE bên ngoài

Runtime nhận đường dẫn ledger qua cấu hình; không phụ thuộc đường dẫn Windows.
Artifact: `xref_a3g2_final_ledger.jsonl`, vai trò classification LOCKED R2.

```text
xrefs SHA256: 6ade2790faf6ee843b3a5ade34c5bbc09dd64ebd4cacb9b751a93b2329462188
ledger SHA256: 1dea69f2c2b3ac344478ef24b1844f06514c4150a069e1c6d5cc5f9ffe8fecb4
classification total: 17512
SAFE_EDGE records: 8144 = 7709 affirmative + 435 exclusion
join: EXISTING_RECORD_FINGERPRINT_SHA256_CANONICAL_JSON
```

Fingerprint lịch sử dùng **đủ 13 trường record xref nguồn**, kể cả
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
nên khóa khác. Gộp provenance xác định trước writer. Contract ghi
`server_idempotency_verified=false`, `production_ingestion_enabled=false`.

## Xác nhận bắt buộc trước ingestion

Parser offline chấp nhận schema bằng source/model thật của KAG đã pin,
`with_server=False`. Test dùng boundary Configuration/SchemaClient trong bộ
kiểm thử để tránh khởi tạo SDK/network; không giả lập parser hoặc model.
Chạy từ root với Python có `six` của SDK upstream:

```sh
python -B tests/schema/test_schema_contract.py
python -B -m unittest discover -s tests/schema -p "test_*.py" -v
```

Trước ingestion phải xác nhận trên server ba nhóm: sync schema/built-in Thing `id/name` và constraints;
codec round-trip/coercion/omission/empty và giới hạn storage/index; edge
upsert/identity/dedup và cập nhật nhiều evidence. Khóa xác định ở ứng dụng
không chứng minh server idempotent. Graph chưa build; chưa chạy production
ingestion hoặc benchmark; builder/retriever/solver chưa triển khai.
