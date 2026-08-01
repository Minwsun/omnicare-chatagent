import unittest

from app.omnicare_agent.advisor import CasePlan
from app.omnicare_agent.model_router import reviewer_profile, select_model_profile


class ModelRouterTests(unittest.TestCase):
    def test_simple_order_status_uses_fast_model(self):
        decision = select_model_profile("ORDER_TRACKING", CasePlan("ORDER_TRACKING", "SIMPLE"))
        self.assertEqual(decision.profile, "fast")

    def test_policy_and_high_risk_use_reasoning_model(self):
        policy = select_model_profile("PRIVACY", CasePlan("PRIVACY", "MODERATE"))
        risk = select_model_profile("FRAUD_WARNING", CasePlan("FRAUD_WARNING", "HIGH_RISK"), risk_flags=["FRAUD"])
        self.assertEqual(policy.profile, "reasoning")
        self.assertEqual(risk.profile, "reasoning")

    def test_low_confidence_multi_intent_escalates(self):
        decision = select_model_profile(
            "ORDER_TRACKING",
            CasePlan("ORDER_TRACKING", "MODERATE"),
            secondary_intents=["ORDER_CANCELLATION"],
            route_confidence=0.6,
        )
        self.assertEqual(decision.profile, "reasoning")

    def test_deterministic_review_does_not_call_reviewer_model(self):
        self.assertEqual(reviewer_profile(["ORDER_ID_MISMATCH"]).profile, "fast")
        self.assertEqual(reviewer_profile(["UNSUPPORTED_CLAIM"]).profile, "reviewer")


if __name__ == "__main__":
    unittest.main()
