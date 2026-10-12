# Retrieval và đánh giá frozen slice

`kag/retriever` truy hồi bằng bốn vector nội dung và đọc lại chứng cứ theo ID
chính xác. Helper frozen slice dùng để kiểm đường đi retrieval trên sample;
Evaluation Framework đầy đủ nằm trong [kiến trúc](architecture.md#evaluation-framework).
Kết quả helper không phải benchmark pháp lý chính thức.

Retrieval đọc graph, có thể gọi embedding cho câu hỏi; không gọi Solver/LLM
sinh đáp án, writer, cập nhật project/schema hoặc production runner.

```python
from kag.retriever.neo4j import Neo4jRetrievalClient
from kag.retriever.retriever import Retriever

# reader dùng physical DB đã được BackendIdentitySession xác minh.
# embed khớp endpoint/model/dimension trong provenance graph.
retriever = Retriever(reader, embed, schema_contract, search_k=10)
evidence = retriever.retrieve(question, top_k=10, expand=False)
# Nếu đã có vector hợp lệ: retriever.retrieve_vector(vector, top_k=10).
```

Entrypoint dùng SDK gọi `kag.bootstrap.initialize()` trước import adapter SDK.
Core retrieval/evaluation không tự tải SDK hoặc tạo provider. Không dùng generic
retriever với schema `Chunk/content`. HTTP SAMPLE còn cần serving proof và
ngân sách provider theo [hướng dẫn cài đặt](INSTALL.md).

## Vector và chứng cứ

Bốn target lấy từ [vector_contract.py](../kag/vector_contract.py):
`LegalUnit.text`, `LegalDocument.title`, `TrafficSign.ten`, `TrafficSign.moTa`.
Transport chọn đúng một index theo label/property, yêu cầu ONLINE, dimension
3072 và cosine. Query vector phải có 3072 số hữu hạn và khác vector zero.
Neo4j lookup trả ID/score; cosine score phải trong `[0,1]`.

Hydrate đọc node theo fully-qualified type + ID. Neo4jReadClient bỏ outer JSON
layer đúng một lần; semantic codec xử lý JSON_TEXT. Giữ ID, Unicode, occurrence
suffix và toàn bộ source text, không trim hoặc cắt nội dung.

Evidence gồm `entity_type`, `entity_id`, `doc_id`, `unit_id`/`sign_id` nếu có,
`source_texts`, `score`, `vector_sources` và `graph_context`. Dedup theo type + ID;
giữ nguồn vector từng field và score cao nhất của field đó. Mỗi target tìm
`search_k` candidates; chọn tối đa `top_k` seed chung, xếp score giảm dần rồi
type/ID. Thứ tự tie xác định trên candidates được trả về; ANN có thể đổi tập
candidates khi index/runtime thay đổi.

Expansion mặc định tắt. Khi bật: một hop, mặc định tối đa 50 relation, chỉ dùng
`hasUnit`, `hasChild`, `hasSign`, `citesUnit`, `excludesUnit`, `cites`, `amends`,
`repeals`, `implements`, `consolidates`. Endpoint types phải khớp schema và mỗi
relation phải chạm seed. Seed giữ thứ tự; node mở rộng dedup, thêm theo type/ID.
Graph-only evidence có `score=null`, `vector_sources=[]`; context giữ exact
from/predicate/to. Với giới hạn mặc định, kết quả có tối đa `top_k` seed và 50
node bổ sung.

## Frozen slice và metrics

[build_demo_slice](../kag/retriever/evaluation.py) chọn câu có
**nonempty gold_unit_ids ⊆ exact sample LegalUnit IDs**. Giữ byte từng dòng
eligible, thứ tự và metadata nguồn; không sửa dataset/sample/gold. Output phải
là artifact mới ngoài repo, không overwrite nguồn hoặc artifact đã freeze.
Manifest chứa hash nguồn, sample identity, slice, lý do loại và phân bố
category/source.

`evaluate(questions, predictions, ks=(1,5,10))` yêu cầu đúng một prediction mỗi QID.
`unit_ids` là projection LegalUnit từ evidence order, dedup ID chính xác.
`TrafficSign.unit_id` chỉ là anchor metadata, không tự tính là LegalUnit được
truy hồi. Document/sign giữ trong evidence, không chiếm rank unit metrics;
số unit có thể thấp hơn global `top_k`.

- Hit@k: 1 nếu top-k có ít nhất một gold, ngược lại 0.
- Recall@k: số gold unique trong top-k / tổng gold unique.
- MRR: nghịch đảo rank gold đầu tiên trong toàn ranking, 0 nếu không có.
- MRR@k: nghịch đảo rank nếu rank ≤ k, ngược lại 0.

Macro average theo overall/category/source; metadata thiếu giữ `unknown`,
không suy nguồn viết tay/tự động. Missing/extra/duplicate prediction hoặc gold
sai định dạng bị từ chối. Slice rỗng trả `BLOCKED`, metrics null; không thay
undefined bằng 0 hoặc 1. Freeze cutoffs, `search_k` và expansion trước retrieval,
không tuning theo gold. Thiếu gold nằm trong graph phải báo phạm vi không đủ,
không sửa gold/sample để mở gate đánh giá.
