# Entry points vận hành

Thư mục root này reserved, chưa có wrapper script riêng. Runtime Builder/
resume/verify đã nằm trong [`kag.__main__`](../kag/__main__.py);
dataset validate/freeze/import trong [`kag.evaluation`](../kag/evaluation/__main__.py).
Không cần tạo thêm runner để dùng các implementation hiện tại.

Từ root repository:

```sh
python -B -m kag --help
python -B -m kag.evaluation --help
```

Script hạ tầng nằm tại [`docker/`](../docker/README.md); nhập và kiểm tra dữ
liệu nghiệp vụ WebApp tại [`WebApp/scripts/`](../WebApp/README.MD).
Các script nhập/build/verify-stack có side effects được mô tả trong hướng dẫn
riêng, không thuộc kiểm tra tài liệu. Production WRITE vẫn BLOCKED. Xem
[kiến trúc](../docs/architecture.md) và [vận hành](../docs/runner.md).
