# OmniCare AI Customer Support Hub

MVP hỗ trợ khách hàng có căn cứ: customer/order/payment/shipment tools, Knowledge Platform, LangGraph workflow, citation và safe handoff.

## Chạy local

```powershell
docker compose up --build
```

- Web: `http://localhost:3000`
- AI health: `http://localhost:8000/health`
- Orders: `http://localhost:3000/orders`
- Help Center: `http://localhost:3000/help`
- Login: `http://localhost:3000/login`
- Customer portal: `http://localhost:3000/portal`
- Admin portal: `http://localhost:3000/admin`

Docker startup tự chạy Prisma migrations và deterministic seed.

Dataset mặc định gồm 20 khách hàng, 60 đơn hàng, 408 knowledge documents, 40 historical tickets, 12 incidents và 100 evaluation cases.

## Tài khoản demo

- Admin: `admin@test.com` / `admin`
- Customer 1: `user1@test.com` / `user`
- Customer 2: `user2@test.com` / `user`

Đổi toàn bộ mật khẩu trước khi deploy public.

## Agent runtime

- LangGraph supervisor chạy transaction, incident và knowledge subgraphs song song.
- Transaction access qua LangChain `@tool`; trusted customer context không nằm trong model arguments.
- PostgreSQL checkpointer lưu state theo `conversation_id`.
- GraphRAG dùng entities, edges và claims có provenance về document/version/chunk.
- LangSmith chỉ bật khi có khóa mới hợp lệ; khóa đã gửi trong chat không được tái sử dụng.

## Kiểm tra không cần Docker

```powershell
cd apps/web
$env:DATABASE_URL='postgresql://db-user:db-password@localhost:5432/omnicare'
npm run build
npm run lint

cd ../ai-service
$env:PYTHONPATH='.'
py -3.13 -m unittest discover -s tests -v
```

## An toàn

- Customer identity và order ownership bắt buộc trước mọi transaction lookup.
- `AUTHORIZED` không được diễn giải thành đã thanh toán.
- ETA là dự kiến, không phải cam kết.
- Refund/cancellation/account deletion chỉ tạo `PENDING_APPROVAL` proposal.
- Internal, expired, archived và draft knowledge không được public citation.
- System prompt: `apps/ai-service/app/prompts/core_system.md`.

## Giới hạn hiện tại

- Email là simulator; không kết nối provider thật.
- Embedding column đã có; retrieval hiện dùng PostgreSQL full-text deterministic. Vector embedding cần provider cấu hình.
- Docker Desktop phải chạy để kiểm thử migration và end-to-end local.
