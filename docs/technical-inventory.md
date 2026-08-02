# Danh sách công cụ, mô hình, API và nguồn tham khảo

Tài liệu được tạo từ source/config ngày 2 tháng 8 năm 2026. Registry và route source là nguồn chuẩn nếu tài liệu khác biệt.

## 1. Công nghệ chính

| Thành phần | Công nghệ | Vai trò |
| --- | --- | --- |
| Web | Next.js 16.2.12, React 19.2.4, TypeScript | UI, API gateway, auth, SSE client, admin/customer portal. |
| ORM | Prisma 6.18 | Schema, migration và truy cập PostgreSQL từ web. |
| AI API | FastAPI, Pydantic, Uvicorn | Contracts, agent endpoints, streaming và health. |
| Agent | LangChain 1.x, LangGraph 1.x | Tool calling, middleware, graph workflow và checkpoint. |
| Database | PostgreSQL 16, pgvector | Transaction, conversation, memory, KB, vector, graph và audit. |
| Test | Python unittest, Playwright | Unit/integration và E2E production. |
| Hosting | Vercel, Render | Web và AI service. |

## 2. Model profiles

| Profile | Environment | Giá trị deploy hiện tại | Mục đích |
| --- | --- | --- | --- |
| Fast | `LLM_FAST_MODEL` | `cx/gpt-5.4-mini` | Routing, intent rõ, trả lời thường và latency thấp. |
| Reasoning | `LLM_REASONING_MODEL` | `cx/gpt-5.6-terra` | Case phức tạp, policy, multi-intent, risk hoặc evidence conflict. |
| Reviewer | `LLM_REVIEWER_MODEL` | `cx/gpt-5.6-terra` | Review semantic khi deterministic reviewer chưa đủ. |
| Knowledge builder | dùng reasoning profile | `cx/gpt-5.6-terra` | Tác vụ phân tích Knowledge khi workflow yêu cầu. |
| Embedding | `EMBEDDING_MODEL` | tùy provider | Vector hóa chunk/query; lexical retrieval là fallback. |

Model router chuyển sang reasoning khi complexity score từ 45, dựa trên complexity, intent cần authority, multi-intent, risk flags, evidence conflict và route confidence thấp. Reviewer chỉ gọi model cho lỗi cần đánh giá ngữ nghĩa.

## 3. Tool registry

### Read tools

| Tool | Dữ liệu/chức năng |
| --- | --- |
| `get_customer_profile` | Hồ sơ customer đã xác minh. |
| `get_recent_orders` | Danh sách order gần đây thuộc customer. |
| `get_order_summary` | Tổng hợp số lượng/trạng thái order. |
| `find_eligible_orders` | Tìm order phù hợp với hủy, giao vận, thanh toán, refund hoặc return. |
| `get_order_details` | Chi tiết order sau ownership check. |
| `get_shipping_status` | Shipment và trạng thái giao hàng. |
| `get_payment_status` | Trạng thái payment của order thuộc customer. |
| `get_refund_status` | Trạng thái refund. |
| `check_return_eligibility` | Kiểm tra điều kiện trả hàng theo order/reason. |
| `get_active_incidents` | Incident dịch vụ đang hoạt động. |
| `search_knowledge` | Hybrid RAG trên tài liệu được phép truy cập. |
| `search_products` | Tìm sản phẩm theo nhu cầu. |
| `get_product_details` | Chi tiết, giá và tồn kho sản phẩm. |
| `get_customer_addresses` | Địa chỉ customer dùng cho checkout. |
| `quote_checkout` | Tính quote trước khi tạo checkout. |

### Write tools

| Tool | Risk | Approval |
| --- | --- | --- |
| `create_support_ticket` | MEDIUM | Không cần confirmation; dùng cho handoff. |
| `cancel_order` | HIGH | Customer confirmation. |
| `create_return_request` | MEDIUM | Customer confirmation. |
| `create_shipping_investigation` | MEDIUM | Customer confirmation. |
| `create_dispute` | HIGH | Customer confirmation. |
| `create_refund` | CRITICAL | Human approval. |
| `create_checkout_session` | MEDIUM | Customer confirmation. |
| `confirm_checkout` | HIGH | Customer confirmation. |

Mọi write tool là idempotent. Tool policy kiểm actor role và verified customer context trước khi chạy.

## 4. AI service API

| Method | Endpoint | Mục đích |
| --- | --- | --- |
| GET | `/health` | Kiểm tra service, DB, LLM và model. |
| POST | `/vision/analyze` | Phân tích ảnh JPEG/PNG/WebP đã gửi. |
| POST | `/admin/assist` | Gợi ý trả lời cho nhân viên theo ticket context. |
| POST | `/agent/run` | Chạy agent không streaming. |
| POST | `/agent/stream` | Chạy agent bằng SSE, gồm progress/token/done. |
| POST | `/agent/confirm` | Xác nhận pending action. |
| POST | `/agent/interactions` | Xử lý lựa chọn UI có semantic payload. |
| POST | `/retrieval/search` | Truy xuất KB theo query/profile/visibility. |
| POST | `/retrieval/rebuild-all` | Rebuild retrieval index. |
| POST | `/retrieval/cache/clear` | Xóa retrieval cache. |
| POST | `/evaluation/run` | Chạy evaluation qua API. |

