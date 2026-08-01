import unittest

from app.contracts import GroundedAgentResponse, PendingAgentAction, ToolExecutionSummary, ToolStatus
from app.omnicare_agent.advisor import build_case_plan, enrich_advisor_response, review_response, validate_advisor_response


class AdvisorHarnessTests(unittest.TestCase):
    def test_adapts_complexity(self):
        self.assertEqual(build_case_plan("ORDER_TRACKING", "ORD-1003 đang ở đâu", "ORD-1003").complexity, "SIMPLE")
        self.assertEqual(build_case_plan("ORDER_TRACKING", "Đơn báo giao nhưng tôi chưa nhận", None).complexity, "COMPLEX")
        self.assertEqual(build_case_plan("ACCOUNT_SECURITY", "Tôi nhận OTP lạ", None).complexity, "HIGH_RISK")

    def test_builds_controlled_recommendation(self):
        plan = build_case_plan("ORDER_TRACKING", "ORD-1003 chưa nhận", "ORD-1003")
        response = GroundedAgentResponse(answer="Mở tra soát vận chuyển.", confidence=1, tool_calls=[ToolExecutionSummary(name="get_shipping_status", status=ToolStatus.SUCCESS)])
        enriched = enrich_advisor_response(response, plan)
        self.assertIsNotNone(enriched.recommendation)
        self.assertEqual(enriched.case_state, "RESOLVED")
        self.assertEqual(validate_advisor_response(enriched, plan), [])

    def test_critic_rejects_missing_required_evidence(self):
        plan = build_case_plan("PAYMENT_STATUS", "ORD-1019 thanh toán chưa", "ORD-1019")
        response = GroundedAgentResponse(answer="Đã thanh toán.", confidence=1)
        enriched = enrich_advisor_response(response, plan)
        self.assertIn("REQUIRED_EVIDENCE_MISSING", validate_advisor_response(enriched, plan))

    def test_response_critic_tracks_coverage_and_internal_terms(self):
        response = review_response("Đơn ở đâu và có hủy được không?", GroundedAgentResponse(answer="Evidence cho thấy đơn đang giao.", confidence=1))
        self.assertLess(response.quality.coverage_score, 1)
        self.assertNotIn("Evidence", response.answer)


if __name__ == "__main__":
    unittest.main()
