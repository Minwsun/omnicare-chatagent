import asyncio
import unittest

from app.embeddings import vector_literal
from app.graphrag_worker import GraphRagWorker, split_sections


class KnowledgeIndexWorkerTests(unittest.TestCase):
    def test_splits_large_document_without_losing_tail(self):
        content = "# Phần một\n" + "nội dung " * 500 + "\n# Phần hai\n" + "quy định cuối " * 500
        chunks = split_sections("Tài liệu", content)
        self.assertGreater(len(chunks), 2)
        self.assertIn("quy định cuối", chunks[-1][1])

    def test_vector_literal_uses_pgvector_format(self):
        self.assertEqual(vector_literal([0.25, -0.5]), "[0.25000000,-0.50000000]")


class WorkerLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_claim_error_does_not_kill_worker(self):
        class RecoveringWorker(GraphRagWorker):
            def __init__(self):
                self.repository = None
                self.tasks = []
                self.stopping = asyncio.Event()
                self.wakeup = asyncio.Event()
                self.supervisor = None
                self.started_at = None
                self.last_poll_at = None
                self.last_claim_at = None
                self.last_success_at = None
                self.last_error = None
                self.claims = 0
                self.processed = asyncio.Event()

            async def _claim(self):
                self.claims += 1
                if self.claims == 1:
                    raise RuntimeError("temporary database failure")
                return {"id": "run-1", "attempts": 1}

            async def _process(self, run):
                self.processed.set()
                self.stopping.set()

        worker = RecoveringWorker()
        await asyncio.wait_for(worker._loop(0), timeout=4)
        self.assertTrue(worker.processed.is_set())
        self.assertEqual(worker.claims, 2)

    async def test_stage_progress_never_decreases(self):
        class Pool:
            def __init__(self):
                self.query = ""

            async def execute(self, query, *args):
                self.query = query

        class RepositoryStub:
            pool = Pool()

        worker = GraphRagWorker(RepositoryStub())
        await worker._stage("run-1", "CHUNKING", 15)
        self.assertIn("GREATEST(progress,$3)", RepositoryStub.pool.query)


if __name__ == "__main__":
    unittest.main()
