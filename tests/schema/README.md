# Kiểm thử schema

[test_schema_contract.py](test_schema_contract.py) kiểm [schema/contract](../../kag/schema/): parser/model KAG đúng pin, namespace, inheritance từ Thing, property mappings, predicates, codec, SAFE_EDGE và runtime requirements.

Chạy offline từ root checkout trong [runtime chuẩn](../../docs/runtime.md), với dependency parser `six`:

```sh
python -B -m unittest discover -s tests/schema -p "test_*.py" -v
```

Không gọi server/model. Kết quả xác nhận contract/parser trên source đã pin; không xác nhận schema hoặc graph đang chạy trên backend live.
