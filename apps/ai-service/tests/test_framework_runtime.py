import unittest

from langchain_core.messages import HumanMessage, ToolMessage

from app.contracts import IncomingMessage, ToolExecutionSummary, ToolStatus
from app.omnicare_agent.framework_runtime import LangChainAgentRuntime, SupportAgentOutput, SupportRuntimeContext


class FrameworkRuntimeTests(unittest.TestCase):
    def test_compact_runtime_context_caps_large_collections(self):
        context = SupportRuntimeContext(
            customer_id="customer_001",
            memory_facts=[{"key": str(index)} for index in range(12)],
            open_tickets=[{"id": str(index)} for index in range(5)],
            active_incidents=[{"id": str(index)} for index in range(5)],
            loaded_at="2026-07-31T00:00:00+00:00",
        )
        payload = context.compact_json()
        self.assertEqual(payload.count('"key"'), 8)
        self.assertEqual(payload.count('"id"'), 6)

    def test_infers_transaction_intent_from_verified_tool_goal(self):
        intent = LangChainAgentRuntime._infer_intent(
            "KNOWLEDGE",
            [("find_eligible_orders", {"status": "SUCCESS", "data": {"goal": "RETURNABLE", "orders": []}})],
            [ToolExecutionSummary(name="find_eligible_orders", status=ToolStatus.SUCCESS)],
        )
        self.assertEqual(intent, "RETURN_ELIGIBILITY")

    def test_builds_order_selector_from_verified_tool_result(self):
        message = IncomingMessage(message_id="message", content="trả hàng", customer_id="customer_001", conversation_id="conversation")
        ui = LangChainAgentRuntime._order_selector(message, [("find_eligible_orders", {
            "status": "SUCCESS",
            "data": {"goal": "RETURNABLE", "selectionRequired": True, "orders": [
                {"id": "ORD-1", "status": "DELIVERED", "totalAmount": 100000, "currency": "VND"},
                {"id": "ORD-2", "status": "DELIVERED", "totalAmount": 200000, "currency": "VND"},
            ]},
        })], "RETURN_ELIGIBILITY")
        self.assertEqual(ui[0].type, "ORDER_SELECTOR")
        self.assertEqual([option.id for option in ui[0].options], ["ORD-1", "ORD-2"])

    def test_builds_product_selector_from_runtime_data_not_query_literals(self):
        message = IncomingMessage(message_id="dynamic-product", content="giúp mình mua một thiết bị", customer_id="customer_001", conversation_id="conversation")
        ui = LangChainAgentRuntime._product_selector(message, [("search_products", {
            "status": "SUCCESS",
            "data": {"products": [
                {"id": "SKU-RANDOM-91", "name": "Thiết bị Alpha", "price": 1234567, "stock": 7},
                {"id": "SKU-RANDOM-37", "name": "Thiết bị Beta", "price": 7654321, "stock": 0},
            ]},
        })], "PRODUCT_DISCOVERY")
        self.assertEqual(len(ui), 1)
        self.assertEqual(ui[0].type, "PRODUCT_SELECTOR")
        self.assertEqual([option.id for option in ui[0].options], ["SKU-RANDOM-91"])

    def test_semantic_route_overrides_knowledge_for_commerce_paraphrase(self):
        message = IncomingMessage(
            message_id="semantic-commerce",
            content="lấy món vừa xem cho mình",
            customer_id="customer_001",
            conversation_id="conversation",
            page_context={"semanticRoute": {"primary_intent": "PRODUCT_DISCOVERY", "confidence": 0.91}},
        )
        self.assertEqual(LangChainAgentRuntime._reconcile_text_intent(message, "KNOWLEDGE"), "PRODUCT_DISCOVERY")

    def test_does_not_build_selector_when_order_is_already_known(self):
        message = IncomingMessage(message_id="message", content="hủy đơn ORD-1001", customer_id="customer_001", conversation_id="conversation")
        ui = LangChainAgentRuntime._order_selector(message, [("find_eligible_orders", {"status": "SUCCESS", "data": {"orders": [{"id": "ORD-1"}, {"id": "ORD-2"}]}})], "ORDER_CANCELLATION")
        self.assertEqual(ui, [])

    def test_injects_only_backend_selected_order_context(self):
        message = IncomingMessage(message_id="message", content="kiểm tra đơn này", customer_id="customer_001", conversation_id="conversation", page_context={"orderId": "ORD-1", "resumeIntent": "ORDER_TRACKING"})
        content = LangChainAgentRuntime._input_content(message)
        self.assertIn("selected_order_id=ORD-1", content)
        self.assertIn("resume_intent=ORDER_TRACKING", content)

    def test_infers_safe_cancel_confirmation_from_verified_order(self):
        message = IncomingMessage(message_id="message", content="tôi muốn hủy đơn ORD-1001", customer_id="customer_001", conversation_id="conversation")
        output = SupportAgentOutput(answer="Đơn có thể hủy.")
        LangChainAgentRuntime._infer_requested_action(message, output, [("get_order_details", {"status": "SUCCESS", "data": {"id": "ORD-1001", "status": "CONFIRMED"}})])
        self.assertEqual(output.requested_action, "CANCEL_ORDER")
        self.assertEqual(output.requested_order_id, "ORD-1001")

    def test_reconciles_logged_in_policy_question_to_transaction_intent(self):
        message = IncomingMessage(message_id="message", content="đơn này có trả hàng được không", customer_id="customer_001", conversation_id="conversation")
        self.assertEqual(LangChainAgentRuntime._reconcile_text_intent(message, "KNOWLEDGE"), "RETURN_ELIGIBILITY")

    def test_keeps_generic_return_question_as_policy(self):
        message = IncomingMessage(message_id="message", content="Hàng lỗi thì trả sao", customer_id="customer_001", conversation_id="conversation")
        self.assertEqual(LangChainAgentRuntime._reconcile_text_intent(message, "KNOWLEDGE"), "RETURN_POLICY")

    def test_trusted_resume_intent_survives_ambiguous_follow_up(self):
        message = IncomingMessage(
            message_id="message",
            content="kiểm tra đơn này",
            customer_id="customer_001",
            conversation_id="conversation",
            page_context={"orderId": "ORD-1001", "resumeIntent": "RETURN_ELIGIBILITY"},
        )
        self.assertEqual(LangChainAgentRuntime._reconcile_text_intent(message, "KNOWLEDGE"), "RETURN_ELIGIBILITY")

    def test_removes_non_latin_words_from_answer(self):
        self.assertEqual(LangChainAgentRuntime._sanitize_language("Đơn vẫn đang xử lý هنوز nhé"), "Đơn vẫn đang xử lý nhé")

    def test_replays_historical_order_selector_until_order_selected(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="current", content="tôi vẫn muốn trả hàng", customer_id="customer_001", conversation_id="conversation")
        result = {
            "messages": [
                HumanMessage(content="trả hàng"),
                ToolMessage(
                    content='{"status":"SUCCESS","data":{"goal":"RETURNABLE","selectionRequired":true,"orders":[{"id":"ORD-1","status":"DELIVERED","totalAmount":100000,"currency":"VND"},{"id":"ORD-2","status":"DELIVERED","totalAmount":200000,"currency":"VND"}]}}',
                    name="find_eligible_orders",
                    tool_call_id="tool-1",
                ),
                HumanMessage(content="tôi vẫn muốn trả hàng"),
            ],
            "structured_response": SupportAgentOutput(answer="Bạn cần chọn đơn.", intent="KNOWLEDGE"),
        }
        response = runtime._convert(message, result)
        self.assertEqual(response.intent, "RETURN_ELIGIBILITY")
        self.assertEqual(response.ui[0].type, "ORDER_SELECTOR")

    def test_historical_selected_order_prevents_stale_selector(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="current", content="kiểm tra tiếp", customer_id="customer_001", conversation_id="conversation")
        result = {
            "messages": [
                HumanMessage(content="trả hàng"),
                ToolMessage(
                    content='{"status":"SUCCESS","data":{"goal":"RETURNABLE","selectionRequired":true,"orders":[{"id":"ORD-1"},{"id":"ORD-2"}]}}',
                    name="find_eligible_orders",
                    tool_call_id="tool-1",
                ),
                HumanMessage(content="[TRUSTED_BACKEND_CONTEXT]\nselected_order_id=ORD-1\nresume_intent=RETURN_ELIGIBILITY"),
                HumanMessage(content="kiểm tra tiếp"),
            ],
            "structured_response": SupportAgentOutput(answer="Đang kiểm tra.", intent="RETURN_ELIGIBILITY"),
        }
        response = runtime._convert(message, result)
        self.assertNotIn("ORDER_SELECTOR", {component.type for component in response.ui})
        self.assertEqual(response.clarification.field, "returnReason")
        self.assertEqual(response.ui[0].bindings[0].reference_id, "ORD-1")

    def test_requests_return_reason_after_order_selection(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(
            message_id="current",
            content="đơn này có trả được không",
            customer_id="customer_001",
            conversation_id="conversation",
            page_context={"orderId": "ORD-1001", "resumeIntent": "RETURN_ELIGIBILITY"},
        )
        response = runtime._convert(message, {
            "messages": [HumanMessage(content=LangChainAgentRuntime._input_content(message))],
            "structured_response": SupportAgentOutput(answer="Cần biết lý do.", intent="RETURN_ELIGIBILITY"),
        })
        self.assertEqual(response.resolution_status, "NEEDS_INPUT")
        self.assertEqual(response.missing_slots, ["returnReason"])
        self.assertEqual(response.clarification.field, "returnReason")
        self.assertEqual(response.ui[0].type, "SINGLE_CHOICE")
        self.assertEqual({option.id for option in response.ui[0].options}, set(LangChainAgentRuntime.RETURN_REASONS))

    def test_does_not_repeat_return_reason_when_backend_supplies_slot(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(
            message_id="current",
            content="tiếp tục kiểm tra",
            customer_id="customer_001",
            conversation_id="conversation",
            page_context={"orderId": "ORD-1001", "resumeIntent": "RETURN_ELIGIBILITY", "returnReason": "DAMAGED"},
        )
        response = runtime._convert(message, {
            "messages": [HumanMessage(content=LangChainAgentRuntime._input_content(message))],
            "structured_response": SupportAgentOutput(answer="Đang kiểm tra.", intent="RETURN_ELIGIBILITY"),
        })
        self.assertEqual(response.ui, [])
        self.assertEqual(response.missing_slots, [])

    def test_builds_citation_from_verified_retrieval_tool(self):
        citations = LangChainAgentRuntime._citations_from_tools([("search_knowledge", {
            "status": "SUCCESS",
            "data": {"results": [{
                "document_id": "policy-1",
                "semantic_version": "2.1.0",
                "title": "Chính sách đổi trả",
                "section": "Điều kiện",
                "effective_from": "2026-01-01T00:00:00+00:00",
                "public_url": "/help/chinh-sach-doi-tra",
                "content": "Khách được gửi yêu cầu trong thời hạn áp dụng.",
                "score": 0.94,
            }]},
        })])
        self.assertEqual(citations[0]["document_id"], "policy-1")
        self.assertEqual(citations[0]["effective_from"], "2026-01-01")
        self.assertEqual(citations[0]["score"], 0.94)

    def test_foreign_order_result_requires_handoff(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="foreign", content="xem đơn ORD-OTHER", customer_id="customer_001", conversation_id="conversation")
        response = runtime._convert(message, {
            "messages": [
                HumanMessage(content="xem đơn ORD-OTHER"),
                ToolMessage(
                    content='{"status":"FORBIDDEN","error_code":"ORDER_NOT_ACCESSIBLE"}',
                    name="get_order_details",
                    tool_call_id="tool-foreign",
                ),
            ],
            "structured_response": SupportAgentOutput(answer="Không thể xác minh đơn hàng.", intent="ORDER_TRACKING"),
        })
        self.assertTrue(response.requires_human)
        self.assertEqual(response.escalation_reason, "ORDER_OWNERSHIP_VERIFICATION_FAILED")

    def test_human_request_intent_always_requires_handoff(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="human", content="cân fgapwj nhân viên", customer_id="customer_001", conversation_id="conversation")
        response = runtime._convert(message, {
            "messages": [HumanMessage(content=message.content)],
            "structured_response": SupportAgentOutput(answer="Đã ghi nhận.", intent="HUMAN_REQUEST", requires_human=False),
        })
        self.assertTrue(response.requires_human)
        self.assertEqual(response.escalation_reason, "CUSTOMER_REQUEST")
        self.assertEqual(response.resolution_status, "HANDOFF")


if __name__ == "__main__":
    unittest.main()
