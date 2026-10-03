# Mô hình miền pháp lý v0.1

Nguồn tri thức: dataset **LOCKED R2**. Mô hình có đúng ba loại node:

- **LegalDocument**: văn bản production, identity giữ nguyên `doc_id`.
- **LegalUnit**: đơn vị nội dung, identity giữ nguyên `unit_id`; `unitType`
  nhận đúng `Dieu`, `Khoan`, `Diem`, `QCVN`, `QCVN_Muc`.
- **TrafficSign**: bản ghi biển theo phiên bản QCVN, identity giữ nguyên
  `sign_id`. Không gộp theo `ma_bien` hoặc giữa phiên bản 2019/2024.

`name` kỹ thuật bằng `id`; hiển thị dùng `title`, `ten`, `maBien` từ nguồn.
Không bỏ hậu tố occurrence, chuẩn hóa Unicode, dùng title/order làm khóa hoặc
tạo UUID thay ID nguồn. Provenance dùng đường dẫn tương đối, SHA-256 file và
số dòng bắt đầu từ 1; provenance không phải identity node.

## Cây đơn vị

`LegalDocument.hasUnit → LegalUnit` chỉ nối root có `parent_id=null`.
`LegalUnit.hasChild → LegalUnit` theo `parent_id` thực, hai đầu cùng văn bản.
Quyền sở hữu mọi unit vẫn thể hiện qua `docId` và đường đi trong cây.

Một loại LegalUnit phục vụ truy vấn text/ID và traversal chung. QCVN là
occurrence trong văn bản nguồn, có thể chỉ là đoạn dẫn; không tạo văn bản QCVN
giả hoặc gộp theo `qcvnId`. Không tự tạo cây từ số mục 1.1/1.1.1. `order` dùng
sắp xếp, `unit_id` làm tie-break xác định; không coi tie-break là thứ tự pháp lý.
Text cha có thể lặp text con, không coi hai tầng là hai chứng cứ độc lập.

## Xử phạt và biển báo

Penalty gộp vào thuộc tính `penalty*` của LegalUnit: R2 có 1.966 record,
quan hệ nguồn 1:0..1, `penalty_id=unit_id`, không có vòng đời độc lập.
Unit không có penalty giữ toàn bộ thuộc tính penalty vắng mặt. Không đổi
null thành 0/false. Tước GPLX `[min,max]` giữ hai thuộc tính tháng; không lấy
trung bình hoặc suy ra mọi biện pháp đồng thời áp dụng. Nếu cardinality nguồn
thay đổi, adapter phải báo lỗi thay vì ghi đè.

`LegalUnit.hasSign → TrafficSign` theo `unit_id` thực của record biển.
Giữ mã, tên, nhóm, biến thể, mô tả, QCVN và ngày từ nguồn; tên rỗng vẫn rỗng.
Neo trích xuất hiện có thể là Điều rộng dưới QCVN: cạnh ghi nhận nguồn record,
không khẳng định đó là điều định nghĩa độc quyền biển. Không tự reparent.

## Quan hệ pháp lý

LegalDocument có năm quan hệ cùng hướng nguồn → đích: `cites`, `amends`,
`repeals`, `implements`, `consolidates`. Cả hai cờ corpus phải true và cả hai
ID phải thuộc production. Không sinh thêm cạnh từ danh sách metadata văn bản.
Thiếu/rỗng evidence vẫn bảo toàn trong provenance; không sáng tác trích dẫn.
Quan hệ sửa đổi/bãi bỏ không đủ suy ra phạm vi hoặc hiệu lực từng unit.
Văn bản hợp nhất giữ identity riêng với bản gốc.

Xref chỉ tạo cạnh khi classification ngoài repo là **SAFE_EDGE** và qua gate
hash/join/endpoint trong [schema.md](schema.md). `is_exclusion=false` dùng
`citesUnit`; true dùng `excludesUnit`. Exclusion ghi nhận ngữ cảnh ngoại lệ,
không phải citation khẳng định, phủ định tuyệt đối hoặc bãi bỏ. Giữ self-reference
và mọi record evidence/provenance đã duyệt. Không tạo node Evidence.

Khóa cạnh ứng dụng là SHA-256 canonical JSON của type nguồn fully qualified,
ID nguồn, predicate vật lý, type đích fully qualified, ID đích. Evidence nằm
ngoài identity; nhiều record cùng cạnh được gộp xác định, không ghi đè.
Identity server và quy tắc cập nhật cạnh theo [schema.md](schema.md).

## Phạm vi graph production

Whitelist gồm document có record, `scope != out_of_scope` và Markdown tương ứng
trong `processed/documents/`: R2 có 91 document, loại `22_VBHN_BXD`.
Giữ văn bản lịch sử/Superseded. Theo nguồn có 55.597 unit, 887 biển,
238 quan hệ văn bản nội bộ; penalty chỉ merge thuộc tính. 8.144 SAFE_EDGE
là số record được duyệt, không phải số cạnh duy nhất sau gộp provenance.

Loại `processed/out_of_scope/**`, penalty bị loại, `processed/eval/**`, `raw/**`;
eval không đi vào retrieval corpus hoặc sinh tri thức. Metadata/manifest chỉ
phục vụ provenance. Tham chiếu ngoài corpus và classification khác SAFE_EDGE
giữ ngoài graph; không tạo placeholder. ID trùng, join penalty sai, endpoint
thiếu, lệch doc hoặc parent cycle phải fail closed; không sửa snapshot bằng suy đoán.

Mô hình không kết luận pháp luật hiện hành ngoài snapshot. Chunking, suy luận
thời gian và độ chính xác neo biển/QCVN thuộc các giai đoạn sau.