## 5. Web API

| Nhóm | Endpoint chính |
| --- | --- |
| Auth | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/session` |
| Chat | `POST /api/chat/stream`, `POST /api/chat/interactions`, `POST /api/chat/actions/confirm` |
| Conversation | `GET/POST /api/chat/conversations`, messages, close conversation |
| Attachment | upload attachment và đọc attachment theo ID |
| Handoff | tạo, đọc và kết thúc trạng thái handoff |
| Customer orders | danh sách order và chi tiết order thuộc session |
| Help | tìm kiếm tài liệu Help Center công khai |
| Admin inbox | danh sách ticket cần hỗ trợ |
| Admin ticket | chi tiết, claim, reply, status và AI Assist |
| Knowledge | auto-ingest, document detail/delete/archive/restore/reindex và deletion impact |
| Ingestion | trạng thái run và SSE tiến độ |
| Retrieval admin | inspector, reindex-all và rebuild graph |
| Graph admin | tree, search, neighborhood, children, evidence và workspace CRUD/parse/validate/publish |

Tất cả endpoint admin gọi `requireAdmin`. Endpoint customer lấy identity từ server session, không nhận customer ID tin cậy từ trình duyệt.

## 6. Contracts quan trọng

- `IncomingMessage`: message, content, customer, channel, conversation, actor, locale và page context.
- `GroundedAgentResponse`: answer, intent, confidence, evidence, citations, tool calls, UI, pending action, quality, priority và handoff.
- `RetrievalRequest/Result`: query profile, visibility, document/version/chunk, score, provenance và compression metadata.
- `AgentUiComponent`: order/product selector, form, confirmation và các option do backend chuẩn hóa.
- `ToolContext/ToolResult`: trusted identity, idempotency, status, safe error và observed time.

## 7. Biến môi trường chính

| Biến | Ý nghĩa |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string; bắt buộc, lưu trong secret manager. |
| `AI_SERVICE_URL` | URL FastAPI dùng bởi web. |
| `LLM_BASE_URL`, `LLM_API_KEY` | OpenAI-compatible provider. |
| `LLM_ENABLED` | Bật/tắt model calls. |
| `LLM_FAST_MODEL`, `LLM_REASONING_MODEL`, `LLM_REVIEWER_MODEL` | Model theo profile. |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | Vector provider và kích thước. |
| `AGENT_MAX_MODEL_CALLS` | Giới hạn model calls mỗi run. |
| `RETRIEVAL_TOKEN_BUDGET`, `RETRIEVAL_MAX_CHUNKS` | Ngân sách context RAG. |
| `LANGSMITH_*` | Tracing tùy chọn. |
| `SESSION_COOKIE_SECURE` | Cookie secure trên HTTPS. |

Không ghi giá trị secret vào Git, docs, log hoặc client bundle.

## 8. Nguồn tham khảo chính

### Framework và nền tảng

- Next.js Documentation: `https://nextjs.org/docs`
- React Documentation: `https://react.dev`
- Prisma Documentation: `https://www.prisma.io/docs`
- FastAPI Documentation: `https://fastapi.tiangolo.com`
- LangChain Python Documentation: `https://docs.langchain.com/oss/python/langchain/overview`
- LangGraph Documentation: `https://docs.langchain.com/oss/python/langgraph/overview`
- PostgreSQL Documentation: `https://www.postgresql.org/docs/`
- pgvector repository/documentation: `https://github.com/pgvector/pgvector`
- Playwright Documentation: `https://playwright.dev/docs/intro`
- Vercel Documentation: `https://vercel.com/docs`
- Render Documentation: `https://render.com/docs`

### Nguồn nội dung Knowledge

- Shopee Việt Nam Help Center và các URL cụ thể lưu trong `KnowledgeSourcePage`/citation.
- TikTok Shop Việt Nam University và các snapshot có provenance.
- Tài liệu Omni nội bộ do admin nhập, có version, visibility, effective date và review state.

Nguồn marketplace phải được snapshot theo ngày, giữ URL và hash. Nội dung dẫn xuất phải được review trước khi publish; không tự nhận là chính sách chính thức của Omni.

## 9. Test và lệnh vận hành

```powershell
npm test
npm run eval:audit
npm run test:e2e:production
npm run test:e2e:handoff
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

Raw evaluation report là artifact sinh lại được và không commit. `datasets/artifacts/release-manifest.json` chỉ lưu bản tóm tắt release có ngày chạy.
