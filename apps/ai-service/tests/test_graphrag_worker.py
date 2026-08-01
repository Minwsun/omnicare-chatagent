import unittest

from app.embeddings import vector_literal
from app.graphrag_worker import split_sections


class KnowledgeIndexWorkerTests(unittest.TestCase):
    def test_splits_large_document_without_losing_tail(self):
        content = "# Phần một\n" + "nội dung " * 500 + "\n# Phần hai\n" + "quy định cuối " * 500
        chunks = split_sections("Tài liệu", content)
        self.assertGreater(len(chunks), 2)
        self.assertIn("quy định cuối", chunks[-1][1])

    def test_vector_literal_uses_pgvector_format(self):
        self.assertEqual(vector_literal([0.25, -0.5]), "[0.25000000,-0.50000000]")


if __name__ == "__main__":
    unittest.main()
