# OmniCare AI Customer Support Hub

Nền tảng chăm sóc khách hàng dùng Next.js, FastAPI, PostgreSQL, LangChain/LangGraph, transaction tools, hybrid RAG, citation, streaming và human handoff.

## Production

- Web: `https://omnicare-chatagent.vercel.app`
- AI health: `https://omnicare-ai-service.onrender.com/health`

## Tài liệu

- [Kiến trúc hệ thống](docs/architecture.md)
- [Hướng dẫn sử dụng web đã deploy](docs/deployed-web-guide.md)
- [Công cụ, mô hình, API và nguồn tham khảo](docs/technical-inventory.md)
- [Phương pháp evaluation chống overfit](docs/holdout-evaluation.md)

## Chạy local

1. Sao chép `.env.example` thành `.env` và điền credential local.
2. Không commit `.env`, API key hoặc database URL.
3. Chạy:

```powershell
docker compose up --build
```

- Web: `http://localhost:3000`
- AI health: `http://localhost:8000/health`

## Kiểm thử

```powershell
npm test
npm run eval:audit
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

E2E production:

```powershell
npm run test:e2e:production
npm run test:e2e:handoff
```

## Nguyên tắc an toàn

- Identity và order ownership được xác minh ở backend trước transaction lookup.
- Write action dùng idempotency và confirmation theo mức rủi ro.
- Refund cần human approval.
- Knowledge draft, internal, expired hoặc archived không được citation công khai.
- Secret chỉ nằm trong environment của Render/Vercel hoặc `.env` local đã ignore.
