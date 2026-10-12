# Kiểm thử Builder

Tests dùng records/files synthetic và transport/model doubles; không gọi graph, embedding hoặc provider thật.

## Phạm vi

- Codec: logical/physical keys, native Integer, Boolean Text và JSON encode/decode; `server_encoded=True` chỉ đọc thêm một lớp JSON ngoài.
- Inputs: identity/hierarchy/joins, production scope, fingerprint ledger/policy và hash file. Fixtures cấp hash riêng, không sửa contract/source production.
- Mapping/graph plan: node/edge identity, provenance, polarity SAFE_EDGE, aggregation và canonical ordering/hash.
- Writer adapter: exact scope, payload validation, node readback trước edge và chặn thao tác ngoài manifest.
- Vectorizer: retry có giới hạn, checkpoint/resume, cache identity, chunk fallback và gate khi vectorization chưa hoàn thành.

Source: [kag/builder](../../kag/builder/). Codec/inputs/mapping/graph plan dùng stdlib; writer/vectorizer tests cần SDK/dependencies đã pin.

## Chạy

Từ root checkout trong [runtime chuẩn](../../docs/runtime.md), chạy process riêng:

```sh
python -B -m unittest discover -s tests/builder -p "test_*.py" -v
```

Giữ source read-only và network denied. Kết quả synthetic không chứng minh graph write, provider reliability hoặc production readiness.
