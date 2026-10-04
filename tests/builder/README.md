# Builder offline

Các module project-layer dùng stdlib; import trực tiếp `kag.builder.codec`,
`kag.builder.inputs`, `kag.builder.mapping`. Không khởi tạo SDK/service/model.

- Codec nhận logical keys và property rows từ `schema_contract.json`; encode trả
  physical keys. JSON_TEXT nhận giá trị Python logical, encode một lần; Integer
  giữ native int. Decode trả logical keys, semantic JSON và Boolean Text `true/false`.
  `server_encoded=True` đọc thêm đúng một lớp JSON ngoài cho non-identity properties.
- `load_inputs(project_root, ledger_path, audit_path, policy_path, contract)` trả
  `ValidatedInputs`: exact indexes, penalty join, toàn bộ fingerprint join.
  Production mặc định pin SHA ledger/audit/policy và xref. Chỉ fixture synthetic
  cấp `expected_artifact_hashes` riêng và xref SHA tương ứng trong contract copy.
- `validate_input_integrity(BuilderInputs(...), contract)` dành cho records đã đọc,
  bao gồm synthetic fixtures. Kiểm identity/hierarchy/joins; SHA của file thật được
  kiểm tại `load_inputs`. Markdown paths trong `BuilderInputs` phải đã kiểm tồn tại.
- `map_nodes(validated, contract)` trả dict `{type, id, name, properties}`.
- `map_relation_rows(validated, contract)` giữ tất cả contributing rows, tuple,
  application key, logical properties, invariant candidates và locator.
- `aggregate_relations(rows, contract)` trả dict `{tuple, application_edge_key,
  properties}` với physical properties. Tuple gồm `(from_type, from_id, predicate,
  to_type, to_id)`; types fully qualified. Evidence nằm ngoài identity.

Containers frozen; dicts/specs immutable-by-convention, caller không sửa inputs
sau validation. Output provenance có bản sao riêng. Không runner full-source,
writer hoặc vectorization ở các module này.

Tests dùng synthetic records/file nhỏ. Chạy từ project root, bằng Python hiện có:

```powershell
rtk proxy python -B -m unittest discover -s tests/builder -p 'test_*.py' -v
rtk proxy python -B -c "import unittest; suite=unittest.TestSuite([unittest.TestLoader().discover('tests/schema'), unittest.TestLoader().discover('tests/builder')]); result=unittest.TextTestRunner(verbosity=1).run(suite); raise SystemExit(not result.wasSuccessful())"
```

Schema tests cần environment chứa các dependency parser đã cài của project.
Builder tests không cần dependency ngoài stdlib hoặc internet.
