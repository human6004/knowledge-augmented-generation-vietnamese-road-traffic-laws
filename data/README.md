# Vietnamese Road Traffic Legal Dataset

## 1. Dataset này là gì?

Bộ dữ liệu pháp luật giao thông đường bộ Việt Nam (luật, nghị định, thông tư, QCVN, văn bản hợp nhất), được chuẩn hóa để dùng cho retrieval, knowledge graph, KAG và đánh giá về sau.

Repo này hiện chỉ là **lớp dữ liệu (dataset layer)**. Hệ thống truy xuất, KAG và suy luận chưa thuộc repo này. Trạng thái hiện tại: **Dataset Lock R2 — 02/10/2026**.

## 2. Luồng dữ liệu

```text
raw/                      file nguồn gốc (PDF / HTML / DOC)
  ↓
processed/documents/      Markdown chuẩn hóa, mỗi văn bản một file
  ↓
processed/units/          tách thành Điều / Khoản / Điểm (và QCVN)
  ↓
  ├── xrefs        tham chiếu trong nội dung (Điều này dẫn tới đâu)
  ├── relations    quan hệ giữa các văn bản
  └── penalties / signs    dữ liệu miền: xử phạt, biển báo
  ↓
retrieval / graph / evaluation (làm sau, ngoài repo này)

metadata/   ↳ mô tả và kiểm tra toàn bộ dataset
```

Văn bản gốc trong `raw/` được chuyển thành Markdown chuẩn hóa, rồi tách thành các đơn vị pháp lý (units) có id ổn định, ví dụ `100_2019_ND_CP::D5::K1::Pa` = văn bản `100_2019_ND_CP`, Điều 5, Khoản 1, Điểm a. Từ units, dataset trích ra tham chiếu, quan hệ giữa văn bản và dữ liệu miền (xử phạt, biển báo).

**xrefs ≠ relations.**
- `xrefs` = tham chiếu nằm *trong nội dung* pháp lý, thường ở mức Điều/Khoản/Điểm (ví dụ "theo khoản 2 Điều 5").
- `relations` = quan hệ *giữa các văn bản*, gồm 5 loại: `cites`, `amends`, `repeals`, `implements`, `consolidates`.

## 3. Cấu trúc thư mục

Tất cả đường dẫn dưới đây tính từ thư mục `data/`.

| Path | Chứa gì? | Dùng để làm gì? |
|---|---|---|
| `raw/` | 215 file nguồn: `pdf/` (171), `html/` (38), `doc/` (6, gồm .docx và .doc) | Đối chiếu, kiểm chứng khi nội dung đã trích có vẻ sai |
| `processed/documents/` | 91 file Markdown chuẩn hóa, tên theo `doc_id` | Đọc toàn văn, tìm kiếm văn bản |
| `processed/units/` | `units.jsonl`: Điều, Khoản, Điểm, QCVN, QCVN_Muc | Đơn vị truy xuất / trích dẫn nhỏ nhất |
| `processed/meta/` | `documents.jsonl`, `xrefs.jsonl`, `relations.jsonl` | Metadata văn bản, tham chiếu và quan hệ cốt lõi |
| `processed/penalties/` | `penalties.jsonl` (+ `excluded_out_of_scope.jsonl`) | Các đơn vị có thông tin xử phạt |
| `processed/signs/` | `signs.jsonl` | Biển báo trích từ QCVN |
| `processed/eval/` | `eval_questions.jsonl` | Câu hỏi benchmark để đánh giá |
| `processed/out_of_scope/` | Markdown, units, xrefs, relations của văn bản ngoài phạm vi | Giữ để audit / tham khảo, không thuộc production corpus |
| `metadata/` | `corpus.json`, `document_inventory.csv`, `sources.csv`, `checksums.json` | Thống kê, danh mục văn bản, nguồn, checksum |

## 4. Các file quan trọng

