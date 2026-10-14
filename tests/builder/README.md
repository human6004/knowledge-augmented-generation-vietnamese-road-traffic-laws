# Tests Builder

Fixtures synthetic/transport/model doubles kiểm codec, inputs/joins, graph plan/provenance/SAFE_EDGE, writer scope/node barrier và vector retry/checkpoint/chunk fallback. Không gọi graph/provider thật.

Source: [`kag/builder/`](../../kag/builder/); writer/vectorizer cần SDK pin. Chạy suite `builder` theo [hướng dẫn tests](../README.md#chạy-suite), giữ source read-only/network denied/output ngoài repo.
