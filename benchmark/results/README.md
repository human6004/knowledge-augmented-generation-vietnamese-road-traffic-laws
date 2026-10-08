# Kết quả đánh giá

Thư mục này reserved. Evaluation Framework nhận `output_dir` ngoài repository
và ghi snapshots, manifest, metrics cùng reports có hash; implementation tại
[`kag/evaluation/report.py`](../../kag/evaluation/report.py).

Giữ dataset/protocol/model identity và PROVISIONAL/FROZEN/official riêng trong
báo cáo. Metrics không đủ điều kiện phải là null kèm lý do. `COMPLETE` không
phải quality PASS; `PAPER_ELIGIBLE=NO` vẫn là trạng thái hiện tại. Không đưa
secret hoặc overwrite source/gold vào workspace kết quả. Xem
[Evaluation Framework](../../docs/architecture.md#evaluation-framework).
