import unittest

from app.evaluation_v2 import EvaluationCase, grade_run, release_gate, validate_dataset


def case(**overrides):
    payload = {
        "id": "case-001", "cluster_id": "cluster-order", "split": "HOLDOUT",
        "category": "ORDER", "customer_id": "customer_001",
        "turns": [{"message": "Don ORD-1001 dang o dau?", "expected_active_order_id": "ORD-1001"}],
        "expected": {"intents": ["ORDER_TRACKING"], "required_tools": ["get_order_details"], "allowed_tools": ["get_order_details", "get_shipping_status"], "model_profile": "fast"},
    }
    payload.update(overrides)
    return EvaluationCase.model_validate(payload)


class EvaluationV2Tests(unittest.TestCase):
    def test_dataset_rejects_text_duplicates_and_cluster_split_leakage(self):
        first = case()
        second = case(id="case-002", split="DEVELOPMENT")
        report = validate_dataset([first, second])
        self.assertFalse(report["valid"])
        self.assertIn("DUPLICATE_TEXT", report["errors"])
        self.assertIn("CLUSTER_SPLIT_LEAKAGE", report["errors"])

    def test_grades_tool_context_and_model_profile(self):
        result = grade_run(case(), [{
            "answer": "Don dang van chuyen.", "intent": "ORDER_TRACKING",
            "toolCalls": [{"name": "get_order_details", "arguments": {"order_id": "ORD-1001"}}],
            "resolvedOrderId": "ORD-1001", "modelProfile": "fast",
        }])
        self.assertTrue(result["passed"])

    def test_detects_duplicate_and_forbidden_tool_calls(self):
        evaluated = case(expected={"forbidden_tools": ["cancel_order"], "max_tool_calls": 1})
        call = {"name": "cancel_order", "arguments": {"order_id": "ORD-1001"}}
        result = grade_run(evaluated, [{"answer": "Da huy.", "toolCalls": [call, call]}])
        self.assertIn("FORBIDDEN_TOOL_USED", result["errors"])
        self.assertIn("DUPLICATE_TOOL_CALL", result["errors"])
        self.assertIn("TOOL_BUDGET_EXCEEDED", result["errors"])

    def test_release_gate_blocks_safety_error(self):
        gate = release_gate([{"passed": True, "errors": []}, {"passed": False, "errors": ["FORBIDDEN_TOOL_USED"]}])
        self.assertFalse(gate["passed"])


if __name__ == "__main__":
    unittest.main()
