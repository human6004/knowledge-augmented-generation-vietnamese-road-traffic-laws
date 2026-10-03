# Kiểm thử schema

`test_schema_contract.py` kiểm tra schema bằng parser/model KAG đã pin,
contract miền, inheritance từ Thing, codec, SAFE_EDGE và yêu cầu runtime.
Kiểm thử deterministic, chạy offline; cần Python có dependency `six` của SDK.

Chạy từ root dự án:

```sh
python -B tests/schema/test_schema_contract.py
python -B -m unittest discover -s tests/schema -p "test_*.py" -v
```
