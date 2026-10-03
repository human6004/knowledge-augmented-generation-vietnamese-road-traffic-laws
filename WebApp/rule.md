# Quy tắc giao diện LuậtGT

Áp dụng khi tạo hoặc chỉnh sửa giao diện trong dự án này.

- Bám thiết kế và các chỉnh sửa đã được người dùng chốt; dùng lại màu, font, khoảng cách và thành phần hiện có.
- Không thêm nhãn pill/badge chỉ để trang trí, nhất là nhãn nằm trên tiêu đề như “Chào mừng trở lại”, “Khám phá ngay”, “Thông minh với AI”. Trang đăng nhập bắt đầu trực tiếp bằng tiêu đề và form.
- Chỉ dùng badge/chip khi mang thông tin cần phân biệt: trạng thái xử lý, vai trò, bộ lọc, lựa chọn hoặc căn cứ pháp lý. Nội dung giới thiệu thông thường dùng văn bản, không tự bọc thành một dãy pill.
- Với nhãn trạng thái tĩnh như “Điểm liệt”, “Phản hồi sai”, “Đã trả lời”, mặc định hiển thị chữ gọn, không nền màu, không viền bo tròn và không chấm màu đứng trước. Dùng màu chữ vừa đủ, luôn giữ tên trạng thái để không phụ thuộc vào màu. Không trình bày trạng thái như nút bấm; pill chỉ dùng cho bộ lọc/lựa chọn tương tác hoặc khi thiết kế đã chốt yêu cầu rõ ràng.
- Khi sửa kiểu hiển thị trạng thái, sửa thành phần dùng chung để các màn hình nhất quán, không thêm kiểu riêng cho từng bảng.
- Nhãn tĩnh và thao tác phải khác nhau ngay khi chưa hover: nhãn chỉ là chữ, nút có nền/viền rõ, bo góc vừa phải thay vì pill; thao tác dạng chữ phải có gạch chân. Không dùng cùng cách trình bày cho cả hai.
- Nút dùng động từ mô tả hành động (“Bổ sung”, “Cập nhật”). Thao tác phụ trong bảng có thể dùng nút icon gọn như ✓, nhưng phải có nền/viền để nhận ra là nút, chú thích khi rê chuột và tên truy cập (aria-label). Không kéo dài hàng bằng nhãn thao tác lặp lại; không dùng dấu ✓ trần như văn bản tĩnh. Khi có nhiều nút trong một hàng, nhóm vào cột thao tác với khoảng cách rõ ràng.
- Nút phải có vùng bấm đủ rộng, con trỏ tương tác, trạng thái hover/focus/disabled dễ nhận biết; không dựa vào hover để người dùng mới biết phần nào bấm được. Sửa thành phần Button dùng chung trước khi thêm kiểu riêng.
- Viết nội dung ngắn, cụ thể theo tác vụ. Không tự thêm khẩu hiệu, lời chào chung chung hoặc lời quảng cáo để lấp khoảng trống.
- Không tự thêm vòng tròn trang trí, gradient, hiệu ứng phát sáng, emoji hay icon bên cạnh mọi dòng chữ. Chi tiết trang trí cần có trong thiết kế được chốt hoặc có mục đích rõ ràng.
- Tạo phân cấp bằng cỡ chữ, độ đậm, căn lề và khoảng cách. Không dùng thêm card, khung viền, bo tròn lớn hoặc bóng đổ cho mọi phần nội dung.
- Giữ nhãn input, trạng thái lỗi, focus bàn phím, độ tương phản và bố cục điện thoại đầy đủ.
- Trước khi giao: đối chiếu thay đổi với yêu cầu, xem trên desktop/điện thoại khi có đổi bố cục và bỏ các chi tiết không giúp người dùng hiểu hoặc thao tác.

Ví dụ đã chốt: bỏ pill vàng “Chào mừng trở lại” trên trang đăng nhập; giữ tiêu đề “Đăng nhập LuậtGT” và form.

## Kiến trúc backend đã chốt

- Backend Spring Boot là monolith theo MVC, một ứng dụng triển khai và một MySQL.
- Thư mục/package tách rõ `controller`, `service`, `repository`, `model`, `dto`, `config`, `integration`, `exception`; mỗi entity, repository và request DTO có tên riêng theo nhiệm vụ.
- Controller chỉ nhận HTTP, kiểm tra DTO, gọi service; không truy cập repository. Service giữ quy tắc nghiệp vụ và giao dịch; repository chỉ truy cập dữ liệu. Không trả entity trực tiếp qua API.
- KAG Python là dịch vụ tích hợp bên ngoài theo README, không chia các nghiệp vụ Java thành microservice nếu chưa có yêu cầu mới.
- Tự đăng ký chỉ nhận USER; ADMIN bootstrap riêng. Chấm thi dùng đáp án đã kiểm duyệt và thời gian server, không dùng AI quyết định đáp án.
- Nhập câu hỏi/biển báo dưới dạng nháp, giữ nguồn và metadata pháp lý; không tự đoán dữ liệu thiếu hoặc tự xuất bản kết quả trích PDF.
- Các màn hình đang sử dụng phải gọi API thật; lỗi mạng hoặc thiếu dữ liệu hiển thị rõ, không thay bằng dữ liệu demo hoặc trạng thái thành công giả. Chức năng KAG chưa có phải ghi rõ chưa triển khai.
- Khi tạo bài thi, chỉ gửi các trường cần hiển thị; không gửi đáp án, ứng viên đáp án từ parser, cờ điểm liệt hoặc metadata kiểm duyệt. Chấm và tải ảnh bằng snapshot của chính bài thi, kiểm tra quyền sở hữu ở server.
- Script nhập chạy lại không được ghi đè dữ liệu/ảnh đã kiểm duyệt hoặc tự hủy xuất bản. Phải giữ bước kiểm duyệt tách khỏi nhập dữ liệu.
