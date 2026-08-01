import unittest

from app.contracts import RetrievalRequest
from app.retrieval import build_query_plan, build_search_queries, compress_content, decompose_query, lexical_score, normalize_text, profile_matches


class RetrievalProfileTests(unittest.TestCase):
    def test_policy_compression_preserves_conditions_and_numbers(self):
        content = "Giới thiệu chương trình. Khách có thể trả hàng. Chỉ áp dụng trong vòng 7 ngày. Không áp dụng với hàng đã sử dụng. Nội dung quảng bá không liên quan."
        compressed, reason = compress_content("điều kiện trả hàng", content, "POLICY", ("trả hàng",))
        self.assertIn("7 ngày", compressed)
        self.assertIn("Không áp dụng", compressed)
        self.assertEqual(reason, "POLICY_SAFE_EXTRACT")

    def test_search_queries_include_discriminative_terms(self):
        request = RetrievalRequest(query="Theo chính sách mã quy tắc sao-lam-a547350f được xử lý thế nào")
        plan = build_query_plan(request)
        queries = build_search_queries(request, plan, ["chính", "sách", "quy", "tắc", "sao", "lam", "a547350f", "xử", "lý"], ())
        self.assertIn("a547350f", queries)

    def test_decomposes_multi_intent_without_overexpanding(self):
        self.assertEqual(decompose_query("ORD-1003 đang ở đâu và có hủy được không?"), ["ORD-1003 đang ở đâu", "có hủy được không"])

    def test_builds_ontology_plan_without_question_aliases(self):
        plan = build_query_plan(RetrievalRequest(query="Có dùng COD được không?", profile="PAYMENT_POLICY"))
        self.assertEqual(plan.intent, "PAYMENT_POLICY")
        self.assertIn("PAYMENT_METHOD", plan.concepts)

    def test_normalization_is_accent_insensitive(self):
        self.assertEqual(normalize_text("Trả hàng và hoàn tiền"), "tra hang va hoan tien")

    def test_profile_raises_relevant_content(self):
        row = {"title": "Thanh toán khi nhận hàng", "section": "COD", "content": "Hướng dẫn dùng COD"}
        relevant = lexical_score(["cod"], ("thanh toán", "cod"), row)
        irrelevant = lexical_score(["voucher"], ("mã giảm giá",), row)
        self.assertGreater(relevant, irrelevant)

    def test_profile_rejects_unrelated_document(self):
        row = {"title": "Điều khoản Shopee Live", "section": "Phạm vi", "content": "Quy định livestream cho người bán"}
        self.assertFalse(profile_matches(("thanh toán", "cod"), row))

    def test_multi_concept_return_query_requires_both_concepts(self):
        query = normalize_text("Điều kiện trả hàng và bằng chứng cần có")
        profile_terms = ("trả hàng", "hoàn tiền", "bằng chứng")
        matched_terms = tuple(term for term in profile_terms if normalize_text(term) in query)
        unrelated = normalize_text("Hướng dẫn hoàn tiền trả góp bằng thẻ tín dụng")
        relevant = normalize_text("Quy định trả hàng và bằng chứng ảnh hoặc video")
        self.assertEqual(len(matched_terms), 2)
        self.assertLess(sum(normalize_text(term) in unrelated for term in matched_terms), 2)
        self.assertEqual(sum(normalize_text(term) in relevant for term in matched_terms), 2)


if __name__ == "__main__":
    unittest.main()
