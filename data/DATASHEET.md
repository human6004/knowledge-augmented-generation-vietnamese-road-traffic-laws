# Dataset Overview

Tên dataset:
Vietnamese Road Traffic Legal Dataset

Mục đích:
Tập hợp và chuẩn hóa các văn bản pháp luật liên quan đến giao thông đường bộ Việt Nam.

Ngôn ngữ:
Tiếng Việt.

## Data Sources

Nguồn chính là các văn bản pháp luật và Công báo được lưu trong raw/.

Đường dẫn nguồn của từng văn bản nằm trong metadata/sources.csv. Danh mục văn bản nằm trong metadata/document_inventory.csv.

## Dataset Structure

raw/
Nguồn gốc, gồm các tệp PDF, HTML và DOC.

processed/
Dữ liệu đã chuẩn hóa.

metadata/
Thông tin mô tả dataset và nguồn.

## Processed Data

documents/
Văn bản Markdown.

meta/
Metadata văn bản, quan hệ giữa văn bản và tham chiếu.

units/
Cấu trúc pháp lý: Điều, Khoản và Điểm.

penalties/
Thông tin xử phạt.

signs/
Thông tin biển báo.

eval/
Dữ liệu đánh giá.

out_of_scope/
Văn bản được lưu để tham khảo nhưng không thuộc corpus chính.

## Current Dataset

Đếm từ production JSONL ngày 02/10/2026. `metadata/corpus.json`, `metadata/sources.csv` và `metadata/checksums.json` mô tả cùng tập dữ liệu production.

- 92 văn bản metadata
- 91 văn bản production Markdown
- 55,597 production units
- 821 relations
- 17,512 xrefs
- 1,966 penalties
- 887 signs

Một văn bản khác được lưu trong processed/out_of_scope/ và không thuộc corpus chính.

## Known Limitations

- Một số ký tự trong văn bản nguồn bị lỗi ngay từ bản Công báo.
- Một số tham chiếu dẫn tới văn bản ngoài corpus.
- Một số trang scan cũ có giới hạn chất lượng OCR.

## License

Xem LICENSE.md.
