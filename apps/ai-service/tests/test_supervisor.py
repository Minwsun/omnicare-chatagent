import unittest

from app.omnicare_agent.runtime import classify, normalize_order_id, normalize_support_text
from app.omnicare_agent.supervisor import RouteDecision, SupervisorHarness


class StubSupervisorHarness(SupervisorHarness):
    async def _structured_route(self, content: str, heuristic: str) -> RouteDecision:
        return RouteDecision(
            primary_intent="ORDER_TRACKING",
            secondary_intents=["ORDER_CANCELLATION"],
            proposition=content,
            confidence=0.9,
            requires_structured_fallback=True,
        )


class SemanticStubSupervisorHarness(SupervisorHarness):
    async def _understand(self, state):
        return {
            "canonical_query": "tôi muốn trả đơn này",
            "semantic_intent": "RETURN_ELIGIBILITY",
            "semantic_confidence": 0.96,
            "semantic_entities": {},
            "semantic_ambiguities": [],
            "understanding_fallback": False,
        }


class SupervisorHarnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_transaction_route_avoids_fallback(self):
        from app.contracts import IncomingMessage

        harness = StubSupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="message", content="ORD-1003 đang ở đâu?", customer_id="customer_001",
            channel="WEB", conversation_id="conversation",
        ))
        self.assertEqual(result["route"].primary_intent, "ORDER_TRACKING")
        self.assertFalse(result["route"].requires_structured_fallback)
        self.assertEqual(result["plan"].required_tools, ("get_order_details", "get_shipping_status"))
        self.assertEqual(
            [task["specialist"] for task in result["adaptive_plan"]["tasks"]],
            ["order", "logistics"],
        )
        self.assertTrue(result["selected_skills"])

    async def test_multi_intent_uses_structured_fallback(self):
        from app.contracts import IncomingMessage

        harness = StubSupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="message", content="ORD-1003 đang ở đâu và có hủy được không?", customer_id="customer_001",
            channel="WEB", conversation_id="conversation",
        ))
        self.assertTrue(result["route"].requires_structured_fallback)

    async def test_missing_order_uses_preflight_tool_only(self):
        from app.contracts import IncomingMessage

        harness = SupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="missing-order", content="khi nào được giao?", customer_id="customer_001",
            channel="WEB", conversation_id="missing-order-conversation",
        ))
        self.assertEqual(result["route"].primary_intent, "ORDER_TRACKING")
        self.assertEqual(result["plan"].required_tools, ("find_eligible_orders",))

    async def test_follow_up_uses_active_order_context(self):
        from app.contracts import IncomingMessage

        harness = StubSupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="message", content="C\u00f2n thanh to\u00e1n th\u00ec sao?", customer_id="customer_001",
            channel="WEB", conversation_id="conversation-payment-follow-up",
            page_context={"memory": {"activeContext": {"orderId": "ORD-8743D67CB8"}}},
        ))
        self.assertEqual(result["order_id"], "ORD-8743D67CB8")
        self.assertEqual(result["route"].primary_intent, "PAYMENT_STATUS")
        self.assertTrue(result["tool_policy"]["get_payment_status"]["allowed"])

    async def test_typo_return_follow_up_keeps_active_order_and_changes_goal(self):
        from app.contracts import IncomingMessage

        harness = StubSupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="message-return-typo", content="tôi muốn tar đơn này", customer_id="customer_001",
            channel="WEB", conversation_id="conversation-return-typo",
            page_context={"memory": {"activeContext": {"orderId": "ORD-8743D67CB8", "activeIntent": "ORDER_TRACKING"}}},
        ))
        self.assertEqual(result["order_id"], "ORD-8743D67CB8")
        self.assertEqual(result["route"].primary_intent, "RETURN_ELIGIBILITY")
        self.assertIn("check_return_eligibility", result["tool_policy"])

    async def test_checkpoint_state_uses_json_payloads(self):
        from app.contracts import IncomingMessage

        harness = StubSupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="message-json", content="Xem ORD-1003", customer_id="customer_001",
            channel="WEB", conversation_id="conversation-json",
        ))
        self.assertIsInstance(result["risk_flags"], list)
        self.assertIsInstance(result["active_context"], dict)
        self.assertIsInstance(result["tool_policy"], dict)

    async def test_semantic_understanding_overrides_wrong_surface_form(self):
        from app.contracts import IncomingMessage

        harness = SemanticStubSupervisorHarness(classify, normalize_support_text, normalize_order_id)
        result = await harness.prepare(IncomingMessage(
            message_id="semantic-typo", content="toi muon taa don nay", customer_id="customer_001",
            channel="WEB", conversation_id="semantic-typo-conversation",
            page_context={"memory": {"activeContext": {"orderId": "ORD-8743D67CB8"}}},
        ))
        self.assertEqual(result["route"].primary_intent, "RETURN_ELIGIBILITY")
        self.assertEqual(result["route"].proposition, "tôi muốn trả đơn này")
        self.assertIn("check_return_eligibility", result["tool_policy"])


if __name__ == "__main__":
    unittest.main()
