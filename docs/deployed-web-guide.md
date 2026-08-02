# Hướng dẫn sử dụng web OmniCare đã deploy

## 1. Truy cập

- Web production: `https://omnicare-chatagent.vercel.app`
- Trang đăng nhập: `https://omnicare-chatagent.vercel.app/login`
- Customer portal: `/portal`
- Admin portal: `/admin`

Tài khoản demo hiện được seed trong database. Dùng tài khoản được người vận hành cấp; không ghi mật khẩu hoặc connection string vào tài liệu, issue hay ảnh chụp màn hình.

## 2. Khách hàng

### Đăng nhập và điều hướng

1. Mở `/login`, nhập email và mật khẩu.
2. Sau khi đăng nhập, customer được chuyển tới `/portal`.
3. Chọn **Đơn hàng**, **Hỏi OmniCare AI** hoặc **Help Center**.

### Chat với OmniCare

- Popup chat xuất hiện trên các trang portal; `/portal/chat` cung cấp vùng chat riêng.
- Nhập câu hỏi tự nhiên, kể cả câu viết tắt hoặc sai chính tả.
- Bấm biểu tượng lịch sử để mở cuộc trò chuyện cũ hoặc tạo **Trò chuyện mới**.
- Mỗi message hiển thị người gửi và thời gian theo múi giờ Việt Nam.
- Citation có nhãn **Nguồn**; mở để xem tài liệu công khai được dùng.
- Khi hệ thống đang xử lý, UI hiển thị stage như tìm hiểu, đối chiếu và xử lý.

### Ảnh đính kèm

1. Bấm biểu tượng kẹp giấy.
2. Chọn tối đa 5 ảnh JPEG, PNG hoặc WebP.
3. Kiểm tra thumbnail, xóa ảnh chọn nhầm nếu cần.
4. Gửi kèm mô tả vấn đề; ảnh chỉ được dùng trong conversation hiện tại.

### Đơn hàng và UI tương tác

- Nếu yêu cầu cần một đơn cụ thể nhưng chưa có order ID, AI hiển thị danh sách đơn phù hợp.
- Bấm một order card để tiếp tục đúng intent: giao hàng, hủy, trả hàng, hoàn tiền hoặc thanh toán.
- Product selector cho phép chọn sản phẩm; checkout UI cho phép chọn số lượng và địa chỉ khi dữ liệu đủ.
- Hành động thay đổi dữ liệu luôn có bước xác nhận. Đọc nội dung, chọn đồng ý hoặc hủy.
- Không gửi lại confirmation cũ sau khi conversation hoặc context đã thay đổi.

### Gặp nhân viên CSKH

- Nhắn tự nhiên như “tôi muốn gặp nhân viên” hoặc “chuyển giúp tôi tới tư vấn viên”.
- AI tạo handoff và giữ toàn bộ conversation context.
- Khi nhân viên claim, customer thấy thông báo nhân viên đã tham gia.
- Tin nhắn tiếp theo được lưu trong cùng conversation; không cần kể lại từ đầu.

## 3. Admin

### Dashboard

`/admin` hiển thị số tài liệu đang hoạt động, graph build hoàn thành và AI Runs đã ghi nhận.

### Inbox hỗ trợ

1. Mở `/admin/inbox` để xem ticket cần người thật.
2. Chọn ticket để xem customer, priority, category, conversation và AI context.
3. Bấm claim để tham gia.
4. Dùng AI Assist để lấy gợi ý trả lời theo conversation hiện tại.
5. Chỉnh nội dung nếu cần, gửi cho khách và cập nhật trạng thái ticket.

AI Assist chỉ gợi ý; admin chịu trách nhiệm với message gửi thực tế.

### Knowledge Base

- `/admin/knowledge`: xem tài liệu đang hoạt động, ingestion status và thao tác quản lý.
- Thêm tài liệu bằng title, content, loại, visibility và metadata được UI yêu cầu.
- Sửa nội dung tạo/cập nhật version rồi reindex.
- Archive loại tài liệu khỏi Knowledge hoạt động và khỏi retrieval công khai.
- `/admin/knowledge/archive`: xem, restore hoặc kiểm tra tài liệu đã archive.
- Reindex dùng khi nội dung đúng nhưng index/RAG chưa đồng bộ.
- Retrieval Inspector dùng để kiểm tra query đang lấy chunk, score và nguồn nào.

Kiểm tra lifecycle tối thiểu:

1. Thêm một tài liệu chứa một fact duy nhất.
2. Chờ ingestion hoàn tất, hỏi chatbot bằng câu diễn đạt khác.
3. Xác nhận câu trả lời có citation đúng tài liệu.
4. Archive tài liệu, xóa cache/reindex nếu UI yêu cầu, hỏi lại.
5. Chatbot phải không còn dùng fact đã archive.
6. Restore, reindex và xác nhận fact xuất hiện lại.

### AI Runs

- `/admin/ai-runs`: danh sách lượt chạy, intent, trạng thái và thời gian.
- Trang chi tiết hiển thị stage, model profile, tool calls, retrieval results và review.
- Dùng dữ liệu này để phân biệt lỗi routing, tool, KB, provider hoặc latency.

## 4. Help Center và đơn hàng

- `/help`: tìm tài liệu công khai đã publish.
- `/portal/orders`: xem các đơn thuộc customer hiện tại.
- `/portal/orders/[id]`: xem chi tiết order, payment, shipment và refund có quyền truy cập.
- Không thể truy cập order của customer khác; API trả forbidden/not accessible.

## 5. Xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra |
| --- | --- |
| Không đăng nhập được | Kiểm tra email, mật khẩu, rate limit 15 phút và seed database. |
| Chat không trả lời | Mở AI health, AI Runs và log Render; kiểm tra LLM provider. |
| Không thấy lịch sử | Kiểm tra đúng tài khoản, conversation chưa bị close và API conversations. |
| Không chọn được đơn | Kiểm tra order card còn active, conversation context và order ownership. |
| Không tạo ticket | Kiểm tra intent/handoff fields, ticket fingerprint và Inbox filter. |
| KB mới chưa được dùng | Kiểm tra publish, visibility, effective date, ingestion và reindex. |
| KB đã archive vẫn xuất hiện | Xóa retrieval cache, kiểm tra version/chunk còn searchable. |
| Ảnh không tải lên | Kiểm tra MIME, kích thước, giới hạn 5 ảnh và session đăng nhập. |

## 6. Quy tắc demo

- Không nhập dữ liệu cá nhân hoặc credential thật.
- Không coi câu trả lời AI là quyết định thanh toán/pháp lý cuối cùng.
- Hủy, trả hàng, checkout và dispute phải qua confirmation.
- Refund cần nhân viên phê duyệt.
- Khi trình diễn, chuẩn bị sẵn một customer có nhiều order và một admin ở cửa sổ riêng để test handoff.
