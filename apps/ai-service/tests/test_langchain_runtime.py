import unittest

from langchain_core.messages import AIMessage

from app.omnicare_agent.framework_runtime import LangChainAgentRuntime
from app.tool_adapters import get_order_details, search_knowledge
from app.omnicare_agent.registry import tool_registry


class LangChainRuntimeTests(unittest.TestCase):
    def test_internal_model_limit_message_is_not_exposed(self):
        answer = LangChainAgentRuntime._last_answer([AIMessage(content="Model call limits exceeded: run limit (3/3)")])
        self.assertNotIn("Model call limits exceeded", answer)

    def test_transaction_tool_does_not_expose_customer_id(self):
        schema = get_order_details.args_schema.model_json_schema()
        self.assertEqual(set(schema["properties"]), {"order_id"})

    def test_knowledge_tool_has_bounded_limit(self):
        schema = search_knowledge.args_schema.model_json_schema()
        self.assertIn("query", schema["properties"])
        self.assertIn("limit", schema["properties"])

    def test_knowledge_tool_does_not_expose_visibility(self):
        schema = search_knowledge.args_schema.model_json_schema()
        self.assertNotIn("visibility", schema["properties"])

    def test_registry_contains_integrated_tool_suite(self):
        self.assertTrue({"get_order_details", "get_shipping_status", "get_payment_status", "check_return_eligibility", "search_knowledge", "cancel_order", "create_return_request", "create_refund", "create_shipping_investigation", "create_dispute"}.issubset(tool_registry.names()))

    def test_registry_has_unique_tool_names(self):
        self.assertEqual(len(tool_registry.names()), len(tool_registry.all_tools()))

    def test_high_risk_write_requires_approval(self):
        refund = tool_registry.specification("create_refund")
        self.assertEqual(refund.risk, "CRITICAL")
        self.assertEqual(refund.approval, "HUMAN_APPROVAL")
        decision = tool_registry.authorize("create_refund", "CUSTOMER", True)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.approval, "HUMAN_APPROVAL")

    def test_write_requires_verified_customer_context(self):
        decision = tool_registry.authorize("cancel_order", "CUSTOMER", False)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "CUSTOMER_CONTEXT_REQUIRED")


if __name__ == "__main__":
    unittest.main()
