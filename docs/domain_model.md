# Mô hình miền pháp lý

Corpus trong `data/` có đúng ba loại node:

- **LegalDocument**: văn bản thuộc whitelist graph, giữ exact `doc_id`.
- **LegalUnit**: đơn vị nội dung, giữ exact `unit_id`; `unitType` chỉ nhận
  `Dieu`, `Khoan`, `Diem`, `QCVN`, `QCVN_Muc`.
- **TrafficSign**: record theo phiên bản QCVN, giữ exact `sign_id`; không gộp
  theo `ma_bien` hoặc giữa phiên bản 2019/2024.

`name=id` là nhãn kỹ thuật; hiển thị dùng `title/ten/maBien` từ nguồn.
Không bỏ occurrence suffix, normalize Unicode, trim ID, dùng title/order/text
hash làm khóa hoặc tạo UUID thay ID nguồn. Provenance gồm path tương đối,
SHA-256 file và số dòng từ 1; provenance không phải identity node.

## Cây đơn vị

`LegalDocument.hasUnit → LegalUnit` chỉ nối root có `parent_id=null`.
`LegalUnit.hasChild → LegalUnit` dùng parent_id nguồn, hai đầu cùng văn bản.
Quyền sở hữu unit thể hiện qua `docId` và đường đi trong cây.

QCVN là occurrence trong văn bản nguồn, có thể chỉ là đoạn dẫn; không tạo văn
bản QCVN giả hoặc gộp theo `qcvnId`. Không tự dựng cây từ số mục 1.1/1.1.1.
`order` dùng sắp xếp, exact unit_id làm tie-break xác định; tie-break không
phải thứ tự pháp lý. Text cha có thể lặp text con, không tính thành hai chứng
cứ độc lập.

## Xử phạt và biển báo

Penalty merge vào `penalty*` của LegalUnit theo unit_id, cardinality nguồn
1:0..1 và `penalty_id=unit_id`; không có node/vòng đời độc lập. Unit không có
penalty giữ các properties này vắng mặt. Không đổi null thành 0/false.
Tước GPLX `[min,max]` giữ hai thuộc tính tháng; không lấy trung bình hoặc suy
mọi biện pháp cùng áp dụng. Cardinality/join/doc mismatch phải báo lỗi, không ghi đè.

`LegalUnit.hasSign → TrafficSign` dùng exact unit_id của record biển. Giữ mã,
tên, nhóm, biến thể, mô tả, QCVN và ngày nguồn; tên rỗng vẫn rỗng.
Neo trích xuất có thể là Điều rộng dưới QCVN: cạnh ghi nhận nguồn, không
khẳng định đó là điều định nghĩa độc quyền biển. Không tự reparent.

## Quan hệ pháp lý

LegalDocument có năm quan hệ hướng nguồn → đích: `cites`, `amends`, `repeals`,
`implements`, `consolidates`. Hai cờ corpus phải true, hai IDs thuộc whitelist.
Không sinh thêm cạnh từ metadata văn bản. Missing/rỗng evidence giữ trong
provenance; không sáng tác citation. Sửa đổi/bãi bỏ không đủ suy hiệu lực từng
unit; văn bản hợp nhất giữ identity riêng.

Xref chỉ thành cạnh khi ledger là **SAFE_EDGE** và qua gate hash/join/endpoint
trong [schema](schema.md#gate-safe_edge-bên-ngoài). `is_exclusion=false` dùng
`citesUnit`, true dùng `excludesUnit`. Exclusion ghi ngữ cảnh ngoại lệ, không
phải citation khẳng định, phủ định tuyệt đối hoặc bãi bỏ. Giữ self-reference
và mọi evidence/provenance đã duyệt; không tạo node Evidence.

Khóa cạnh ứng dụng là SHA-256 canonical JSON của fully-qualified source type,
source ID, physical predicate, fully-qualified target type, target ID.
Evidence ngoài identity. Server dùng tuple **(node nguồn, predicate, node đích)**
và **LAST_WRITE_WINS** cho properties; Builder gộp evidence xác định trước
ghi đầy đủ properties. Khóa ứng dụng không điều khiển uniqueness server.
Codec/aggregation contract: [schema](schema.md).

## Phạm vi graph production

Whitelist yêu cầu record document, `scope != out_of_scope`, Markdown tương ứng
trong `processed/documents/`; loại `22_VBHN_BXD`, giữ văn bản lịch sử/Superseded.
Expected source counts nằm trong
[schema_contract.json](../kag/schema/schema_contract.json); không phải counts
của graph đang chạy hoặc quyền production WRITE. SAFE_EDGE counts là số record
được duyệt, khác số cạnh unique sau gộp.

Loại `processed/out_of_scope/**`, penalties bị loại, `processed/eval/**` và
`raw/**`. Eval không vào retrieval corpus hoặc sinh tri thức; metadata/manifest
chỉ dùng provenance. Tham chiếu ngoài corpus và classification khác SAFE_EDGE
giữ ngoài graph, không tạo placeholders. ID trùng, penalty join sai, endpoint
thiếu/lệch doc hoặc parent cycle phải fail closed; không sửa nguồn theo suy đoán.

Mô hình không kết luận pháp luật hiện hành ngoài corpus. Chunking, suy luận
thời gian và độ chính xác neo biển/QCVN không do schema miền bảo đảm.
