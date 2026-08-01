import asyncio
import unittest

from app.contracts import GroundedAgentResponse, ToolResult, ToolStatus
from app.omnicare_agent.executor import ToolExecutor
from app.omnicare_agent.reviewer import review_grounded_response
from app.omnicare_agent.registry import tool_registry
from app.omnicare_agent.capabilities import build_adaptive_plan
from app.omnicare_agent.skills import SkillDefinition, SkillRegistry, skill_registry


class HarnessV3Tests(unittest.IsolatedAsyncioTestCase):
    def test_adaptive_plan_combines_capabilities_without_duplicate_tools(self):
        plan = build_adaptive_plan(
            "Theo doi va kiem tra thanh toan don hang",
            ["ORDER_TRACKING", "PAYMENT_STATUS"],
            tool_registry,
            True,
        )
        tools = [tool for task in plan.tasks for tool in task.required_tools]
        self.assertLessEqual(len({task.specialist for task in plan.tasks}), plan.budget.max_specialists)
        self.assertLessEqual(len(tools), plan.budget.max_tool_calls)
        self.assertEqual(len(tools), len(set(tools)))

    def test_progressive_skills_only_load_for_selected_capability(self):
        skills = skill_registry.select({"RETURN"}, {"payment_refund"})
        self.assertEqual([item.name for item in skills], ["assess-return"])

    def test_learned_skill_cannot_grant_itself_unknown_tool(self):
        registry = SkillRegistry(())
        with self.assertRaisesRegex(ValueError, "SKILL_CANNOT_GRANT_TOOL_PERMISSION"):
            registry.propose(
                SkillDefinition("unsafe", "ORDER", "order", "unsafe", ("run",), ("delete_database",)),
                tool_registry.names(),
            )

    def test_skill_requires_evaluation_before_activation(self):
        registry = SkillRegistry(())
        registry.propose(
            SkillDefinition("learned-order", "ORDER", "order", "learned", ("verify",), ("get_order_details",)),
            tool_registry.names(),
        )
        candidate = registry.evaluate("learned-order", 19, 20)
        self.assertEqual(candidate.status, "CANARY")
        self.assertEqual(registry.promote("learned-order").status, "ACTIVE")

    async def test_executor_retries_transient_failure(self):
        executor = ToolExecutor(tool_registry)
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            return ToolResult(status=ToolStatus.UNAVAILABLE if attempts == 1 else ToolStatus.SUCCESS, data={"id": "ORD-1001"})

        record = await executor.execute("get_order_details", "CUSTOMER", True, operation)
        self.assertEqual(record.result.status, ToolStatus.SUCCESS)
        self.assertEqual(record.attempts, 2)

    async def test_executor_does_not_retry_business_failure(self):
        executor = ToolExecutor(tool_registry)
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            return ToolResult(status=ToolStatus.FORBIDDEN, error_code="ORDER_NOT_ACCESSIBLE")

        record = await executor.execute("get_order_details", "CUSTOMER", True, operation)
        self.assertEqual(record.result.status, ToolStatus.FORBIDDEN)
        self.assertEqual(attempts, 1)

    def test_reviewer_detects_wrong_order_id(self):
        response = GroundedAgentResponse(answer="Đơn ORD-9999 đang giao.", confidence=1, resolved_context={"orderId": "ORD-1001"})
        verdict = review_grounded_response(response)
        self.assertEqual(verdict.status, "FALLBACK")
        self.assertIn("ORDER_ID_MISMATCH", verdict.errors)

    def test_reviewer_accepts_matching_grounded_answer(self):
        response = GroundedAgentResponse(answer="Đơn ORD-1001 đang giao.", confidence=1, resolved_context={"orderId": "ORD-1001"})
        self.assertEqual(review_grounded_response(response).status, "PASSED")

    def test_reviewer_rejects_high_confidence_when_required_tool_not_successful(self):
        response = GroundedAgentResponse(
            answer="Đơn ORD-1001 đang được giao.", confidence=1,
            resolved_context={"orderId": "ORD-1001"},
            tool_calls=[{"name": "get_order_details", "status": "SUCCESS"}, {"name": "get_shipping_status", "status": "NOT_FOUND"}],
        )
        verdict = review_grounded_response(response, ("get_order_details", "get_shipping_status"))
        self.assertEqual(verdict.status, "FALLBACK")
        self.assertIn("POSITIVE_CLAIM_WITHOUT_TOOL_EVIDENCE", verdict.errors)

    def test_reviewer_accepts_not_found_as_negative_evidence(self):
        response = GroundedAgentResponse(
            answer="Đơn ORD-1001 đã hủy. Hệ thống không tìm thấy hành trình vận chuyển đang hoạt động.",
            confidence=1,
            resolved_context={"orderId": "ORD-1001"},
            tool_calls=[{"name": "get_order_details", "status": "SUCCESS"}, {"name": "get_shipping_status", "status": "NOT_FOUND"}],
        )
        verdict = review_grounded_response(response, ("get_order_details", "get_shipping_status"))
        self.assertEqual(verdict.status, "PASSED")


if __name__ == "__main__":
    unittest.main()
