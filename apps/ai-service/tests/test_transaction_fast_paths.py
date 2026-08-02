import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.contracts import IncomingMessage, ToolStatus
from app.omnicare_agent.context import TrustedContext
from app.omnicare_agent.framework_runtime import LangChainAgentRuntime


class TransactionFastPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivered_not_received_requires_handoff_without_eta(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="m1", content="ORD-1005 báo đã giao nhưng tôi chưa nhận", customer_id="customer_001", conversation_id="c1")
        result = SimpleNamespace(status=ToolStatus.SUCCESS, data={"status": "DELIVERED", "carrier": "OmniShip", "estimatedDelivery": "2026-08-02T00:00:00Z"})
        with patch("app.omnicare_agent.framework_runtime.get_shipping_status_impl", AsyncMock(return_value=result)):
            response = await runtime._run_order_tracking_fast(message, TrustedContext.from_message(message))
        self.assertTrue(response.requires_human)
        self.assertEqual(response.escalation_reason, "DELIVERED_NOT_RECEIVED")
        self.assertNotIn("Dự kiến giao", response.answer)

    async def test_payment_status_fast_path_uses_single_public_tool(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="m2", content="ORD-1019 thanh toán chưa", customer_id="customer_001", conversation_id="c2")
        result = SimpleNamespace(status=ToolStatus.SUCCESS, data={"status": "CAPTURED", "amount": 125000, "currency": "VND"})
        with patch("app.omnicare_agent.framework_runtime.get_payment_status_impl", AsyncMock(return_value=result)):
            response = await runtime._run_transaction_status_fast(message, TrustedContext.from_message(message), "PAYMENT_STATUS")
        self.assertEqual([call.name for call in response.tool_calls], ["get_payment_status"])
        self.assertNotIn("CAPTURED", response.answer)
        self.assertIn("ORD-1019", response.answer)

    async def test_refund_status_fast_path_hides_internal_status(self):
        runtime = object.__new__(LangChainAgentRuntime)
        message = IncomingMessage(message_id="m3", content="Hoàn tiền ORD-1005 tới đâu", customer_id="customer_001", conversation_id="c3")
        result = SimpleNamespace(status=ToolStatus.SUCCESS, data={"status": "PROCESSING", "amount": 99000})
        with patch("app.omnicare_agent.framework_runtime.get_refund_status_impl", AsyncMock(return_value=result)):
            response = await runtime._run_transaction_status_fast(message, TrustedContext.from_message(message), "REFUND_STATUS")
        self.assertEqual([call.name for call in response.tool_calls], ["get_refund_status"])
        self.assertNotIn("PROCESSING", response.answer)
        self.assertIn("hoàn tiền", response.answer)


if __name__ == "__main__":
    unittest.main()
