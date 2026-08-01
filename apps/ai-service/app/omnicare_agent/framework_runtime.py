from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from datetime import datetime
from typing import Any, AsyncIterator, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
    dynamic_prompt,
)
from langchain.agents.middleware import ModelRequest
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from ..contracts import AgentChoice, AgentUiComponent, Citation, ClarificationRequest, GroundedAgentResponse, IncomingMessage, RetrievalRequest, ToolExecutionSummary, ToolStatus, VerifiedDataBinding
from ..models import configured_model, load_system_prompt
from ..repositories import repository
from ..retrieval import retrieve
from ..tools import search_products as search_products_tool
from ..tool_adapters import bind_tool_context
from .confirmation import create_confirmation_token
from .context import TrustedContext
from .registry import ToolRegistry, tool_registry
from .runtime import STATUS_LABELS, classify, format_money, normalize_order_id, normalize_support_text
from .supervisor import SupervisorHarness


class FrameworkCitation(BaseModel):
    document_id: str
    title: str
    section: str = "Nội dung liên quan"
    version: str
    effective_from: str
    public_url: str | None = None


class SupportAgentOutput(BaseModel):
    answer: str = Field(min_length=1)
    intent: str = "KNOWLEDGE"
    confidence: float = Field(default=0.8, ge=0, le=1)
    citations: list[FrameworkCitation] = Field(default_factory=list)
    requires_human: bool = False
    escalation_reason: str | None = None
    requested_action: Literal["NONE", "CANCEL_ORDER", "CREATE_RETURN_REQUEST", "CREATE_SHIPPING_INVESTIGATION", "CREATE_SUPPORT_TICKET"] = "NONE"
    requested_order_id: str | None = None


