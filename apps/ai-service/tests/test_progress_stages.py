import json
import unittest

from app.main import progress_event, tool_progress


class ProgressStageTests(unittest.TestCase):
    def test_maps_transaction_tools_to_customer_stages(self):
        self.assertEqual(tool_progress({"tools": ["get_order_details"]})[0], "CHECKING_ORDER")
        self.assertEqual(tool_progress({"tools": ["get_shipping_status"]})[0], "CHECKING_SHIPMENT")
        self.assertEqual(tool_progress({"tools": ["get_payment_status"]})[0], "CHECKING_PAYMENT")

    def test_maps_retrieval_tool_without_exposing_tool_name(self):
        stage, label = tool_progress({"tools": ["search_knowledge"]})
        self.assertEqual(stage, "SEARCHING_KNOWLEDGE")
        self.assertNotIn("search_knowledge", label)

    def test_progress_event_has_stable_contract(self):
        event = progress_event("REVIEWING", "Đang kiểm tra lại độ chính xác…")
        payload = json.loads(event.split("data: ", 1)[1])
        self.assertEqual(payload["stage"], "REVIEWING")
        self.assertEqual(payload["status"], "STARTED")
        self.assertIn("startedAt", payload)


if __name__ == "__main__":
    unittest.main()
