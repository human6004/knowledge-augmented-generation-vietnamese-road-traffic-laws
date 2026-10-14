# Bộ deploy đi kèm bản thiết kế

Thư mục này chứa Dockerfiles, Compose và công cụ đóng gói riêng của bản thiết kế `kag-legal`. Đây là cấu hình tham chiếu của `WebApp/App-design/`, chưa được xác minh tương đương sản phẩm LuậtGT hiện tại.

**Cài và cập nhật LuậtGT dùng Compose tại root repository**, một project `luatgt` gồm 12 services. Làm theo [INSTALL](../../../docs/INSTALL.md), [UPDATE](../../../docs/UPDATE.md) và [Docker](../../../docker/README.md).

Compose trong thư mục này dùng project, images, ports và volumes riêng; cơ chế restore dump cũng khác. Không dùng `build.sh`, `pack.sh`, `install.sh` hoặc `install.ps1` ở đây để thay quy trình sản phẩm, không trỏ chúng tới storage LuậtGT đang phục vụ. Giữ các file này để tham chiếu thiết kế; cần kiểm riêng trước khi sử dụng cho mục đích khác.