- `processed/meta/documents.jsonl` — mỗi dòng một văn bản (`doc_id`, `so_hieu`, tiêu đề, loại, cơ quan, ngày hiệu lực, trạng thái…). `doc_id` là khóa nối giữa các lớp dữ liệu.
- `processed/units/units.jsonl` — cây Điều → Khoản → Điểm của từng văn bản, cùng QCVN/QCVN_Muc cho quy chuẩn. Mỗi dòng có `unit_id`, `parent_id`, `unit_type`, `text`.
- `processed/meta/xrefs.jsonl` — tham chiếu từ một unit tới Điều/Khoản/Điểm khác (`from_unit_id`, `to_unit_id`, `scope` internal/external, `in_corpus`, `is_exclusion`, `evidence`). **Không phải dòng nào cũng là cạnh đồ thị hợp lệ** — xem mục Lưu ý.
- `processed/meta/relations.jsonl` — quan hệ giữa các văn bản:
  - `cites`: văn bản này dẫn chiếu văn bản kia;
  - `amends`: sửa đổi, bổ sung;
  - `repeals`: bãi bỏ / hết hiệu lực;
  - `implements`: hướng dẫn, quy định chi tiết thi hành;
  - `consolidates`: văn bản hợp nhất (VBHN) hợp nhất văn bản gốc.
- `processed/penalties/penalties.jsonl` — mỗi dòng là một unit có xử phạt: đối tượng, hành vi, mức phạt tiền min/max, trừ điểm / tước GPLX, tịch thu.
- `processed/signs/signs.jsonl` — mỗi dòng là một biển báo: `ma_bien`, nhóm, tên, mô tả, QCVN nguồn và `unit_id`.
- `processed/eval/eval_questions.jsonl` — 71 câu hỏi benchmark (`cau_hoi`, `gold_unit_ids`, `dap_an_ngan`…). Đây là dữ liệu đánh giá, **không phải nguồn luật**.
- `processed/out_of_scope/` — dữ liệu của văn bản cố ý loại khỏi production (xem mục 6).
- `metadata/corpus.json` — số lượng record của dataset; `document_inventory.csv` — danh mục văn bản; `sources.csv` — nguồn từng văn bản; `checksums.json` — SHA-256 để kiểm tra các file production trong `processed/`.

## 5. Muốn tìm dữ liệu gì thì xem ở đâu?

- Toàn văn văn bản → `processed/documents/`
- Điều / Khoản / Điểm → `processed/units/units.jsonl`
- Điều này dẫn tới đâu → `processed/meta/xrefs.jsonl`
- Văn bản nào sửa / bãi bỏ văn bản nào → `processed/meta/relations.jsonl`
- Mức phạt → `processed/penalties/penalties.jsonl`
- Biển báo → `processed/signs/signs.jsonl`
- Benchmark → `processed/eval/eval_questions.jsonl`
- Nguồn gốc, hash, thống kê → `metadata/` và `raw/`

## 6. Production và out-of-scope

Có **92** bản ghi văn bản trong `documents.jsonl`, trong đó **91** thuộc production corpus (có Markdown trong `processed/documents/`) và **1** cố ý ngoài phạm vi: `22_VBHN_BXD`. Dữ liệu của văn bản này nằm riêng trong `processed/out_of_scope/` (và `penalties/excluded_out_of_scope.jsonl`). Không trộn vào graph hoặc dữ liệu production nếu không có chủ đích.

## 7. Checkpoint: Dataset Lock R2 — 02/10/2026

| Thành phần | Số lượng |
|---|---|
| Documents (metadata) | 92 |
| Production documents (Markdown) | 91 |
| Units | 55.597 |
| Xrefs | 17.512 |
| Relations | 821 (cites 690, repeals 37, amends 44, implements 32, consolidates 18) |
| Penalties | 1.966 |
| Signs | 887 |

## 8. Lưu ý khi sử dụng

1. **Xrefs làm cạnh đồ thị:** chỉ dùng các tham chiếu được phân loại `downstream_use == "SAFE_EDGE"` (8.144 trong 17.512 dòng). `in_corpus = true` chỉ cho biết văn bản đích có trong corpus, **không** đảm bảo `to_unit_id` tồn tại trong `units.jsonl`. Trường `downstream_use` hiện chưa nằm trong `xrefs.jsonl` (bảng phân loại được giữ ngoài repo), nên cần đính kèm bảng này trước khi dựng graph; tối thiểu phải kiểm tra `to_unit_id` có trong `units.jsonl`.
2. **`out_of_scope/` không phải production corpus.**
3. **`eval_questions.jsonl` là dữ liệu benchmark**, không dùng làm nguồn luật hay đưa vào corpus truy xuất.
4. **`raw/`** dùng để kiểm chứng khi nội dung đã trích có vấn đề.
5. **Dataset đã LOCKED R2:** các công việc schema / graph về sau nên coi đây là baseline, không sửa trực tiếp file production.

Xem thêm [DATASHEET.md](DATASHEET.md) để biết chi tiết về dataset. Điều kiện sử dụng nằm trong [LICENSE.md](LICENSE.md).
