# Phase B1 — Legal Domain Model Proposal

Ngày audit: 02/10/2026. Baseline: **LOCKED R2**. Phạm vi: kiểm kê nguồn và đề xuất thiết kế; không triển khai schema, ingestion, graph hoặc benchmark.

**Khuyến nghị:** 3 node `LegalDocument`, `LegalUnit`, `TrafficSign`; Penalty gộp thuộc tính vào LegalUnit. Một loại LegalUnit giữ nguyên 5 giá trị `unit_type`. Đề xuất 10 loại cạnh, trong đó 2 loại xref chưa được phép nạp khi thiếu bảng `SAFE_EDGE`.

## 1. Dataset inputs inspected

Quét toàn bộ dòng của 6 JSONL chính bằng Python stdlib; thống kê union trường, kiểu, null/rỗng, enum, tính duy nhất và khóa ngoại. Đọc mẫu cho từng loại unit, xref exclusion/null, từng loại document relation, penalty cảnh cáo và biển thiếu tên. Không dùng README thay cho record.

| Nguồn trong data/ | Phạm vi kiểm tra | Số lượng thực |
|---|---|---:|
| `processed/meta/documents.jsonl` | Toàn bộ schema/record | 92 |
| `processed/units/units.jsonl` | Toàn bộ schema, ID, parent, chu trình | 55,597 |
| `processed/meta/xrefs.jsonl` | Toàn bộ schema, endpoint, exclusion | 17,512 |
| `processed/meta/relations.jsonl` | Toàn bộ schema, flags, endpoint | 821 |
| `processed/penalties/penalties.jsonl` | Toàn bộ schema, cardinality, endpoint | 1,966 |
| `processed/signs/signs.jsonl` | Toàn bộ schema, tên, endpoint | 887 |
| `processed/eval/eval_questions.jsonl` | Schema và mẫu; không dùng đáp án làm luật | 71 |
| `metadata/corpus.json` | Toàn bộ thống kê | Khớp baseline |
| `metadata/document_inventory.csv`, `metadata/sources.csv` | Header, số dòng, mẫu | 92 mỗi file |
| `metadata/checksums.json` | Kiểm tra SHA-256 thực của mọi entry | 103/103 khớp |
| `README.md`, `DATASHEET.md` | Đọc mô tả và chính sách | 2 file |
| `processed/documents/` | Kiểm kê 91 tên file; đọc mẫu 3 Markdown dưới đây | 91 |

Mẫu Markdown: `100_2019_ND_CP.md`, `51_2024_TT_BGTVT.md`, `48_2024_TT_BGTVT.md`. Tổng 16 file dữ liệu/tài liệu được đọc nội dung phục vụ audit; kiểm tra hash bao phủ rộng hơn. Mục 14 liệt kê 10 file upstream đọc toàn bộ hoặc đoạn liên quan: **FILES_INSPECTED = 26**. Không cần đọc dự án cũ; không sử dụng domain model cũ.

**Sai lệch/giới hạn quan sát được:**

- Số lượng trong README, DATASHEET và `corpus.json` khớp JSONL. DATASHEET mô tả units chỉ bằng Điều/Khoản/Điểm, thiếu QCVN/QCVN_Muc trong mô tả ngắn.
- README nêu 8.144 SAFE_EDGE và nói bảng phân loại nằm ngoài repo. JSONL đúng là không chứa `downstream_use`; không có bảng phân loại trong `data/`. Số 8.144 chưa thể tái xác minh từ artifact hiện có.
- `documents.n_units` không khớp units thực ở 4 văn bản: `48_2024_TT_BGTVT` 3.823→3.841; `71_2024_TT_BCA` 131→75; `55_2024_TT_BGTVT` 422→279; `30_2026_TT_BXD` 492→341. Dùng record thực, không dùng counter metadata để dựng graph.
- 10 metadata vẫn ghi `scrape_status=raw_only_not_processed`, dù đều có Markdown và units production. Không dùng trường này làm điều kiện loại.
- `documents.sha256` của 91 văn bản production không bằng hash bytes Markdown hiện tại. Chưa xác định quy ước hash cũ; không kết luận file hỏng. `metadata/checksums.json` mới là manifest bytes đã kiểm chứng. Ví dụ `sources.csv` còn ghi `text_chars=326401`, `loai=NĐ` cho `100_2019_ND_CP`, còn documents ghi 326388 và “Nghị định”.
- Không sửa các sai lệch. Các ngày/trạng thái là dữ liệu của snapshot, không phải kết luận pháp lý đã xác minh theo thời gian hiện tại.

## 2. Actual source schemas

Các bảng dưới liệt kê **mọi trường quan sát được**, không chỉ dòng mẫu. “Có mặt” bằng tổng dòng = trường common; nhỏ hơn tổng dòng = optional. Null và chuỗi rỗng khác nhau; không tự đổi thành 0/false. “Bắt buộc” trong mapping mục 11 là hợp đồng đề xuất, không phải JSON Schema sẵn có. Giá trị mẫu dài được rút gọn.

**`data/processed/meta/documents.jsonl` — 92 dòng; 49 trường.**