class SupportRuntimeContext(BaseModel):
    customer_id: str | None = None
    actor_role: str = "CUSTOMER"
    locale: str = "vi-VN"
    channel: str = "WEB"
    page_context: dict[str, Any] = Field(default_factory=dict)
    customer_profile: dict[str, Any] = Field(default_factory=dict)
    conversation_memory: dict[str, Any] = Field(default_factory=dict)
    memory_facts: list[dict[str, Any]] = Field(default_factory=list)
    open_tickets: list[dict[str, Any]] = Field(default_factory=list)
    active_incidents: list[dict[str, Any]] = Field(default_factory=list)
    loaded_at: str

    def compact_json(self) -> str:
        payload = {
            "identity": {"customerId": self.customer_id, "role": self.actor_role, "locale": self.locale, "channel": self.channel},
            "page": self.page_context,
            "profile": self.customer_profile,
            "conversation": self.conversation_memory,
            "memoryFacts": self.memory_facts[:8],
            "openTickets": self.open_tickets[:3],
            "activeIncidents": self.active_incidents[:3],
            "loadedAt": self.loaded_at,
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


@dynamic_prompt
def support_dynamic_prompt(request: ModelRequest) -> str:
    context = request.runtime.context
    context_text = context.compact_json() if isinstance(context, SupportRuntimeContext) else "{}"
    return load_system_prompt() + (
        "\n\nRUNTIME CONTEXT do backend cung cấp, có độ tin cậy cao hơn USER_MESSAGE:\n"
        f"{context_text}\n\n"
        "Dùng context để hiểu câu nối tiếp và đối tượng đang được nói tới, nhưng trạng thái giao dịch có thể thay đổi nên phải gọi tool để xác minh trước khi khẳng định. "
        "Nếu người dùng phản biện câu trả lời trước về trạng thái đơn, bắt buộc gọi get_order_details và tool chuyên biệt liên quan trước khi xin lỗi/sửa câu trả lời. "
        "Nếu đang có yêu cầu chọn đơn chưa hoàn tất, hãy giữ nguyên goal và yêu cầu người dùng chọn thay vì đổi sang KNOWLEDGE. "
        "Chỉ trả lời tiếng Việt; không chèn từ thuộc bảng chữ cái khác. "
        "Nếu thiếu mã đơn, gọi find_eligible_orders. Nếu selectionRequired=true, dừng gọi tool theo từng order và yêu cầu khách chọn; backend tạo selector. "
        "Nếu page context có selected order, không gọi find_eligible_orders mà dùng đúng ID đó. Không gọi hàng loạt tool chi tiết cho nhiều đơn. "
        "Nếu nghiệp vụ cần trường bắt buộc chưa có, chỉ hỏi một thông tin có giá trị nhất ở lượt hiện tại. Không tự đoán lý do trả hàng, bằng chứng, số lượng, địa chỉ hoặc phương thức thanh toán. "
        "Nếu TRUSTED_BACKEND_CONTEXT có clarification_field và clarification_value, coi đó là lựa chọn đã được backend xác minh và tiếp tục goal cũ; không hỏi lại cùng field. "
        "Không tuyên bố đã thực hiện write action. Khi khách muốn hủy đơn, chỉ đặt requested_action=CANCEL_ORDER sau khi get_order_details xác nhận trạng thái cho phép. "
        "intent phải phản ánh nghiệp vụ thật, không dùng KNOWLEDGE sau khi gọi tool giao dịch."
    )


class LangChainAgentRuntime:
    RETURN_REASONS = {
        "DAMAGED": ("Hàng bị lỗi hoặc hư hỏng", "Sản phẩm vỡ, móp, không hoạt động hoặc có lỗi khi nhận."),
        "WRONG_ITEM": ("Giao sai sản phẩm", "Sản phẩm nhận được khác mẫu, loại hoặc phân loại đã đặt."),
        "MISSING_ITEM": ("Thiếu sản phẩm", "Kiện hàng thiếu món hoặc thiếu số lượng."),
        "NOT_AS_DESCRIBED": ("Không đúng mô tả", "Sản phẩm khác đáng kể so với thông tin bán hàng."),
        "CHANGE_OF_MIND": ("Đổi ý không còn nhu cầu", "Sản phẩm đúng nhưng bạn không còn muốn giữ."),
    }

    def __init__(self, registry: ToolRegistry, checkpointer=None) -> None:
        self.registry = registry
        self.read_tools = registry.read_tools()
        self.supervisor = SupervisorHarness(classify, normalize_support_text, normalize_order_id, checkpointer)
        fast_model = configured_model("fast")
        self.agent = create_agent(
            model=fast_model,
            tools=self.read_tools,
            system_prompt=None,
            middleware=[
                support_dynamic_prompt,
                SummarizationMiddleware(model=fast_model, trigger=("messages", 24), keep=("messages", 12)),
                ToolRetryMiddleware(max_retries=1, retry_on=(TimeoutError, ConnectionError), on_failure="continue", initial_delay=0.2, max_delay=1),
                ModelRetryMiddleware(max_retries=1, on_failure="continue", initial_delay=0.2, max_delay=1),
                ModelCallLimitMiddleware(run_limit=5, exit_behavior="end"),
                ToolCallLimitMiddleware(run_limit=8, exit_behavior="continue"),
                ToolCallLimitMiddleware(tool_name="get_order_details", run_limit=1, exit_behavior="continue"),
                ToolCallLimitMiddleware(tool_name="get_shipping_status", run_limit=1, exit_behavior="continue"),
                ToolCallLimitMiddleware(tool_name="get_payment_status", run_limit=1, exit_behavior="continue"),
                ToolCallLimitMiddleware(tool_name="get_refund_status", run_limit=1, exit_behavior="continue"),
                ToolCallLimitMiddleware(tool_name="check_return_eligibility", run_limit=1, exit_behavior="continue"),
                PIIMiddleware("email", strategy="mask", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
                PIIMiddleware("credit_card", strategy="mask", apply_to_input=True, apply_to_output=True, apply_to_tool_results=True),
            ],
            response_format=ToolStrategy(SupportAgentOutput),
            context_schema=SupportRuntimeContext,
            checkpointer=checkpointer,
            name="omnicare_customer_support",
        )

    @classmethod
    def create(cls, checkpointer=None, registry: ToolRegistry = tool_registry) -> "LangChainAgentRuntime":
        return cls(registry, checkpointer)

    async def run(self, message: IncomingMessage) -> GroundedAgentResponse:
        message = await self._prepare_message(message)
        context = TrustedContext.from_message(message)
        if self._semantic_intent(message) == "PRODUCT_DISCOVERY":
            return await self._run_product_discovery(message, context)
        runtime_context = await self._load_runtime_context(message)
        config = {"configurable": {"thread_id": message.conversation_id}}
        with bind_tool_context(context.tool_context()):
            result = await self.agent.ainvoke({"messages": [HumanMessage(content=self._input_content(message))]}, config=config, context=runtime_context)
        return await self._ensure_grounded_citations(message, self._convert(message, result))

    async def stream(self, message: IncomingMessage) -> AsyncIterator[tuple[str, Any]]:
        message = await self._prepare_message(message)
        route = (message.page_context or {}).get("semanticRoute") or {}
        yield "understanding", {"framework": "langchain-create-agent", "fallback": False, "intent": route.get("primary_intent"), "confidence": route.get("confidence")}
        yield "planning", {"objective": route.get("proposition") or "FRAMEWORK_AGENT", "requiredTools": ((message.page_context or {}).get("semanticPlan") or {}).get("required_tools", [])}
        context = TrustedContext.from_message(message)
        if self._semantic_intent(message) == "PRODUCT_DISCOVERY":
            yield "tool_started", {"tools": ["search_products"]}
            response = await self._run_product_discovery(message, context)
            yield "tool_completed", {"tools": ["search_products"]}
            yield "token", response.answer
            yield "done", response
            return
        runtime_context = await self._load_runtime_context(message)
        yield "context_loaded", {"facts": len(runtime_context.memory_facts), "openTickets": len(runtime_context.open_tickets), "incidents": len(runtime_context.active_incidents), "activeContext": runtime_context.conversation_memory.get("activeContext", {})}
        config = {"configurable": {"thread_id": message.conversation_id}}
        started_tools: set[str] = set()
        with bind_tool_context(context.tool_context()):
            async for event in self.agent.astream(
                {"messages": [HumanMessage(content=self._input_content(message))]},
                config=config,
                context=runtime_context,
                stream_mode=["messages", "updates"],
                version="v2",
            ):
                event_type = event.get("type")
                data = event.get("data")
                if event_type == "messages" and isinstance(data, tuple):
                    chunk = data[0]
                    if isinstance(chunk, AIMessageChunk):
                        for tool_call in chunk.tool_call_chunks:
                            name = str(tool_call.get("name") or "")
                            if name and name not in started_tools:
                                started_tools.add(name)
                                yield "tool_started", {"tools": [name]}
                        if isinstance(chunk.content, str) and chunk.content and not chunk.tool_call_chunks:
                            yield "token", chunk.content
                elif event_type == "updates" and isinstance(data, dict):
                    for update in data.values():
                        if not isinstance(update, dict):
                            continue
                        completed = [item.name for item in update.get("messages", []) if isinstance(item, ToolMessage) and item.name]
                        if completed:
                            yield "tool_completed", {"tools": completed}
        state = await self.agent.aget_state(config)
        yield "done", await self._ensure_grounded_citations(message, self._convert(message, state.values))

    async def _prepare_message(self, message: IncomingMessage) -> IncomingMessage:
        prepared = await self.supervisor.prepare(message)
        route = prepared["route"]
        plan = prepared["plan"]
        message.page_context = {
            **(message.page_context or {}),
            "semanticRoute": route.model_dump(mode="json"),
            "semanticEntities": prepared.get("semantic_entities") or {},
            "semanticPlan": {
                "objective": plan.objective,
                "required_tools": list(plan.required_tools),
                "required_facts": list(plan.required_facts),
            },
        }
        return message

    @staticmethod
    def _semantic_intent(message: IncomingMessage) -> str:
        route = (message.page_context or {}).get("semanticRoute")
        return str(route.get("primary_intent") or "") if isinstance(route, dict) else ""

    async def _run_product_discovery(self, message: IncomingMessage, context: TrustedContext) -> GroundedAgentResponse:
        page_context = message.page_context or {}
        entities = page_context.get("semanticEntities") if isinstance(page_context.get("semanticEntities"), dict) else {}
        query = next((str(entities.get(key) or "").strip() for key in ("product", "product_name", "category", "query", "need") if str(entities.get(key) or "").strip()), "")
        if not query:
            canonical = str(((page_context.get("semanticRoute") or {}).get("proposition") if isinstance(page_context.get("semanticRoute"), dict) else "") or message.content).strip()
            query = canonical if len(canonical.split()) <= 8 else message.content
        result = await search_products_tool(context.tool_context(), query, None, None, 6)
        payload = result.model_dump(mode="json")
        ui = self._product_selector(message, [("search_products", payload)], "PRODUCT_DISCOVERY")
        if not ui:
            return GroundedAgentResponse(
                answer="Mình chưa tìm thấy sản phẩm còn hàng phù hợp. Bạn cho mình tên sản phẩm, hãng hoặc khoảng giá cụ thể hơn nhé.",
                confidence=0.8,
                intent="PRODUCT_DISCOVERY",
                goal="FIND_PRODUCT",
                resolved_context={"activeIntent": "PRODUCT_DISCOVERY", "productQuery": query},
                tool_calls=[ToolExecutionSummary(name="search_products", status=result.status)],
            )
        return GroundedAgentResponse(
            answer="Mình đã tìm các sản phẩm còn hàng phù hợp. Bạn chọn một mẫu để tiếp tục nhé.",
            confidence=1,
            intent="PRODUCT_DISCOVERY",
            goal="CREATE_ORDER",
            resolved_context={"activeIntent": "PRODUCT_DISCOVERY", "productQuery": query},
            collected_slots={"productQuery": query},
            missing_slots=["productId", "quantity", "addressId", "paymentMethod"],
            tool_calls=[ToolExecutionSummary(name="search_products", status=result.status)],
            ui=ui,
            conversation_state="AWAITING_INPUT",
        )

    @staticmethod
    async def _load_runtime_context(message: IncomingMessage) -> SupportRuntimeContext:
        profile: dict[str, Any] = {}
        conversation: dict[str, Any] = {"memory": {}, "facts": [], "openTickets": []}
        incidents: list[dict[str, Any]] = []
        if message.customer_id:
            profile_result, conversation, incidents = await asyncio.gather(
                repository.customer_profile(message.customer_id),
                repository.conversation_context(message.conversation_id, message.customer_id),
                repository.active_incidents(),
            )
            profile = profile_result or {}
        return SupportRuntimeContext(
            customer_id=message.customer_id,
            actor_role=message.actor_role,
            locale=message.locale,
            channel=message.channel,
            page_context=message.page_context or {},
            customer_profile=profile,
            conversation_memory=conversation.get("memory") or {},
            memory_facts=conversation.get("facts") or [],
            open_tickets=conversation.get("openTickets") or [],
            active_incidents=incidents,
            loaded_at=datetime.utcnow().isoformat(),
        )

    async def resume_order_intent(self, intent: str, message: IncomingMessage, order_id: str) -> GroundedAgentResponse:
        message.page_context = {**(message.page_context or {}), "orderId": order_id, "resumeIntent": intent}
        return await self.run(message)

    def _convert(self, message: IncomingMessage, result: dict[str, Any]) -> GroundedAgentResponse:
        all_messages = result.get("messages", [])
        messages = self._current_turn_messages(all_messages)
        output = result.get("structured_response")
        if not isinstance(output, SupportAgentOutput):
            output = SupportAgentOutput(answer=self._last_answer(messages), confidence=0.5)
        tool_calls, tool_payloads = self._tool_results(messages)
        output.intent = self._infer_intent(output.intent, tool_payloads, tool_calls)
        output.intent = self._reconcile_text_intent(message, output.intent)
        self._infer_requested_action(message, output, tool_payloads)
        ui = self._order_selector(message, tool_payloads, output.intent)
        if not ui:
            ui = self._product_selector(message, tool_payloads, output.intent)
            if ui:
                output.intent = "PRODUCT_DISCOVERY"
                output.answer = "Mình đã tìm các sản phẩm còn hàng phù hợp. Bạn chọn một mẫu để tiếp tục chọn số lượng, địa chỉ và thanh toán nhé."
        if not ui and not normalize_order_id(message.content, message.page_context) and not self._historical_selected_order(all_messages):
            historical_calls, historical_payloads = self._tool_results(all_messages)
            pending_intent = self._infer_intent(output.intent, historical_payloads, historical_calls)
            ui = self._order_selector(message, historical_payloads, pending_intent)
            if ui:
                output.intent = pending_intent
        if ui and ui[0].type == "ORDER_SELECTOR":
            output.answer = "Mình đã kiểm tra các đơn phù hợp trong tài khoản. Bạn chọn đúng đơn bên dưới để mình tiếp tục nhé."
        clarification = None
        collected_slots: dict[str, Any] = {}
        missing_slots: list[str] = []
        if not ui:
            component, clarification, collected_slots = self._clarification_ui(message, all_messages, output.intent, tool_payloads)
            if component:
                ui.append(component)
                missing_slots = [clarification.field] if clarification else []
                output.answer = clarification.question if clarification else output.answer
        if output.requested_action != "NONE" and output.requested_order_id:
            confirmation = self._confirmation(message, output)
            if confirmation:
                ui.append(confirmation)
                output.answer = self._confirmation_answer(output, tool_payloads)
        citations = [
            {
                "document_id": item.document_id,
                "title": item.title,
                "section": item.section,
                "version": item.version,
                "effective_from": item.effective_from,
                "public_url": item.public_url,
            }
            for item in output.citations
        ]
        evidence_citations = self._citations_from_tools(tool_payloads)
        citations = list({(item["document_id"], item["version"]): item for item in [*evidence_citations, *citations]}.values())[:4]
        return GroundedAgentResponse(
            answer=self._sanitize_language(output.answer),
            confidence=output.confidence,
            intent=output.intent,
            goal=output.intent,
            collected_slots=collected_slots,
            missing_slots=missing_slots,
            clarification=clarification,
            resolution_status="HANDOFF" if output.requires_human else "NEEDS_INPUT" if clarification else "READY_FOR_CONFIRMATION" if ui else "RESOLVED",
            next_best_action=clarification.question if clarification else None,
            citations=citations,
            tool_calls=tool_calls,
            ui=ui,
            requires_human=output.requires_human,
            escalation_reason=output.escalation_reason,
            conversation_state="AWAITING_INPUT" if ui else "ANSWERED",
            review_status="PASSED",
        )

    @staticmethod
    def _input_content(message: IncomingMessage) -> str:
        page_context = message.page_context or {}
        order_id = str(page_context.get("orderId") or "").strip()
        resume_intent = str(page_context.get("resumeIntent") or "").strip()
        semantic_route = page_context.get("semanticRoute") if isinstance(page_context.get("semanticRoute"), dict) else {}
        semantic_plan = page_context.get("semanticPlan") if isinstance(page_context.get("semanticPlan"), dict) else {}
        semantic_context = ""
        if semantic_route:
            semantic_context = (
                f"\nsemantic_intent={semantic_route.get('primary_intent', '')}"
                f"\ncanonical_request={semantic_route.get('proposition', '')}"
                f"\nrequired_tools={json.dumps(semantic_plan.get('required_tools', []), ensure_ascii=False)}"
            )
        attachments = page_context.get("attachments") if isinstance(page_context.get("attachments"), list) else []
        attachment_context = ""
        if attachments:
            evidence = [{
                "fileName": item.get("fileName"),
                "mimeType": item.get("mimeType"),
                "analysis": item.get("analysis"),
            } for item in attachments[:5] if isinstance(item, dict)]
            attachment_context = f"\nimage_evidence={json.dumps(evidence, ensure_ascii=False, default=str)}"
        clarification = page_context.get("clarification") if isinstance(page_context.get("clarification"), dict) else {}
        clarification_text = ""
        if clarification:
            clarification_text = f"\nclarification_field={clarification.get('field', '')}\nclarification_value={clarification.get('value', '')}"
        if order_id:
            return f"Người dùng đã chọn đơn {order_id}. Tiếp tục xử lý yêu cầu với đúng đơn này.\nYêu cầu hiện tại: {message.content}\n\n[TRUSTED_BACKEND_CONTEXT]\nselected_order_id={order_id}\nresume_intent={resume_intent}{clarification_text}{attachment_context}{semantic_context}"
        if attachment_context:
            return f"{message.content}\n\n[TRUSTED_BACKEND_CONTEXT]{attachment_context}{semantic_context}\nDùng image_evidence để trả lời về ảnh. Không khẳng định điều nằm ngoài observations/OCR; yêu cầu thêm ảnh nếu missing_evidence còn thiếu."
        if semantic_context:
            return f"{message.content}\n\n[TRUSTED_BACKEND_CONTEXT]{semantic_context}\nTuân theo semantic_intent. Gọi required_tools khi cần dữ liệu; không chuyển sang hồ sơ, KB hoặc intent khác nếu người dùng không yêu cầu."
        return message.content

    @staticmethod
    def _current_turn_messages(messages: list[Any]) -> list[Any]:
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                return messages[index:]
        return messages

    @staticmethod
    def _infer_intent(current: str, payloads: list[tuple[str, dict[str, Any]]], calls: list[ToolExecutionSummary]) -> str:
        names = {item.name for item in calls}
        if "get_order_summary" in names:
            return "ACCOUNT_ORDERS"
        for name, payload in reversed(payloads):
            if name == "find_eligible_orders":
                goal = str((payload.get("data") or {}).get("goal") or "")
                return {
                    "CANCELLABLE": "ORDER_CANCELLATION",
                    "IN_TRANSIT": "ORDER_TRACKING",
                    "PAYMENT_RELEVANT": "PAYMENT_STATUS",
                    "REFUND_RELEVANT": "REFUND_STATUS",
                    "RETURNABLE": "RETURN_ELIGIBILITY",
                }.get(goal, current)
        for tool_name, intent in (
            ("check_return_eligibility", "RETURN_ELIGIBILITY"),
            ("get_shipping_status", "ORDER_TRACKING"),
            ("get_payment_status", "PAYMENT_STATUS"),
            ("get_refund_status", "REFUND_STATUS"),
        ):
            if tool_name in names:
                return intent
        return current

    @staticmethod
    def _reconcile_text_intent(message: IncomingMessage, current: str) -> str:
        semantic_route = (message.page_context or {}).get("semanticRoute")
        if isinstance(semantic_route, dict):
            routed = str(semantic_route.get("primary_intent") or "")
            confidence = float(semantic_route.get("confidence") or 0)
            if routed and routed != "KNOWLEDGE" and confidence >= 0.55:
                return routed
        resume_intent = str((message.page_context or {}).get("resumeIntent") or "")
        if resume_intent in {
            "ORDER_CANCELLATION",
            "ORDER_TRACKING",
            "PAYMENT_STATUS",
            "REFUND_STATUS",
            "RETURN_ELIGIBILITY",
        }:
            return resume_intent
        if current not in {"KNOWLEDGE", "SOCIAL"}:
            return current
        inferred = classify(message.content)
        if inferred == "RETURN_POLICY" and message.customer_id:
            return "RETURN_ELIGIBILITY"
        if inferred == "SHIPPING_POLICY" and message.customer_id:
            return "ORDER_TRACKING"
        if inferred == "REFUND_POLICY" and message.customer_id:
            return "REFUND_STATUS"
        if inferred == "PAYMENT_POLICY" and message.customer_id:
            return "PAYMENT_STATUS"
        return inferred if inferred != "KNOWLEDGE" else current

    @staticmethod
    def _product_selector(message: IncomingMessage, payloads: list[tuple[str, dict[str, Any]]], intent: str) -> list[AgentUiComponent]:
        if intent != "PRODUCT_DISCOVERY":
            return []
        for name, payload in reversed(payloads):
            if name != "search_products" or str(payload.get("status")) != "SUCCESS":
                continue
            products = ((payload.get("data") or {}).get("products") or [])
            options = [
                AgentChoice(
                    id=str(product.get("id")),
                    label=str(product.get("name") or product.get("id")),
                    description=f"{format_money(float(product.get('price') or 0))} · còn {int(product.get('stock') or 0)} sản phẩm",
                    value={"productId": str(product.get("id"))},
                )
                for product in products[:6]
                if product.get("id") and int(product.get("stock") or 0) > 0
            ]
            if not options:
                return []
            token, expires_at = create_confirmation_token({
                "action": "SELECT_PRODUCT_FOR_PURCHASE",
                "customerId": message.customer_id,
                "conversationId": message.conversation_id,
                "allowedProductIds": [option.id for option in options],
            })
            return [AgentUiComponent(
                type="PRODUCT_SELECTOR",
                id=f"product-selector-{message.message_id}",
                title="Chọn sản phẩm",
                description="Chọn đúng mẫu bạn muốn mua.",
                options=options,
                bindings=[VerifiedDataBinding(type="PRODUCT", reference_id=option.id) for option in options],
                continuation_token=token,
                expires_at=expires_at,
            )]
        return []

    @staticmethod
    def _historical_selected_order(messages: list[Any]) -> str | None:
        for item in reversed(messages):
            if not isinstance(item, HumanMessage) or not isinstance(item.content, str):
                continue
            match = re.search(r"selected_order_id=(ORD-[A-Z0-9]+)", item.content, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    @staticmethod
    def _sanitize_language(answer: str) -> str:
        words = answer.split()
        cleaned: list[str] = []
        for word in words:
            foreign_letter = any(
                unicodedata.category(character).startswith("L") and "LATIN" not in unicodedata.name(character, "")
                for character in word
            )
            if not foreign_letter:
                cleaned.append(word)
        return " ".join(cleaned).strip()

    @staticmethod
    def _infer_requested_action(message: IncomingMessage, output: SupportAgentOutput, payloads: list[tuple[str, dict[str, Any]]]) -> None:
        if output.requested_action != "NONE":
            return
        text = normalize_support_text(message.content)
        if not any(term in text for term in ("hủy", "không muốn mua", "dừng giao")):
            return
        order_id = normalize_order_id(message.content, message.page_context)
        if not order_id:
            return
        for name, payload in reversed(payloads):
            if name != "get_order_details" or str(payload.get("status")) != "SUCCESS":
                continue
            data = payload.get("data") or {}
            if str(data.get("id") or order_id) == order_id and str(data.get("status")) in {"PENDING", "CONFIRMED", "PROCESSING"}:
                output.requested_action = "CANCEL_ORDER"
                output.requested_order_id = order_id
                output.intent = "ORDER_CANCELLATION"
            return

    @staticmethod
    def _last_answer(messages: list[Any]) -> str:
        for item in reversed(messages):
            if isinstance(item, AIMessage) and item.content:
                return item.content if isinstance(item.content, str) else json.dumps(item.content, ensure_ascii=False)
        return "Mình chưa thể hoàn tất yêu cầu này. Bạn thử diễn đạt lại ngắn gọn hơn nhé."

    @staticmethod
    def _tool_results(messages: list[Any]) -> tuple[list[ToolExecutionSummary], list[tuple[str, dict[str, Any]]]]:
        calls: list[ToolExecutionSummary] = []
        payloads: list[tuple[str, dict[str, Any]]] = []
        for item in messages:
            if not isinstance(item, ToolMessage):
                continue
            try:
                payload = json.loads(item.content) if isinstance(item.content, str) else item.content
            except (json.JSONDecodeError, TypeError):
                payload = {}
            status_value = str(payload.get("status") or "FAILED") if isinstance(payload, dict) else "FAILED"
            status = ToolStatus(status_value) if status_value in ToolStatus._value2member_map_ else ToolStatus.FAILED
            calls.append(ToolExecutionSummary(name=item.name or "unknown_tool", status=status, reference_id=payload.get("reference_id") if isinstance(payload, dict) else None))
            if isinstance(payload, dict):
                payloads.append((item.name or "unknown_tool", payload))
        return calls, payloads

    @staticmethod
    def _citations_from_tools(payloads: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for name, payload in payloads:
            if name != "search_knowledge" or str(payload.get("status")) != "SUCCESS":
                continue
            for item in ((payload.get("data") or {}).get("results") or []):
                if not isinstance(item, dict) or not item.get("document_id") or not item.get("semantic_version"):
                    continue
                effective_from = str(item.get("effective_from") or "").split("T", 1)[0]
                citations.append({
                    "document_id": str(item["document_id"]),
                    "title": str(item.get("title") or "Tài liệu hỗ trợ"),
                    "section": str(item.get("section") or "Nội dung liên quan"),
                    "version": str(item["semantic_version"]),
                    "effective_from": effective_from,
                    "public_url": item.get("public_url"),
                    "snippet": str(item.get("content") or "")[:500] or None,
                    "score": float(item.get("score") or 0),
                })
        return citations

    @staticmethod
    async def _ensure_grounded_citations(message: IncomingMessage, response: GroundedAgentResponse) -> GroundedAgentResponse:
        if response.citations or response.requires_human or response.intent not in {None, "KNOWLEDGE", "RETURN_POLICY", "REFUND_POLICY", "PAYMENT_POLICY", "SHIPPING_POLICY", "VOUCHER", "PRIVACY", "ACCOUNT_SECURITY", "TECHNICAL_SUPPORT"}:
            return response
        results = await retrieve(RetrievalRequest(query=message.content, locale=message.locale, visibility="CUSTOMER_AUTHENTICATED", limit=4))
        if not results:
            return response
        response.citations = [Citation(document_id=item.document_id, title=item.title, section=item.section, version=item.semantic_version, effective_from=item.effective_from.date(), public_url=item.public_url, snippet=item.content[:500], score=item.score) for item in results if item.public_url][:4]
        if response.citations and not any(call.name == "search_knowledge" for call in response.tool_calls):
            response.tool_calls.append(ToolExecutionSummary(name="search_knowledge", status=ToolStatus.SUCCESS))
        return response

    @staticmethod
    def _order_selector(message: IncomingMessage, payloads: list[tuple[str, dict[str, Any]]], intent: str) -> list[AgentUiComponent]:
        if normalize_order_id(message.content, message.page_context):
            return []
        for name, payload in reversed(payloads):
            if name not in {"find_eligible_orders", "get_recent_orders"}:
                continue
            orders = ((payload.get("data") or {}).get("orders") or [])
            if len(orders) <= 1:
                return []
            options = [AgentChoice(id=str(order["id"]), label=str(order["id"]), description=f"{STATUS_LABELS.get(str(order.get('status')), str(order.get('status')))} · {format_money(order.get('totalAmount'), str(order.get('currency') or 'VND'))}", value={"orderId": str(order["id"])}) for order in orders[:8]]
            token, expires_at = create_confirmation_token({"action": "SELECT_ORDER", "resumeIntent": intent, "originalMessage": message.content, "customerId": message.customer_id, "conversationId": message.conversation_id, "allowedOrderIds": [option.id for option in options]})
            return [AgentUiComponent(type="ORDER_SELECTOR", id=f"framework-order-selector-{message.message_id}", title="Chọn đơn hàng", description="Chọn một đơn để mình kiểm tra thông tin mới nhất.", options=options, bindings=[VerifiedDataBinding(type="ORDER", reference_id=option.id) for option in options], continuation_token=token, expires_at=expires_at)]
        return []

    @classmethod
    def _clarification_ui(
        cls,
        message: IncomingMessage,
        messages: list[Any],
        intent: str,
        payloads: list[tuple[str, dict[str, Any]]],
    ) -> tuple[AgentUiComponent | None, ClarificationRequest | None, dict[str, Any]]:
        if intent != "RETURN_ELIGIBILITY" or any(name == "check_return_eligibility" for name, _ in payloads):
            return None, None, {}
        order_id = normalize_order_id(message.content, message.page_context) or cls._historical_selected_order(messages)
        if not order_id:
            return None, None, {}
        reason_code = cls._return_reason(message, messages)
        if reason_code:
            return None, None, {"orderId": order_id, "returnReason": reason_code}
        options = [
            AgentChoice(id=code, label=label, description=description, value={"returnReason": code, "orderId": order_id})
            for code, (label, description) in cls.RETURN_REASONS.items()
        ]
        question = f"Bạn muốn trả đơn {order_id} vì lý do nào? Mình cần lý do để kiểm tra đúng điều kiện áp dụng."
        clarification = ClarificationRequest(
            reason="MISSING_REQUIRED_FIELD",
            field="returnReason",
            question=question,
            ui_type="SINGLE_CHOICE",
            suggested_options=[option.label for option in options],
        )
        token, expires_at = create_confirmation_token({
            "action": "PROVIDE_CLARIFICATION",
            "field": "returnReason",
            "customerId": message.customer_id,
            "conversationId": message.conversation_id,
            "orderId": order_id,
            "resumeIntent": intent,
            "originalMessage": message.content,
            "allowedValues": list(cls.RETURN_REASONS),
        })
        component = AgentUiComponent(
            type="SINGLE_CHOICE",
            id=f"clarify-return-reason-{message.message_id}",
            title="Lý do trả hàng",
            description="Chọn lý do gần đúng nhất. Bạn vẫn có thể mô tả thêm bằng tin nhắn.",
            options=options,
            bindings=[VerifiedDataBinding(type="ORDER", reference_id=order_id)],
            continuation_token=token,
            expires_at=expires_at,
        )
        return component, clarification, {"orderId": order_id}

    @classmethod
    def _return_reason(cls, message: IncomingMessage, messages: list[Any]) -> str | None:
        page_context = message.page_context or {}
        explicit = str(page_context.get("returnReason") or ((page_context.get("clarification") or {}).get("value") if isinstance(page_context.get("clarification"), dict) else ""))
        if explicit in cls.RETURN_REASONS:
            return explicit
        text_parts = [message.content]
        text_parts.extend(item.content for item in messages[-8:] if isinstance(item, HumanMessage) and isinstance(item.content, str))
        text = normalize_support_text(" ".join(text_parts))
        patterns = {
            "DAMAGED": ("hư", "hỏng", "bể", "vỡ", "móp", "không hoạt động", "lỗi"),
            "WRONG_ITEM": ("giao sai", "sai sản phẩm", "sai mẫu", "sai màu", "sai loại"),
            "MISSING_ITEM": ("thiếu hàng", "thiếu sản phẩm", "thiếu món", "thiếu số lượng"),
            "NOT_AS_DESCRIBED": ("không đúng mô tả", "khác mô tả", "không giống hình"),
            "CHANGE_OF_MIND": ("đổi ý", "không còn nhu cầu", "không muốn mua", "không thích"),
        }
        for code, terms in patterns.items():
            if any(term in text for term in terms):
                return code
        return None

    @staticmethod
    def _confirmation(message: IncomingMessage, output: SupportAgentOutput) -> AgentUiComponent | None:
        if output.requested_action != "CANCEL_ORDER":
            return None
        token, expires_at = create_confirmation_token({"action": "CANCEL_ORDER", "tool": "cancel_order", "customerId": message.customer_id, "conversationId": message.conversation_id, "orderId": output.requested_order_id, "reason": "CUSTOMER_REQUEST"})
        return AgentUiComponent(type="CONFIRMATION", id=f"framework-confirm-cancel-{output.requested_order_id}", title=f"Hủy đơn {output.requested_order_id}?", description="Đơn chỉ được hủy sau khi bạn xác nhận.", confirm_label="Đồng ý hủy", cancel_label="Không hủy", bindings=[VerifiedDataBinding(type="ORDER", reference_id=output.requested_order_id)], continuation_token=token, expires_at=expires_at)

    @staticmethod
    def _confirmation_answer(output: SupportAgentOutput, payloads: list[tuple[str, dict[str, Any]]]) -> str:
        for name, payload in reversed(payloads):
            if name != "get_order_details" or str(payload.get("status")) != "SUCCESS":
                continue
            data = payload.get("data") or {}
            status = STATUS_LABELS.get(str(data.get("status")), str(data.get("status") or "đang được xử lý"))
            return f"Mình vừa kiểm tra đơn {output.requested_order_id}: hiện {status} và vẫn có thể gửi yêu cầu hủy. Đơn chưa bị hủy; bạn bấm “Đồng ý hủy” bên dưới nếu muốn tiếp tục."
        return f"Đơn {output.requested_order_id} chưa bị thay đổi. Bạn bấm nút xác nhận bên dưới nếu muốn tiếp tục."
