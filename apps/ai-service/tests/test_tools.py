import unittest
from datetime import datetime, timezone

from app.contracts import ToolContext, ToolStatus
from app.tools import find_eligible_orders, get_order_details, get_order_summary, get_payment_status


class FakeRepository:
    async def order_details(self, customer_id, order_id):
        if customer_id == "cus_demo_001" and order_id == "ORD-1001":
            return {"id": order_id, "status": "OUT_FOR_DELIVERY", "updatedAt": datetime.now(timezone.utc)}
        return None

    async def payment_status(self, customer_id, order_id):
        return {"id": "pay_1001", "status": "AUTHORIZED", "maskedReference": "PAY-***1001", "observedAt": datetime.now(timezone.utc)}

    async def order_summary(self, customer_id):
        return {"total": 7, "byStatus": {"DELIVERED": 4, "PROCESSING": 3}}

    async def orders_by_status(self, customer_id, statuses, limit=8):
        return [{"id": "ORD-1001", "status": statuses[0], "totalAmount": 100000, "currency": "VND"}]


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_identity(self):
        result = await get_order_details(ToolContext(request_id="1", conversation_id="1"), "ORD-1001", FakeRepository())
        self.assertEqual(result.status, ToolStatus.FORBIDDEN)

    async def test_blocks_foreign_order(self):
        context = ToolContext(request_id="1", conversation_id="1", customer_id="cus_other")
        result = await get_order_details(context, "ORD-1001", FakeRepository())
        self.assertEqual(result.error_code, "ORDER_NOT_ACCESSIBLE")

    async def test_payment_requires_owned_order(self):
        context = ToolContext(request_id="1", conversation_id="1", customer_id="cus_demo_001")
        result = await get_payment_status(context, "ORD-1001", FakeRepository())
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.data["status"], "AUTHORIZED")

    async def test_order_summary_counts_all_owned_orders(self):
        context = ToolContext(request_id="1", conversation_id="1", customer_id="cus_demo_001")
        result = await get_order_summary(context, FakeRepository())
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.data["total"], 7)

    async def test_find_eligible_orders_uses_deterministic_status_filter(self):
        context = ToolContext(request_id="1", conversation_id="1", customer_id="cus_demo_001")
        result = await find_eligible_orders(context, "RETURNABLE", FakeRepository())
        self.assertEqual(result.status, ToolStatus.SUCCESS)
        self.assertEqual(result.data["orders"][0]["status"], "DELIVERED")


if __name__ == "__main__":
    unittest.main()