| Trường | Kiểu thực tế | Có mặt | Null | Rỗng | Giá trị mẫu |
|---|---|---:|---:|---:|---|
| `amended_by` | array (8) | 8 | 0 | 0 | ["09/2025/TT-BXD"] |
| `amends` | array (6) | 6 | 0 | 0 | ["118/2021/NĐ-CP"] |
| `co_quan` | string (92) | 92 | 0 | 0 | Chính phủ |
| `consolidates` | array (1) | 1 | 0 | 0 | ["59/2024/QH15","85/2025/QH15","05/2026/QH16"] |
| `consolidation_as_of` | string (14) | 14 | 0 | 0 | 2026-03-17 |
| `current_status` | string (32) | 32 | 0 | 0 | REPLACED |
| `doc_id` | string (92) | 92 | 0 | 0 | 100_2019_ND_CP |
| `document_role` | string (10) | 10 | 0 | 0 | ORIGINAL |
| `effective_from` | string (78) | 78 | 0 | 0 | 2020-01-01 |
| `effective_to` | string (11) | 11 | 0 | 0 | 2025-01-01 |
| `het_hieu_luc_note` | string (11) | 11 | 0 | 0 | bị 168/2024/NĐ-CP thay thế/bãi bỏ |
| `hieu_luc_note` | string (83) | 83 | 0 | 0 | Nghị định này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2020 |
| `identity_note` | string (1) | 1 | 0 | 0 | Cùng số ngắn với 27_VBHN_BXD nhưng khác văn bản; doc_id và nguồn phân biệt. |
| `legal_domains` | array (12) | 12 | 0 | 0 | ["INLAND_WATERWAY"] |
| `loai` | string (92) | 92 | 0 | 0 | Nghị định |
| `n_dieu` | integer (92) | 92 | 0 | 0 | 87 |
| `n_parts` | integer (53) | 53 | 0 | 0 | 2 |
| `n_qcvn` | integer (42) | 42 | 0 | 0 | 0 |
| `n_qcvn_muc` | integer (42) | 42 | 0 | 0 | 0 |
| `n_units` | integer (92) | 92 | 0 | 0 | 1883 |
| `ngay_ban_hanh` | string (92) | 92 | 0 | 0 | 2019-12-30 |
| `ngay_het_hieu_luc` | string (12) | 12 | 0 | 0 | 2025-01-01 |
| `ngay_hieu_luc` | string (78), null (14) | 92 | 14 | 0 | 2020-01-01 |
| `ngay_hieu_luc_bo_phan` | array (18) | 18 | 0 | 0 | ["2027-07-01"] |
| `official_so_hieu` | string (1) | 1 | 0 | 0 | 27/VBHN-BXD |
| `parse_version` | string (42) | 42 | 0 | 0 | v8c_unique_id+wm_strip |
| `phan_lien_quan` | string (7) | 7 | 0 | 0 | phần sửa NĐ 151/2024/NĐ-CP |
| `raw_file_sha256` | object (11) | 11 | 0 | 0 | {"raw/pdf/36_2024_TT_BYT.pdf":"1c961895952e7c055e136696161deba494c6a341b894c7d9… |
| `raw_files` | array (92) | 92 | 0 | 0 | ["raw/html/100_2019_ND_CP.html","raw/pdf/100_2019_ND_CP.pdf","raw/pdf/100_2019_… |
| `reason` | string (20) | 20 | 0 | 0 | fixed_wrong_QD1003_mismatch |
| `repealed_by` | string (6) | 6 | 0 | 0 | 14/2025/TT-BXD |
| `repeals` | array (2) | 2 | 0 | 0 | ["47/2024/TT-BGTVT"] |
| `replaced_by` | string (3) | 3 | 0 | 0 | 89/2026/NĐ-CP |
| `replaces` | array (1) | 1 | 0 | 0 | ["166/2024/NĐ-CP"] |
| `scope` | string (92) | 92 | 0 | 0 | road_related |
| `scrape_status` | string (91) | 91 | 0 | 0 | ok |
| `sha256` | string (92) | 92 | 0 | 0 | c94ef82ea0a327fe039f5522953dfe3359ef4daa410b4bd860d17bd8bfe2ca8d |
| `so_hieu` | string (92) | 92 | 0 | 0 | 100/2019/NĐ-CP |
| `source_kind` | string (92) | 92 | 0 | 0 | congbao_pdf |
| `source_mark` | null (16) | 16 | 16 | 0 | null |
| `source_note` | string (6) | 6 | 0 | 0 | URL bổ sung từ congbao_index |
| `source_quality` | string (11) | 11 | 0 | 0 | OFFICIAL |
| `source_url` | string (92) | 92 | 0 | 0 | https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-100-2019-nd-cp-30341/29265.htm |
| `status` | string (6) | 6 | 0 | 0 | ok |
| `status_hint` | string (86) | 86 | 0 | 16 | SUPERSEDED bởi 168/2024 |
| `text_chars` | integer (92) | 92 | 0 | 0 | 326388 |
| `tier` | string (92) | 92 | 0 | 0 | Superseded |
| `title` | string (92) | 92 | 0 | 0 | Xử phạt VPHC GTĐB và đường sắt (superseded) |
| `underlying_effective_from` | string (11) | 11 | 0 | 0 | 2025-01-01 |

**`data/processed/units/units.jsonl` — 55,597 dòng; 18 trường.**

| Trường | Kiểu thực tế | Có mặt | Null | Rỗng | Giá trị mẫu |
|---|---|---:|---:|---:|---|
| `diem_letter` | string (22960) | 22960 | 0 | 0 | a |
| `diem_occurrence` | integer (22960) | 22960 | 0 | 0 | 1 |
| `dieu_number` | string (51413) | 51413 | 0 | 0 | 1 |
| `dieu_occurrence` | integer (5138) | 5138 | 0 | 0 | 1 |
| `doc_id` | string (55597) | 55597 | 0 | 0 | 100_2019_ND_CP |
| `khoan_number` | string (46275) | 46275 | 0 | 0 | 1 |
| `khoan_occurrence` | integer (23759) | 23759 | 0 | 0 | 1 |
| `order` | integer (55597) | 55597 | 0 | 0 | 1 |
| `parent_id` | null (5046), string (50551) | 55597 | 5046 | 0 | 100_2019_ND_CP::D1 |
| `qcvn_id` | string (4184) | 4184 | 0 | 0 | QCVN04:2024/BGTVT |
| `scope` | string (5497) | 5497 | 0 | 0 | TT |
| `section_number` | string (4102) | 4102 | 0 | 0 | 1.1 |
| `section_occurrence` | integer (4102) | 4102 | 0 | 0 | 1 |
| `so_hieu` | string (55597) | 55597 | 0 | 0 | 100/2019/NĐ-CP |
| `text` | string (55597) | 55597 | 0 | 0 | Điều 1. Phạm vi điều chỉnh  ⏎ 1. Nghị định này quy định về hành vi vi phạm hành… |
| `title` | string (9216), null (46381) | 55597 | 46381 | 0 | Phạm vi điều chỉnh |
| `unit_id` | string (55597) | 55597 | 0 | 0 | 100_2019_ND_CP::D1 |
| `unit_type` | string (55597) | 55597 | 0 | 0 | Dieu |

**`data/processed/meta/xrefs.jsonl` — 17,512 dòng; 13 trường.**

| Trường | Kiểu thực tế | Có mặt | Null | Rỗng | Giá trị mẫu |
|---|---|---:|---:|---:|---|
| `evidence` | string (17512) | 17512 | 0 | 0 | khoản 2 Điều 28 |
| `from_doc_id` | string (17512) | 17512 | 0 | 0 | 100_2019_ND_CP |
| `from_so_hieu` | string (17512) | 17512 | 0 | 0 | 100/2019/NĐ-CP |
| `from_unit_id` | string (17512) | 17512 | 0 | 0 | 100_2019_ND_CP::D4 |
| `in_corpus` | boolean (17512) | 17512 | 0 | 0 | true |
| `is_exclusion` | boolean (17512) | 17512 | 0 | 0 | false |
| `scope` | string (17512) | 17512 | 0 | 0 | internal |
| `to_diem` | string (17512) | 17512 | 0 | 13881 | b |
| `to_dieu` | string (17512) | 17512 | 0 | 0 | 28 |
| `to_doc_id` | string (17512) | 17512 | 0 | 0 | 100_2019_ND_CP |
| `to_khoan` | string (17512) | 17512 | 0 | 7156 | 2 |
| `to_so_hieu` | string (17512) | 17512 | 0 | 0 | 100/2019/NĐ-CP |
| `to_unit_id` | string (17508), null (4) | 17512 | 4 | 0 | 100_2019_ND_CP::D28::K2 |

**`data/processed/meta/relations.jsonl` — 821 dòng; 9 trường.**

| Trường | Kiểu thực tế | Có mặt | Null | Rỗng | Giá trị mẫu |
|---|---|---:|---:|---:|---|
| `evidence` | string (743) | 743 | 0 | 85 | Nghị định số 103/2008/NĐ-CP |
| `from_doc_id` | string (821) | 821 | 0 | 0 | 03_2021_ND_CP |
| `from_in_corpus` | boolean (821) | 821 | 0 | 0 | true |
| `from_so_hieu` | string (821) | 821 | 0 | 0 | 03/2021/NĐ-CP |
| `note` | string (821) | 821 | 0 | 0 | auto-detected |
| `rel_type` | string (821) | 821 | 0 | 0 | cites |
| `to_doc_id` | string (821) | 821 | 0 | 0 | 103_2008_ND_CP |
| `to_in_corpus` | boolean (821) | 821 | 0 | 0 | false |
| `to_so_hieu` | string (821) | 821 | 0 | 0 | 103/2008/NĐ-CP |

**`data/processed/penalties/penalties.jsonl` — 1,966 dòng; 16 trường.**

| Trường | Kiểu thực tế | Có mặt | Null | Rỗng | Giá trị mẫu |
|---|---|---:|---:|---:|---|
| `canh_cao` | boolean (1966) | 1966 | 0 | 0 | false |
| `diem` | string (1966) | 1966 | 0 | 183 | a |
| `dieu` | string (1966) | 1966 | 0 | 0 | 5 |
| `dieu_title` | string (1966) | 1966 | 0 | 0 | Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi |
| `doc_id` | string (1966) | 1966 | 0 | 0 | 100_2019_ND_CP |
| `doi_tuong` | string (1966) | 1966 | 0 | 419 | người điều khiển xe |
| `hanh_vi` | string (1966) | 1966 | 0 | 0 | Không chấp hành hiệu lệnh, chỉ dẫn của biển báo hiệu, vạch kẻ đường, trừ các hà… |
| `khoan` | string (1966) | 1966 | 0 | 0 | 1 |
| `penalty_id` | string (1966) | 1966 | 0 | 0 | 100_2019_ND_CP::D5::K1::Pa |
| `phat_tien_max` | integer (1966) | 1966 | 0 | 0 | 400000 |
| `phat_tien_min` | integer (1966) | 1966 | 0 | 0 | 200000 |
| `so_hieu` | string (1966) | 1966 | 0 | 0 | 100/2019/NĐ-CP |
| `tich_thu` | null (1807), string (159) | 1966 | 1807 | 0 | thiết bị phát tín hiệu ưu tiên lắp đặt sử dụng trái quy định |
| `tru_diem_gplx` | null (1791), integer (175) | 1966 | 1791 | 0 | 2 |
| `tuoc_gplx_thang` | null (1728), array (238) | 1966 | 1728 | 0 | [1,3] |
| `unit_id` | string (1966) | 1966 | 0 | 0 | 100_2019_ND_CP::D5::K1::Pa |

**`data/processed/signs/signs.jsonl` — 887 dòng; 12 trường.**

| Trường | Kiểu thực tế | Có mặt | Null | Rỗng | Giá trị mẫu |
|---|---|---:|---:|---:|---|
| `bien_phu_variant` | string (887) | 887 | 0 | 817 | (a,b,c) |
| `doc_id` | string (887) | 887 | 0 | 0 | 51_2024_TT_BGTVT |
| `ma_bien` | string (887) | 887 | 0 | 0 | DP.127 |
| `mo_ta` | string (887) | 887 | 0 | 0 | Hình B.27e - Biển số P.127c B.27d Biển số DP.127 "Biển hết tốc độ tối đa cho ph… |
| `ngay_het_hieu_luc` | null (446), string (441) | 887 | 446 | 0 | 2025-01-01 |
| `ngay_hieu_luc` | string (887) | 887 | 0 | 0 | 2025-01-01 |
| `nhom` | string (887) | 887 | 0 | 0 | Biển hết cấm |
| `qcvn` | string (887) | 887 | 0 | 0 | QCVN 41:2024/BGTVT |
| `sign_id` | string (887) | 887 | 0 | 0 | QCVN 41:2024/BGTVT::DP.127 |
| `so_hieu` | string (887) | 887 | 0 | 0 | 51/2024/TT-BGTVT |
| `ten` | string (887) | 887 | 0 | 156 | Biển hết tốc độ tối đa cho phép theo biển ghép |
| `unit_id` | string (887) | 887 | 0 | 0 | 51_2024_TT_BGTVT::QCVN41_2024_BGTVT::D84 |

**Kiểu lồng nhau, enum và khóa:**

- Documents: các array là `string[]`; `raw_file_sha256` là object đường dẫn→chuỗi SHA-256. `doc_id` duy nhất 92/92; `so_hieu` cũng duy nhất trong snapshot nhưng không chọn làm identity. `official_so_hieu` ghi nhận trường hợp cùng số ngắn 27/VBHN-BXD khác văn bản.
- `loai`: Nghị định 29, Thông tư 38, Luật 8, Văn bản hợp nhất 14, Bộ luật 2, Thông tư liên tịch 1. `scope`: road_core 55, road_related 15, consolidated 11, procedural 4, adjacent 4, out_of_scope 1, other_supporting 1, consolidated_historical 1.
- `tier`: Implementing 57, Superseded 13, Core 8, Foundational 5, Adjacent 5, Technical 2, OutOfScope 1, Supporting 1. `current_status`: ACTIVE 9, AMENDED 8, REPLACED 11, UNKNOWN 4; thiếu ở 60 dòng. `document_role`: ORIGINAL 3, AMENDMENT 6, CONSOLIDATED 1; thiếu ở 82 dòng. Không biến trường thiếu thành ACTIVE/ORIGINAL.
- Units: `unit_type` = Dieu 5.138, Khoan 23.315, Diem 22.960, QCVN 82, QCVN_Muc 4.102. `scope` không cùng nghĩa với documents.scope: TT hoặc nhãn QCVN, tổng 50 giá trị, thiếu 50.100 dòng. `qcvn_id` có 49 giá trị; không duy nhất. Nhãn số phải giữ string: có `dieu_number=11a`; occurrence giữ integer.
- Xrefs: `scope=internal` 14.576 / `external` 2.936; `in_corpus=true` 15.465 / false 2.047; `is_exclusion=true` 509 / false 17.003. Không có ID riêng, confidence, `downstream_use` hay classification khác.
- Relations: `rel_type` chỉ có cites 690, amends 44, repeals 37, implements 32, consolidates 18. Không có relation ID. Hai cờ corpus là boolean, không phải trạng thái hiệu lực.
- Penalties: `penalty_id` và `unit_id` đều duy nhất 1.966/1.966 và bằng nhau ở mọi dòng. `tuoc_gplx_thang` nếu có là array đúng 2 integer, ví dụ [1,3]; `tru_diem_gplx` quan sát 2,3,4,6,8,10 hoặc null. Không có currency field riêng. `doi_tuong`, `hanh_vi` là text, không phải enum đã chuẩn hóa.
- Signs: `sign_id` duy nhất 887/887; `ma_bien` chỉ có 451 giá trị. `qcvn` có 2 phiên bản 41:2024/BGTVT (446) và 41:2019/BGTVT (441). `nhom` gồm Biển hết cấm 16, Biển chỉ dẫn 217, Biển chỉ dẫn trên đường cao tốc 116, Biển báo cấm 136, Biển hiệu lệnh 152, Biển phụ 51, Biển báo nguy hiểm và cảnh báo 199. `bien_phu_variant` là chuỗi nhóm biến thể, không tách tự động thành biển mới.
- Foreign keys: units.doc_id→documents.doc_id; units.parent_id→units.unit_id; xrefs.from/to_unit_id→units.unit_id và from/to_doc_id→documents.doc_id; relations.from/to_doc_id→documents.doc_id; penalties/signs.unit_id→units.unit_id và doc_id→documents.doc_id. Số hiệu chỉ dùng hiển thị/đối chiếu; endpoint ngoài corpus có thể không resolve.
- Trường kỹ thuật như counters, parse_version, reason, raw_files, hash và scrape_status là metadata audit. Không tạo node cho chúng. Phân loại đầy đủ việc giữ thuộc tính hoặc loại khỏi graph ở mục 11–13.

## 3. Proposed node types

| Candidate | Quyết định | Căn cứ |
|---|---|---|
| LegalDocument | KEEP_AS_NODE | Identity doc_id; nguồn của cây units, hiệu lực và 5 loại quan hệ văn bản |
| LegalUnit | KEEP_AS_NODE | Identity unit_id; text, parent và endpoint citation dùng chung |
| Penalty | MERGE vào LegalUnit | 1.966 record tương ứng đúng 1.966 unit; penalty_id bằng unit_id; không có identity/vòng đời độc lập trong R2 |
| TrafficSign | KEEP_AS_NODE | 887 identity riêng theo phiên bản; nhiều biển cùng một unit; thuộc tính mã/tên/mô tả truy xuất độc lập |
| Dieu, Khoan, Diem, QCVN, QCVN_Muc | PROPERTY_ONLY cho phân loại; record vẫn là LegalUnit | Không tạo thêm 5 loại node; giữ unit_type và identity nguồn |
| Cơ quan, nhóm biển, đối tượng xử phạt, legal domain | PROPERTY_ONLY | Hiện là chuỗi/list, chưa có entity ID hoặc quan hệ chuẩn hóa |
| Xref/DocumentRelation như node trung gian | DO_NOT_MODEL | Cạnh có thuộc tính đủ giữ polarity và provenance; chưa cần node sự kiện |
| Văn bản ngoài corpus, câu hỏi eval, file raw | DO_NOT_MODEL trong production v0.1 | Không có full record production hoặc không phải nguồn tri thức pháp lý |

Không bổ sung entity khác. `TrafficSign` biểu diễn bản ghi biển trong một phiên bản QCVN, không phải khái niệm biển bất biến qua mọi thời kỳ.

## 4. Proposed edge types

| Edge | Hướng | Cardinality | Quan sát R2 / điều kiện |
|---|---|---|---|
| HAS_UNIT | LegalDocument→LegalUnit gốc | 1:N; mỗi root có 1 document | 5.046 root |
| HAS_CHILD | LegalUnit cha→LegalUnit con | 1:N; mỗi non-root có 1 cha | 50.551; không orphan/cycle/cross-document |
| HAS_SIGN | LegalUnit→TrafficSign | 1:N; mỗi sign có 1 unit nguồn | 887 cạnh, 7 source units |
| CITES_UNIT | LegalUnit→LegalUnit | N:N theo thiết kế | SAFE_EDGE và is_exclusion=false; chưa xác định số đủ điều kiện |
| EXCLUDES_UNIT | LegalUnit→LegalUnit | N:N theo thiết kế | SAFE_EDGE và is_exclusion=true; không suy ra phủ định tuyệt đối |
| CITES | LegalDocument→LegalDocument | N:N | 172 cặp nội bộ |
| AMENDS | LegalDocument→LegalDocument | N:N cho phép | 16 cặp nội bộ |
| REPEALS | LegalDocument→LegalDocument | N:N cho phép | 6 cặp nội bộ |
| IMPLEMENTS | LegalDocument→LegalDocument | N:N cho phép | 32 cặp nội bộ |
| CONSOLIDATES | LegalDocument→LegalDocument | N:N cho phép | 12 cặp nội bộ |

Cardinality N:N của quan hệ pháp lý là khả năng mô hình cho phép, không khẳng định mọi nguồn/đích trong R2 đều có nhiều cạnh. Không lưu cạnh inverse dư thừa. Không đề xuất HAS_PENALTY trong v0.1 vì không có node Penalty.

## 5. Legal hierarchy model

**Chọn B: một LegalUnit với unit_type.**

| Tiêu chí | A — 5 loại node riêng | B — một LegalUnit |
|---|---|---|
| Retrieval | Truy vấn hợp nhất nhiều type; xrefs cần chọn type đích | Truy vấn text/ID chung; lọc unit_type khi cần |
| Traversal | Nhiều cặp type/relation cho các cây khác nhau | HAS_CHILD tự liên kết; traversal dùng cùng một loại |
| Hierarchy | Ràng buộc theo type rõ hơn nhưng cần cả QCVN→Dieu | Kiểm tra parent/type ở adapter; giữ đúng cây nguồn |
| Độ phức tạp | Lặp thuộc tính và mapping | 1 mapping dùng 5 enum |
| Phù hợp units.jsonl | Phải chia file logic theo type | Trực tiếp 1 dòng→1 node |
| Suy luận về sau | Type chuyên biệt tiện ràng buộc nhưng không tự cung cấp ngữ nghĩa pháp lý | unit_type + cạnh + text đủ phân biệt; thêm rule khi có dữ liệu thực |

Định nghĩa rõ: `HAS_UNIT` chỉ nối **root có parent_id=null**; quyền sở hữu tất cả unit vẫn truy vấn được bằng `LegalUnit.doc_id` hoặc đường đi HAS_UNIT/HAS_CHILD. Không đồng thời tạo HAS_UNIT cho mọi hậu duệ.

Cây thực, số cạnh:

- Document→Dieu: 4.964; Document→QCVN: 82.
- Dieu→Khoan: 23.315; Khoan→Diem: 22.960.
- QCVN→QCVN_Muc: 4.102; QCVN→Dieu: 174.
- Không có QCVN_Muc→QCVN_Muc trong parent_id hiện tại. Số mục 1.1/1.1.1 không cho phép tự tạo phân cấp mới.
- Tất cả 55.597 unit thuộc 91 document production; parent tồn tại, cùng doc; không chu trình.

Ví dụ đúng nguồn:

```text
100_2019_ND_CP
  HAS_UNIT → 100_2019_ND_CP::D2
    HAS_CHILD → 100_2019_ND_CP::D2::K2
      HAS_CHILD → 100_2019_ND_CP::D2::K2::Pa

48_2024_TT_BGTVT
  HAS_UNIT → 48_2024_TT_BGTVT::QCVN04_2024_BGTVT
    HAS_CHILD → 48_2024_TT_BGTVT::QCVN04_2024_BGTVT::S1_1

51_2024_TT_BGTVT
  HAS_UNIT → 51_2024_TT_BGTVT::QCVN41_2024_BGTVT
    HAS_CHILD → 51_2024_TT_BGTVT::QCVN41_2024_BGTVT::D84
```

QCVN là occurrence trong văn bản nguồn, không thêm LegalDocument QCVN giả. Có 82 unit QCVN nhưng chỉ 49 qcvn_id; ví dụ `56_2024_TT_BGTVT::QCVN26_2010_BTNMT` và hậu tố `~2` đều là đoạn dẫn quy chuẩn tiếng ồn. Không coi mọi node QCVN là toàn văn một quy chuẩn độc lập; không hợp nhất theo qcvn_id.

`order` không phải khóa: có 366 record dư khi nhóm (doc_id,order), 194 khi nhóm (doc_id,parent_id,order). Dùng order để sắp xếp, unit_id làm tie-break xác định; không diễn giải tie-break thành thứ tự pháp lý đã phục dựng. Không cắt hậu tố occurrence như `~2`.

Text ở cha có thể lặp nội dung con; không xem nhiều tầng là nhiều chứng cứ độc lập. Độ dài text quan sát 4–757.423 ký tự: truy xuất/chunking về sau phải giữ lại unit_id gốc.

## 6. Xref policy

Trường đúng nguồn: `from_unit_id`, `to_unit_id`, `from_doc_id`, `to_doc_id`, `from_so_hieu`, `to_so_hieu`, `to_dieu`, `to_khoan`, `to_diem`, `scope`, `in_corpus`, `is_exclusion`, `evidence`.

**Không có downstream_use trong cả 17.512 dòng.** Vị trí phân loại duy nhất được mô tả là “bảng phân loại được giữ ngoài repo” tại `data/README.md:95`; không có đường dẫn, định danh bảng, khóa join hay checksum của bảng trong artifact được phép kiểm tra. Không thể chỉ ra file vật lý hoặc phục dựng các nhãn đã duyệt. Không tra dự án cũ để thay thế bảng này.

Kiểm tra endpoint thực:

| Nhóm | Số dòng |
|---|---:|
| Source unit tồn tại | 17,512 |
| Target unit tồn tại | 9,856 |
| Target tồn tại, không exclusion | 9,410 |
| Target tồn tại, exclusion | 446 |
| in_corpus=true nhưng target unit không tồn tại | 5,609 |
| in_corpus=false; target không tồn tại | 2,047 |
| to_unit_id=null (nằm trong nhóm false) | 4 |

`scope=external` là tham chiếu sang văn bản khác, không đồng nghĩa ngoài corpus. `in_corpus=true` là thông tin văn bản đích, không chứng nhận unit đích hoặc tính đúng của dẫn chiếu. 9.856 endpoint tồn tại **không tương đương** 8.144 SAFE_EDGE được README nêu.

Chính sách tạo cạnh sau này, theo thứ tự:

1. Nhận bảng phân loại đã duyệt gắn với đúng checksum xrefs LOCKED R2. Join từng record không mơ hồ; thiếu/conflict/khác snapshot → không tạo cạnh.
2. Chỉ record có nhãn **downstream_use == "SAFE_EDGE"** mới đi tiếp. Đây là trường của classification bổ sung; không giả vờ nó đã có trong JSONL.
3. Kiểm tra source và target đều là unit production, doc_id của hai endpoint khớp record, in_corpus=true, evidence không rỗng; không tạo placeholder cho target thiếu.
4. is_exclusion=false → CITES_UNIT. is_exclusion=true → EXCLUDES_UNIT, vẫn giữ cờ và evidence.
5. Lưu scope, evidence, classification và định danh nguồn phân loại làm provenance cạnh. Không biến exclusion thành citation khẳng định; không suy ra nguồn “bãi bỏ” đích. Predicate chỉ ghi nhận ngữ cảnh ngoại lệ trong nguồn.
6. Khi chưa có bảng phân loại: **0 cạnh xref được phép nạp**. B1 vẫn hoàn thành đề xuất; phần xref của ingestion sau này bị chặn.

Có 337 dòng dư nếu chỉ nhóm (from_unit_id,to_unit_id,is_exclusion), nhưng không có record trùng toàn bộ 13 trường; có 181 self-reference. Không gộp mất evidence, không tự đổi self-reference thành tham chiếu khác. Thiết kế một cạnh cho mỗi (type nguồn, ID nguồn, predicate, type đích, ID đích), kèm tập evidence/provenance của các record đã duyệt. Nếu cùng cặp vừa citation vừa exclusion thì giữ hai predicate tách biệt. Khóa join classification nên là SHA-256 canonical JSON của **đủ 13 trường nguồn**, xác nhận với bảng thật ở B2; không dùng số dòng đơn lẻ.

## 7. Document relation model

Giữ nguyên hướng from_doc_id→to_doc_id và map rel_type tương ứng CITES, AMENDS, REPEALS, IMPLEMENTS, CONSOLIDATES.

| rel_type | Toàn bộ | Hai đầu production | Có ít nhất một đầu ngoài |
|---|---:|---:|---:|
| cites | 690 | 172 | 518 |
| amends | 44 | 16 | 28 |
| repeals | 37 | 6 | 31 |
| implements | 32 | 32 | 0 |
| consolidates | 18 | 12 | 6 |
| Tổng | 821 | 238 | 583 |

820 source có from_in_corpus=true; 1 false. Target có to_in_corpus=true ở 239 dòng, false ở 582 dòng. Có 238 cặp true/true, 582 true/false, 1 false/true. Cờ khớp tập production thực; không có cặp trùng (from,rel_type,to) trong 238 dòng nội bộ.

**Điều kiện v0.1:** cả hai cờ true **và** cả hai ID thuộc whitelist production. 583 dòng còn lại là EXTERNAL_REFERENCE_ONLY; giữ trong dataset/provenance ngoài graph, không thêm node rỗng. Nguồn ngoài có thật: `14_2025_TT_BXD -repeals→ 35_2024_TT_BGTVT`, from_in_corpus=false. Không được bỏ qua kiểm tra đầu nguồn.

`evidence` optional: toàn bộ có 78 dòng thiếu, 85 chuỗi rỗng. Trong 238 nội bộ: 80 evidence không rỗng, 85 rỗng, 73 thiếu. Vẫn giữ quan hệ nguồn với `note` và source-record provenance; thiếu trích đoạn không được biến thành trích dẫn luật đã kiểm chứng. Không yêu cầu SAFE_EDGE của xrefs cho relations vì đây là file/chính sách khác.

AMENDS/REPEALS không mang unit phạm vi, ngày hiệu lực hoặc điều kiện chuyển tiếp có cấu trúc. Vì vậy chỉ thể hiện quan hệ được dataset ghi nhận; không suy ra mọi unit của văn bản đích đều sửa đổi/bãi bỏ. CONSOLIDATES không đồng nhất identity văn bản hợp nhất với bản gốc. Không sinh cạnh thứ hai từ các danh sách amends/repeals trong documents metadata.

## 8. Penalty model

1.966 record đến từ `100_2019_ND_CP` (1.060), `168_2024_ND_CP` (691), `336_2025_ND_CP` (215). Tất cả unit_id resolve đúng doc_id: 1.783 Diem, 183 Khoan.

- **Quan sát:** một unit có tối đa 1 record penalty; một record chỉ có 1 unit_id scalar. Không có bằng chứng về penalty nhiều unit hoặc nhiều record trên cùng unit.
- **Phương án node + HAS_PENALTY:** hỗ trợ identity và vòng đời riêng, nhiều sanctions về sau; hiện tạo thêm 1.966 node/cạnh 1:1 mà ID lại bằng unit_id.
- **Phương án chọn:** MERGE các trường penalty vào LegalUnit theo unit_id; giữ penalty_id nguồn và prefix `penalty_`. Unit không có record giữ thuộc tính penalty vắng mặt, không điền mức phạt 0.
- Đây là cardinality `LegalUnit 1 : 0..1 PenaltyRecord` ở lớp nguồn, không phải relation graph. Nếu dataset tương lai phá vỡ 1:1, adapter phải báo lỗi/đưa record chờ review, không ghi đè; lúc đó mới cân nhắc node riêng.
- Giữ nguyên min/max integer; hiện không có min>max. 166 record min=0 là dữ liệu cảnh cáo; null trừ điểm/tước GPLX/tịch thu nghĩa “không có giá trị trích xuất”, không đủ kết luận biện pháp không áp dụng.
- Tước GPLX [min,max] chuyển thành hai thuộc tính tháng để truy vấn số; không tính trung bình hoặc cộng cùng hình phạt khác. Một record gom trường xử phạt không chứng minh mọi trường luôn áp dụng đồng thời.
- Không tạo entity riêng cho đối tượng/hành vi, không tự chuẩn hóa 419 doi_tuong rỗng, không suy diễn currency field mới từ schema. Nhãn hiển thị đơn vị tiền cần đối chiếu nội dung nguồn khi xây ứng dụng.

## 9. Traffic sign model

Chọn node TrafficSign vì 887 record có identity riêng, chỉ nối về 7 unit. HAS_SIGN đi LegalUnit→TrafficSign để từ điều nguồn duyệt ra các biển. Mỗi sign có đúng 1 nguồn; chưa có source array cho phép N:N.

Identity `sign_id` đã chứa phiên bản, ví dụ `QCVN 41:2024/BGTVT::DP.127`. Không dùng ma_bien đơn độc; không gộp biển 2019 với 2024.

Giữ nguyên `ma_bien`, `nhom`, `ten`, `bien_phu_variant`, `mo_ta`, `qcvn`, `doc_id`, `unit_id`, `so_hieu` và các ngày. Có **156 ten rỗng**; không sáng tác tên từ mo_ta. Nhãn kỹ thuật name dùng sign_id, khác với tên pháp lý ten. Không có trường ảnh trong nguồn.

887 endpoint đều tồn tại và là **Dieu dưới QCVN**, không phải QCVN_Muc. Hai Điều `...::D84` (2024) và `...::D90` (2019), cùng title “Tổ chức thực hiện”, chứa lần lượt 385 và 381 biển. Đây là neo trích xuất rộng; HAS_SIGN ghi nhận nguồn record, không khẳng định đó là điều định nghĩa độc quyền từng biển. Không tự tìm/reparent theo mô tả. B2 cần giữ cảnh báo provenance này trong hợp đồng truy xuất.

## 10. ID strategy

| Đối tượng | Quy tắc identity |
|---|---|
| LegalDocument | id = doc_id nguyên trạng |
| LegalUnit | id = unit_id nguyên trạng, kể cả ký tự Việt, dấu phân cách, hậu tố occurrence |
| TrafficSign | id = sign_id nguyên trạng, gồm phiên bản QCVN |
| Penalty được merge | Không có node ID mới; giữ penalty_id dưới penalty_id property của unit tương ứng |
| Edge | Khóa logic = canonical JSON array [from_type,from_id,predicate,to_type,to_id]; nếu API cần scalar ID thì dùng SHA-256 UTF-8 của array này |
| Bản ghi provenance | Đường dẫn tương đối + SHA-256 file + số dòng; xref classification join thêm fingerprint canonical JSON toàn record |

Canonical JSON dùng khóa sort cho object, separators không khoảng trắng, UTF-8, không normalize nội dung hay đổi missing thành null. Tên type/namespace là một phần identity kỹ thuật; không trộn ID khác type. Không hash text để thay unit_id, không tạo UUID, không dùng order/title/số hiệu/ngày làm khóa.

Các quy tắc chỉ được thiết kế; B1 không sinh ID hoặc artifact graph. name kỹ thuật của cả ba node mặc định bằng id để tránh gộp các title lặp; UI sử dụng title/ten/ma_bien thật.

## 11. Node property mapping

Viết tắt file (mọi đường dẫn bắt đầu `data/`): **D**=`processed/meta/documents.jsonl`; **U**=`processed/units/units.jsonl`; **P**=`processed/penalties/penalties.jsonl`; **S**=`processed/signs/signs.jsonl`. Các nhóm tên trong một ô map 1:1 theo cùng thứ tự, không đổi tên ngầm.

| Graph type | Graph property | Source file | Source field | Required? | Notes |
|---|---|---|---|---|---|
| LegalDocument | id, name | D | doc_id, doc_id | Có | name là nhãn kỹ thuật |
| LegalDocument | so_hieu, title, loai, co_quan | D | Cùng tên | Có | Giữ giá trị nguồn, không canonicalize cơ quan |
| LegalDocument | official_so_hieu, identity_note | D | Cùng tên | Không | Phân biệt số ngắn trùng |
| LegalDocument | scope, tier | D | Cùng tên | Có | Phạm vi corpus và nhóm nguồn |
| LegalDocument | document_role, legal_domains | D | Cùng tên | Không | string, string[] |
| LegalDocument | current_status, status_hint, phan_lien_quan | D | Cùng tên | Không | Snapshot/ghi chú, không rule thời gian |
| LegalDocument | ngay_ban_hanh | D | ngay_ban_hanh | Có | Chuỗi ngày ISO nguồn |
| LegalDocument | effective_from | D | effective_from nếu có, nếu không ngay_hieu_luc | Không; cho null | Hai trường khớp khi cùng có; không dùng ngày ký làm fallback |
| LegalDocument | effective_to | D | effective_to nếu có, nếu không ngay_het_hieu_luc | Không | Giữ hết hiệu lực bộ phận trong note; không xóa units |
| LegalDocument | hieu_luc_note, het_hieu_luc_note | D | Cùng tên | Không | Bảo toàn điều kiện/ngoại lệ |
| LegalDocument | ngay_hieu_luc_bo_phan | D | ngay_hieu_luc_bo_phan | Không | string[]; chưa gắn được từng ngày với unit |
| LegalDocument | consolidation_as_of, underlying_effective_from | D | Cùng tên | Không | Không thay effective_from của VBHN |
| LegalDocument | source_url, source_kind | D | Cùng tên | Có | Provenance; URL không tạo entity |
| LegalDocument | source_quality, source_note | D | Cùng tên | Không | Không tự nâng record thiếu thành OFFICIAL |
| LegalDocument | markdown_path | D + processed/documents/ | doc_id + file hiện hữu | Có | data/processed/documents/{doc_id}.md |
| LegalUnit | id, name | U | unit_id, unit_id | Có | Identity exact |
| LegalUnit | doc_id, so_hieu, unit_type, text, order | U | Cùng tên | Có | String, string, enum-string, string, integer |
| LegalUnit | parent_id | U | parent_id | Có key; null ở root | Thuộc tính kiểm chứng cây; không tạo node null |
| LegalUnit | title | U | title | Không; null | Không thay bằng text suy đoán |
| LegalUnit | dieu_number, khoan_number, diem_letter | U | Cùng tên | Không | String; giữ chữ/số nguồn |
| LegalUnit | dieu_occurrence, khoan_occurrence, diem_occurrence | U | Cùng tên | Không | Integer; giữ khi tồn tại, không tự điền 1 |
| LegalUnit | qcvn_id, scope, section_number, section_occurrence | U | Cùng tên | Không | 3 string + integer; qcvn_id không là FK toàn cục |
| LegalUnit | penalty_id | P | penalty_id, join unit_id | Có khi có P | Marker record xử phạt; không node mới |
| LegalUnit | penalty_dieu_title | P | dieu_title | Có khi có P | Title trích xuất, không ghi đè unit.title |
| LegalUnit | penalty_doi_tuong, penalty_hanh_vi | P | doi_tuong, hanh_vi | Có khi có P | doi_tuong được phép rỗng |
| LegalUnit | penalty_phat_tien_min, penalty_phat_tien_max | P | phat_tien_min, phat_tien_max | Có khi có P | Integer; bảo toàn 0 |
| LegalUnit | penalty_canh_cao | P | canh_cao | Có khi có P | Boolean; bảo toàn false |
| LegalUnit | penalty_tru_diem_gplx | P | tru_diem_gplx | Không; nullable | Integer nếu có; null không phải 0 |
| LegalUnit | penalty_tuoc_gplx_thang_min, penalty_tuoc_gplx_thang_max | P | tuoc_gplx_thang[0], [1] | Không; nullable | Cặp đủ 2 integer mới map; null giữ thiếu cả cặp |
| LegalUnit | penalty_tich_thu | P | tich_thu | Không; nullable | Text nguyên nguồn |
| LegalUnit | penalty_source_record | P | Vị trí record + checksum file | Có khi có P | Provenance riêng cho thuộc tính merge |
| TrafficSign | id, name | S | sign_id, sign_id | Có | name không phải ten được suy diễn |
| TrafficSign | doc_id, unit_id, so_hieu | S | Cùng tên | Có | Kiểm tra FK và doc ownership |
| TrafficSign | ma_bien, nhom, qcvn | S | Cùng tên | Có | Giữ phiên bản QCVN |
| TrafficSign | ten, bien_phu_variant | S | Cùng tên | Có key; cho rỗng | Không sinh tên/biển biến thể |
| TrafficSign | mo_ta | S | mo_ta | Có | Nội dung trích xuất, không thay unit.text |
| TrafficSign | ngay_hieu_luc | S | ngay_hieu_luc | Có | Ngày nguồn |
| TrafficSign | ngay_het_hieu_luc | S | ngay_het_hieu_luc | Không; nullable | 441 ngày, 446 null |
| Cả ba node | source_record | D/U/S tương ứng | Path + checksum file + số dòng | Có, derived | Truy vết nguồn; không phải identity |
| Cả ba node | dataset_version | README/corpus snapshot | LOCKED R2 | Có, hằng manifest | Không giả vờ là trường JSONL |

**Không map thành thuộc tính tri thức:** documents.`n_units,n_dieu,n_parts,n_qcvn,n_qcvn_muc,text_chars,parse_version,reason,scrape_status,status,source_mark,sha256,raw_files,raw_file_sha256`; giữ ở nguồn audit. Các hint `amended_by,amends,repealed_by,repeals,replaced_by,replaces,consolidates` không tạo cạnh bổ sung; relations.jsonl là nguồn cạnh chuẩn v0.1. `ngay_hieu_luc,ngay_het_hieu_luc` trong D đã map vào hai effective_* theo quy tắc trên.

P.`unit_id,doc_id,so_hieu` dùng join/kiểm tra; `dieu,khoan,diem` là locator đối chiếu, giữ ở nguồn nhưng không tái tạo cây hoặc ghi đè locator của U. Mọi trường khác của P đã map phía trên.

Kiểu logic được nêu ở đây; cú pháp Text/Integer/boolean/date/multivalue và encoding null thực tế của OpenSPG là TO_CONFIRM_IN_B2.

## 12. Edge mapping

Viết tắt bổ sung: **X**=`data/processed/meta/xrefs.jsonl`; **R**=`data/processed/meta/relations.jsonl`. “production” nghĩa thuộc tập hợp nêu mục 13.

| Edge | From | To | Source file | Condition | Evidence |
|---|---|---|---|---|---|
| HAS_UNIT | LegalDocument.id = U.doc_id | LegalUnit.id = U.unit_id | U | parent_id=null; doc production | U.doc_id, unit_id, parent_id; source_record |
| HAS_CHILD | LegalUnit.id = U.parent_id | LegalUnit.id = U.unit_id | U | parent_id khác null; hai unit tồn tại cùng doc production | U.parent_id, unit_id; source_record |
| HAS_SIGN | LegalUnit.id = S.unit_id | TrafficSign.id = S.sign_id | S | Unit tồn tại, cùng S.doc_id production | S.unit_id, sign_id, qcvn; source_record; mo_ta nằm ở node |
| CITES_UNIT | LegalUnit.id = X.from_unit_id | LegalUnit.id = X.to_unit_id | X + bảng classification ngoài repo | SAFE_EDGE; hai endpoint/doc hợp lệ; in_corpus=true; is_exclusion=false | X.evidence, scope, is_exclusion, in_corpus + provenance classification |
| EXCLUDES_UNIT | LegalUnit.id = X.from_unit_id | LegalUnit.id = X.to_unit_id | X + bảng classification ngoài repo | Như trên; is_exclusion=true | Như trên; giữ nghĩa ngoại lệ |
| CITES | LegalDocument.id = R.from_doc_id | LegalDocument.id = R.to_doc_id | R | rel_type=cites; cả hai flags true và ID production | R.evidence nếu có, R.note; source_record |
| AMENDS | LegalDocument.id = R.from_doc_id | LegalDocument.id = R.to_doc_id | R | rel_type=amends; cùng gate corpus | R.evidence nếu có, R.note; source_record |
| REPEALS | LegalDocument.id = R.from_doc_id | LegalDocument.id = R.to_doc_id | R | rel_type=repeals; cùng gate corpus | R.evidence nếu có, R.note; source_record |
| IMPLEMENTS | LegalDocument.id = R.from_doc_id | LegalDocument.id = R.to_doc_id | R | rel_type=implements; cùng gate corpus | R.evidence nếu có, R.note; source_record |
| CONSOLIDATES | LegalDocument.id = R.from_doc_id | LegalDocument.id = R.to_doc_id | R | rel_type=consolidates; cùng gate corpus | R.evidence nếu có, R.note; source_record |

Thuộc tính cạnh cấu trúc: source_record, dataset_version. Cạnh văn bản thêm rel_type, note, evidence (phân biệt thiếu/rỗng), from_in_corpus, to_in_corpus. Cạnh xref giữ các record provenance đã duyệt gồm evidence/scope/polarity/locator nguồn và đích, downstream_use và fingerprint/classification source; nhiều evidence cùng cạnh không ghi đè nhau. Mã hóa collection provenance thành scalar JSON hay multivalue chờ B2, không thêm entity Evidence chỉ để né quyết định storage.

## 13. Production graph inclusion/exclusion

Whitelist document = doc_id có record D, scope khác `out_of_scope`, và có Markdown tương ứng dưới `processed/documents/`. R2 cho đúng 91 ID; `22_VBHN_BXD` chỉ nằm metadata và ngoài phạm vi. Tất cả U thuộc whitelist. Không loại văn bản lịch sử/Superseded theo mặc định: graph giữ lịch sử, truy vấn thời gian phải tách riêng.

| Phân loại | Đầu vào | Cách dùng |
|---|---|---|
| PRODUCTION_GRAPH | processed/meta/documents.jsonl | 91 LegalDocument; loại 22_VBHN_BXD |
| PRODUCTION_GRAPH | processed/units/units.jsonl | 55.597 LegalUnit; HAS_UNIT/HAS_CHILD |
| PRODUCTION_GRAPH | processed/penalties/penalties.jsonl | Merge thuộc tính vào 1.966 LegalUnit; không node/cạnh riêng |
| PRODUCTION_GRAPH | processed/signs/signs.jsonl | 887 TrafficSign và HAS_SIGN |
| PRODUCTION_GRAPH có gate | processed/meta/relations.jsonl | Chỉ 238 quan hệ hai đầu production |
| PRODUCTION_GRAPH có gate đang đóng | processed/meta/xrefs.jsonl | Chỉ SAFE_EDGE đã chứng minh; hiện không nạp xref nào |
| PRODUCTION_GRAPH — nguồn văn bản hỗ trợ | processed/documents/*.md | Nguồn full text/citation, markdown_path; không tạo node thứ hai hoặc extract lại hierarchy đã có |
| OUT_OF_SCOPE | processed/out_of_scope/** | Không nạp Markdown, units, xrefs, relations của 22_VBHN_BXD |
| OUT_OF_SCOPE | processed/penalties/excluded_out_of_scope.jsonl | Không merge các penalty bị loại |
| EVAL | processed/eval/** | Không node, cạnh, retrieval corpus hoặc nguồn sinh tri thức |
| RAW | raw/** | Chỉ đối chiếu; không ingestion cùng bản processed gây lặp |
| METADATA_ONLY | metadata/corpus.json, document_inventory.csv, sources.csv, checksums.json; README/DATASHEET | Manifest, audit, provenance; không tự tạo entities/cạnh từ hints |
| EXTERNAL_REFERENCE_ONLY | 583 R có ít nhất một đầu ngoài; X có in_corpus=false | Giữ để audit ngoài graph; không tạo external placeholder |
| METADATA_ONLY — chờ phân loại | Các X còn lại chưa có SAFE_EDGE/không resolve | Không tạo citation dù target document tồn tại |

Nếu future adapter gặp ID trùng, join nhiều penalty/thiếu endpoint, mismatch doc hoặc parent cycle: báo lỗi/chờ review; không “sửa” bằng suy luận văn bản, không sửa baseline R2. Production corpus là phạm vi nguồn, không chứng nhận mọi câu đều là quy phạm còn hiệu lực hoặc chỉ nói về đường bộ.

## 14. OpenSPG/KAG compatibility notes

Pinned upstream HEAD quan sát: **fdab15b3929d2ee40dfcdd388f90233096a6afc9**. Kiểm tra nguồn local, không nhập module hay gọi server.

Các file đọc toàn bộ hoặc đoạn liên quan trong `vendor/KAG/`:

1. `kag/examples/riskmining/schema/RiskMining.schema`
2. `kag/examples/supplychain/schema/SupplyChain.schema` (đoạn khai báo properties)
3. `knext/schema/model/base.py` (đoạn sub_properties/type)
4. `knext/schema/model/schema_helper.py`
5. `kag/builder/component/reader/dict_reader.py`
6. `kag/builder/component/mapping/spg_type_mapping.py`
7. `kag/builder/component/mapping/relation_mapping.py`
8. `kag/builder/component/writer/kg_writer.py`
9. `kag/builder/model/sub_graph.py`
10. `kag/interface/common/model/sub_graph.py`

Kết luận: **mô hình tương thích về cấu trúc biểu diễn**, chưa xác nhận schema chạy được.

- Schema ví dụ có namespace, EntityType, properties Text/Integer, relations tới entity khác, cạnh tự liên kết và properties trên relation. Không cần ConceptType cho enum unit_type.
- SPGTypeMapping nhận dictionary và property_mapping, hỗ trợ id/name. RelationMapping nhận dictionary, src_id_field/dst_id_field và thuộc tính cạnh. JSONL cần được đọc thành record; không giả định builder tự hiểu toàn bộ dataset.
- Luồng đề xuất về sau: đọc record → gate corpus/classification → join P vào U → mapping node/edge → SubGraph → writer. Dùng mapping xác định cho ID/cạnh có sẵn; không dùng LLM trích lại các trường đã khóa.
- DictReader tạo Chunk và pop các trường ID/name/content khỏi dictionary. Đây là nhánh xử lý text, không chứng minh relations/metadata được tự nạp. Nếu dùng sau này cần bản sao record.
- SubGraph giữ node id/name/label/properties, edge from/to/type/label/properties; hỗ trợ mô hình này. `add_edge` hiện cấp ID bằng `id(self)` khi thiếu ID, nên không dựa vào đó để bảo đảm idempotency.
- RelationMapping kiểm tra predicate bằng `key.split("_")[0]` ở relation keys. Các nhãn logic có underscore như HAS_CHILD/CITES_UNIT cần kiểm tra hoặc ánh xạ sang tên schema camelCase ở B2. Tên trong B1 là tên miền logic, chưa là cú pháp .schema đã thử.
- KGWriter chuyển property không phải string thành JSON string. Cần kiểm chứng round-trip integer, boolean, 0, false, null, list, và các ngày với kiểu server; không tuyên bố raw JSONL types được bảo toàn tự động.
- Không cần sửa upstream hoặc sao chép implementation. Không đọc dự án cũ vì upstream đã đủ giải thích điểm tích hợp. Nếu tham khảo tổ chức file cũ sau này, chỉ được gắn nhãn STRUCTURAL_REFERENCE_ONLY.

## 15. Open questions for B2

**OPEN_QUESTIONS = 7.** Các mục dưới không ngăn B1 hoàn thành; mục 1 chặn cạnh xref, các mục kỹ thuật chặn việc tuyên bố ingestion production sẵn sàng.

1. **TO_CONFIRM_IN_B2 — Bảng SAFE_EDGE:** file/bên quản lý nào giữ classification; checksum/version và khóa join thực là gì; 8.144 có đúng snapshot hiện tại không? Chỉ mở gate khi đối soát từng record, không lấy endpoint tồn tại làm thay thế.
2. **TO_CONFIRM_IN_B2 — Cú pháp schema/predicate:** namespace, tên property/relation hợp lệ, cách map nhãn logic underscore, enum và cardinality. Kiểm tra với pinned parser/server; không sửa vendor.
3. **TO_CONFIRM_IN_B2 — Codec property:** schema types cho integer/boolean/date/list, omission/null/rỗng và tuple tháng; bảo toàn 0/false; chốt encoding source_record và collection evidence.
4. **TO_CONFIRM_IN_B2 — Idempotency cạnh:** API có tôn trọng ID xác định/khóa tuple không; upsert nhiều provenance cùng cạnh ra sao; tránh ID runtime của SubGraph và ghi đè evidence.
5. **TO_CONFIRM_IN_B2 — Text/index:** giới hạn text/index và chiến lược chunk cho unit dài tới 757.423 ký tự; vẫn truy vết unit_id, không double-count text cha/con. Chunk là chi tiết retrieval sau này, chưa thêm domain entity.
6. **TO_CONFIRM_IN_B2 — Hiệu lực/phạm vi:** cách query xử lý ngày bộ phận, ghi chú ngoại lệ, status thiếu và quan hệ amendment/repeal cấp document. Chưa có dữ liệu đủ để áp temporal rules tới từng unit; mặc định chỉ trả provenance.
7. **TO_CONFIRM_IN_B2 — Neo QCVN/biển:** cách hiển thị bản ghi QCVN chỉ là đoạn dẫn và 766 biển neo vào Điều “Tổ chức thực hiện”; tránh mô tả chúng như toàn văn quy chuẩn hoặc điều định nghĩa chính xác. Không reparent hay sửa R2 trong B2.

## 16. Recommended schema v0.1

**Chọn duy nhất mô hình sau:**

- **Nodes (3):** LegalDocument (91), LegalUnit (55.597; unit_type ∈ Dieu/Khoan/Diem/QCVN/QCVN_Muc), TrafficSign (887). Tổng dự kiến 56.575 node.
- **Penalty:** MERGE vào 1.966 LegalUnit qua unit_id; giữ penalty_id và các thuộc tính penalty_*; không node Penalty/HAS_PENALTY.
- **Edges (10 loại logic):** HAS_UNIT, HAS_CHILD, HAS_SIGN, CITES_UNIT, EXCLUDES_UNIT, CITES, AMENDS, REPEALS, IMPLEMENTS, CONSOLIDATES.
- **Identity:** giữ doc_id/unit_id/sign_id; không gộp theo text, title, ma_bien, qcvn_id hoặc so_hieu. Khóa cạnh theo tuple có type và predicate.
- **Inclusion:** 91 document production và units tương ứng; giữ lịch sử; loại out_of_scope/eval/raw khỏi knowledge graph. Relation văn bản chỉ hai đầu production.
- **Xref:** gate SAFE_EDGE bắt buộc; exclusion có predicate riêng. Thiếu bảng phân loại → chưa có cạnh xref. Không external placeholder.
- **Quy mô suy ra từ audit, chưa build:** 5.046 HAS_UNIT + 50.551 HAS_CHILD + 887 HAS_SIGN + 238 document relations = **56.722 cạnh không phải xref**. Số cạnh xref sau phân loại/gộp chưa biết; không cộng 8.144 chưa xác minh vào tổng.

### Kiểm tra phạm vi B1

Đối chiếu hash trước/sau cho các file trong data, kag, vendor/KAG, benchmark, tests, scripts, docker và docs; đối chiếu Git để kiểm tra file ngoài phạm vi. Chỉ file đề xuất này được phép khác. Manifest dataset 103/103 entry đã được xác minh.

```text
STATUS = B1_DOMAIN_MODEL_PROPOSED_WITH_OPEN_QUESTIONS
FILES_INSPECTED = 26
NODE_TYPES_PROPOSED = 3
EDGE_TYPES_PROPOSED = 10
DATA_FILES_CHANGED = 0
KAG_CODE_CHANGED = 0
VENDOR_CHANGED = 0
SCHEMA_CODE_IMPLEMENTED = false
GRAPH_BUILT = false
KAG_INGESTION_RUN = false
BENCHMARK_RUN = false
OUTPUT = docs/phase_b1_domain_model_proposal.md
OPEN_QUESTIONS = 7
```

Dừng tại B1 để review. Không commit, push hoặc bắt đầu B2.
