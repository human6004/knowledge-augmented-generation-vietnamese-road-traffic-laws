# Knowledge-Augmented Generation for Reasoning over Vietnamese Road Traffic Laws

Bộ dữ liệu pháp luật giao thông đường bộ Việt Nam, làm nền cho nghiên cứu Knowledge-Augmented Generation (KAG) và suy luận có dẫn chứng pháp lý.

Repo hiện chứa dữ liệu nguồn và dữ liệu đã chuẩn hóa. Hệ thống truy xuất, sinh câu trả lời và suy luận KAG chưa được triển khai trong repo.

## Trạng thái hiện tại

Checkpoint dữ liệu ngày 02/10/2026:

- 92 văn bản metadata; 91 văn bản Markdown trong corpus chính.
- 55.597 đơn vị pháp lý (units).
- 17.512 tham chiếu (xrefs); 819 quan hệ giữa văn bản.
- 1.966 bản ghi xử phạt; 887 bản ghi biển báo.

A2 đã khóa cấu trúc units. A3 (xrefs) và A4 (relations) đã khóa. Một số tham chiếu vẫn unresolved hoặc cần đối chiếu nguồn.

Các số liệu tổng hợp trong `metadata/corpus.json` đã được làm mới và khớp với số liệu trên (đếm trực tiếp từ JSONL hiện tại). Repo này không chứa scripts và báo cáo review nằm trong workspace riêng.

## Cấu trúc

knowledge-augmented-generation-vietnamese-road-traffic-laws/
├── raw/
├── processed/
├── metadata/
├── README.md
├── DATASHEET.md
└── LICENSE.md

raw/
Dữ liệu nguồn được lưu từ các văn bản gốc.

processed/
Dữ liệu đã được chuẩn hóa để sử dụng cho phân tích và các ứng dụng xử lý dữ liệu.

metadata/
Thông tin mô tả corpus, nguồn dữ liệu và checksum.

## processed/

documents/ — văn bản ở định dạng Markdown.

meta/ — thông tin văn bản và các quan hệ giữa văn bản.

units/ — các đơn vị cấu trúc pháp lý như Điều, Khoản và Điểm.

penalties/ — thông tin về xử phạt.

signs/ — thông tin liên quan đến biển báo.

eval/ — dữ liệu phục vụ đánh giá.

out_of_scope/ — dữ liệu được lưu lại nhưng không thuộc corpus chính.

## metadata/

corpus.json — quy mô của corpus.

document_inventory.csv — danh mục văn bản trong dataset.

sources.csv — nguồn của từng văn bản.

checksums.json — mã SHA-256 của các tệp trong processed/.

## Ghi chú

Dataset giữ lại dữ liệu nguồn trong raw/ để có thể đối chiếu với dữ liệu đã xử lý.

Xem DATASHEET.md để biết thêm thông tin về dataset. Điều kiện sử dụng nằm trong LICENSE.md.
