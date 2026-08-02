import unittest
from unittest.mock import AsyncMock, patch

from app.contracts import GroundedAgentResponse, IncomingMessage
from app.main import apply_triage, ensure_handoff
from app.triage import triage_request


class TriageIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_apply_triage_forces_urgent_handoff(self):
        triage = triage_request("Có người lạ vào tài khoản của tôi", "customer_001")
        response = apply_triage(GroundedAgentResponse(answer="Hãy bảo vệ tài khoản ngay.", confidence=1), triage)
        self.assertTrue(response.requires_human)
        self.assertEqual(response.priority, "URGENT")
        self.assertEqual(response.resolution_status, "HANDOFF")

    async def test_duplicate_handoff_reuses_ticket(self):
        message = IncomingMessage(message_id="m1", content="Có người lạ vào tài khoản của tôi", customer_id="customer_001", conversation_id="c1")
        triage = triage_request(message.content, message.customer_id)
        response = apply_triage(GroundedAgentResponse(answer="Mình sẽ chuyển nhân viên hỗ trợ.", confidence=1), triage)
        with patch("app.main.repository.ticket_exists", AsyncMock(return_value=True)), patch("app.main.repository.create_handoff_ticket", AsyncMock(return_value="ticket")) as create_ticket:
            await ensure_handoff(message, response, triage)
        self.assertEqual(response.duplicate_of, f"TCK-{triage.request_fingerprint}")
        create_ticket.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
