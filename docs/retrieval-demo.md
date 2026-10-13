# Retrieval và đánh giá frozen slice

Hợp đồng stable của `kag/retriever` và helper exact-ranking/frozen-slice.
Evaluation Framework G1/G2 hiện tại được mô tả trong
[kiến trúc sản phẩm](architecture.md#evaluation-framework). Các names
E-DEMO/G1-DEMO và external evidence cuối tài liệu là checkpoint lịch sử;
không phải trạng thái official benchmark hôm nay.

Retrieval chỉ đọc graph sample, không gọi Solver/LLM, writer, project mutation,
schema update hoặc production runner. Production WRITE vẫn BLOCKED.

```python
from kag.retriever.neo4j import Neo4jRetrievalClient
from kag.retriever.retriever import Retriever

# reader phải trỏ đúng physical DB đã được BackendIdentitySession xác minh.
# embed dùng cùng endpoint/model/dimension với provenance sample.
retriever = Retriever(reader, embed, schema_contract, search_k=10)
evidence = retriever.retrieve(question, top_k=10, expand=False)
```

Entrypoint SDK thật gọi `kag.bootstrap.initialize()` trước import adapter SDK.
Core retrieval/evaluation dùng stdlib và codec hiện có, không tự tải SDK.
Không instantiate generic retriever với `Chunk/content`.

Bốn target lấy từ `kag.builder.resilient_vectorizer.TARGETS`:
`LegalUnit.text`, `LegalDocument.title`, `TrafficSign.ten`, `TrafficSign.moTa`.
Transport chọn đúng một index theo label/property, yêu cầu ONLINE, 3072, cosine.
Query vector phải đủ 3072 giá trị hữu hạn, khác vector zero. Neo4j vector lookup
chỉ trả exact ID/score; score cosine phải trong [0,1]. Hydrate đọc graph node
bằng fully-qualified type + ID.
Codec giải outer JSON layer đúng một lần qua Neo4jReadClient rồi semantic codec.
Không normalize Unicode, trim ID, đổi suffix hoặc cắt source text.

Evidence: entity_type/entity_id, doc_id, unit_id/sign_id nếu có, source_texts
đầy đủ, score, vector_sources (property/index/score), graph_context.
Dedup theo exact entity type + ID; giữ nguồn vector từng field, highest score
cho cùng field. Global seed order = score giảm dần, type/ID làm tie-break.
Mỗi target tìm search_k; chọn tối đa top_k seed từ bốn target. ANN candidate
membership phụ thuộc index/runtime; tie order của returned candidates deterministic.
Không hứa ANN luôn trả cùng candidate set qua thay đổi runtime/index.

Expansion mặc định tắt; bật thì một hop, tối đa 50 relation, chỉ 10 predicates:
hasUnit, hasChild, hasSign, citesUnit, excludesUnit, cites, amends, repeals,
implements, consolidates. Kiểm schema endpoint types và ít nhất một seed liên quan.
Seed giữ thứ tự; node mở rộng dedup rồi thêm theo type/ID. Graph-only evidence
score=null, vector_sources=[]; context lưu exact from/predicate/to. Result có
thể gồm top_k seed và tối đa 50 node bổ sung; graph-only không giả score.

Slice chọn **nonempty gold_unit_ids ⊆ exact sample LegalUnit IDs**. Giữ byte gốc
từng dòng eligible và metadata; không sửa dataset/sample/gold. Output mới ngoài
repo; nguồn hoặc artifact đã freeze không được overwrite. Manifest chứa source,
sample identity và slice SHA256, exclusions và category/source distributions.

`evaluate(questions, predictions, ks=(1,5,10))` yêu cầu đúng một prediction mỗi QID.
Prediction `unit_ids` là projection **LegalUnit entities** từ evidence order,
dedup exact ID; TrafficSign.unit_id là anchor metadata, không tự tính là retrieved
LegalUnit. Document/sign giữ trong evidence, không chiếm rank unit metrics.
Với global top_k seed, số unit thực tế có thể thấp hơn k.

- Hit@k = 1 nếu top-k có ít nhất một gold.
- Recall@k = số gold unique trong top-k / tổng gold unique.
- MRR = reciprocal rank gold đầu tiên trong toàn ranking được cung cấp.
- MRR@k = reciprocal rank nếu rank ≤ k, ngược lại 0.

Macro average overall/category/source; source giữ metadata nguyên gốc, không suy
nguồn viết tay/tự động khi metadata thiếu. Missing/extra/duplicate prediction hoặc
gold malformed bị từ chối. Slice rỗng trả BLOCKED và metrics null; không dùng 0
hay 1 để thay cho undefined. Cutoffs 1/5/10, search_k=10, expansion off được freeze
trước retrieval; không tuning hoặc threshold theo gold.

Sample partition-5 hiện không chứa bất kỳ văn bản gold nào của eval 71 câu.
Do đó smoke có thể chứng minh code path, nhưng G1-DEMO chưa thể PASS.
Số demo không phải paper/production metrics. Legal Solver và G2 framework đã
có implementation riêng; slice rỗng vẫn BLOCKED, không được sửa gold/sample
để mở gate. Không tự khởi động Solver/provider từ hợp đồng retrieval này.

Evidence checkpoint lịch sử: `D:/study/caoDATA-workspace/e-demo-g1-demo/`.
