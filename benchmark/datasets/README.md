# Dataset đánh giá

Thư mục này reserved; validation, lifecycle và legacy importer hiện nằm tại
[`kag/evaluation`](../../kag/evaluation/). Corpus và eval nguồn tại
[`data/`](../../data/) được bảo vệ, không chuyển hoặc sửa tại đây.

PROVISIONAL dành cho phát triển; FROZEN cần canonical bytes, version và manifest
hash đã xác minh. Freeze không tự cho quyền official benchmark hoặc publication.
CLI `python -B -m kag.evaluation freeze` luôn tạo bản nonofficial, output mới
ngoài repo. Xem [benchmark workspace](../README.md) và
[dataset lifecycle](../../docs/architecture.md#evaluation-framework).
