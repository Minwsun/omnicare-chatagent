import unittest

from app.contracts import AgentChoice, AgentUiComponent
from app.omnicare_agent.confirmation import create_confirmation_token, verify_confirmation_token


class InteractionTests(unittest.TestCase):
    def test_all_ui_primitives_validate(self):
        types = ["CONFIRMATION", "SINGLE_CHOICE", "MULTI_CHOICE", "ORDER_SELECTOR", "PRODUCT_SELECTOR", "QUANTITY_SELECTOR", "ADDRESS_SELECTOR", "PAYMENT_METHOD_SELECTOR", "CHECKOUT_SUMMARY", "DATE_TIME_PICKER", "TEXT_INPUT", "TEXTAREA", "FILE_UPLOAD", "EVIDENCE_CHECKLIST", "SUMMARY_CARD", "ACTION_RESULT"]
        for component_type in types:
            component = AgentUiComponent(type=component_type, id=component_type.lower(), options=[AgentChoice(id="one", label="Một")])
            self.assertEqual(component.schema_version, "1.0")

    def test_confirmation_token_detects_tampering(self):
        token, _ = create_confirmation_token({"action": "SELECT_ORDER", "resumeIntent": "ORDER_TRACKING", "customerId": "customer_001", "conversationId": "conversation", "allowedOrderIds": ["ORD-1"]})
        self.assertEqual(verify_confirmation_token(token)["allowedOrderIds"], ["ORD-1"])
        with self.assertRaises(ValueError):
            verify_confirmation_token(token[:-1] + ("a" if token[-1] != "a" else "b"))


if __name__ == "__main__":
    unittest.main()
