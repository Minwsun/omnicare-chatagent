import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.contracts import RetrievalRequest
from app.retrieval import retrieve


class FakeHybridStore:
    row = {
        "document_id": "doc-1",
        "version_id": "version-1",
        "chunk_id": "chunk-1",
        "document_type": "POLICY",
        "title": "Chính sách trả hàng",
        "section": "Điều kiện",
        "content": "Khách hàng được gửi yêu cầu trả hàng khi sản phẩm sai mô tả.",
        "semantic_version": "1.0.0",
        "authority_level": 100,
        "public_url": "/help/chinh-sach-tra-hang",
        "effective_from": datetime.now(timezone.utc),
        "parent_summary": "Quy định tổng quát về điều kiện và bằng chứng trả hàng.",
        "score": 0.8,
    }

    async def search_knowledge(self, query, locale, limit, visibility):
        return [dict(self.row)]

    async def search_knowledge_vector(self, embedding, locale, limit, visibility):
        return [dict(self.row)]


class HybridRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_rrf_merges_channels_and_preserves_parent_summary(self):
        with patch("app.retrieval.embed_texts", return_value=[[0.0] * 1536]):
            results = await retrieve(RetrievalRequest(query="điều kiện trả hàng", profile="RETURN_POLICY"), FakeHybridStore())
        self.assertEqual(len(results), 1)
        self.assertEqual(set(results[0].retrieval_channels), {"FULL_TEXT", "VECTOR"})
        self.assertIn("Quy định tổng quát", results[0].parent_summary)
        self.assertIn("rrf", results[0].score_breakdown)

    async def test_profile_prefers_topically_named_sources(self):
        store = FakeHybridStore()
        irrelevant = {**store.row, "document_id": "doc-2", "version_id": "version-2", "chunk_id": "chunk-2", "title": "Điều khoản giao nhận", "section": "Vận chuyển", "authority_level": 100}

        async def text_search(query, locale, limit, visibility):
            return [irrelevant, dict(store.row)]

        store.search_knowledge = text_search
        results = await retrieve(RetrievalRequest(query="điều kiện trả hàng", profile="RETURN_POLICY"), store)
        self.assertTrue(results)
        self.assertTrue(all("trả hàng" in result.title.casefold() for result in results))


if __name__ == "__main__":
    unittest.main()
