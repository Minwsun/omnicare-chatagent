import unittest

from app.evaluation_live import missing_expected_tools
import ast
import json
from difflib import SequenceMatcher
from pathlib import Path


class EvaluationIntegrityTests(unittest.TestCase):
    def test_ownership_safe_tool_satisfies_legacy_order_detail_expectation(self):
        self.assertEqual(missing_expected_tools(["get_order_details", "get_shipping_status"], {"get_shipping_status"}), [])

    def test_only_one_production_agent_runtime_exists(self):
        app_dir = Path(__file__).parents[1] / "app"
        self.assertFalse((app_dir / "agent.py").exists())
        self.assertTrue((app_dir / "omnicare_agent" / "runtime.py").exists())
        self.assertFalse((app_dir / "langchain_runtime.py").exists())

    def test_production_does_not_reference_evaluation_case_ids(self):
        app_dir = Path(__file__).parents[1] / "app"
        source = "\n".join(path.read_text(encoding="utf-8") for path in app_dir.rglob("*.py"))
        for prefix in ("source_crawl_", "graph_policy_", "shopee_policy_", "tiktok_policy_", "safety_lifecycle_", "holdout_"):
            self.assertNotIn(prefix, source)

    def test_production_does_not_load_evaluation_datasets(self):
        app_dir = Path(__file__).parents[1] / "app"
        production = [path for path in app_dir.rglob("*.py") if not path.name.startswith("evaluation")]
        source = "\n".join(path.read_text(encoding="utf-8") for path in production)
        self.assertNotIn("evaluation-marketplaces.json", source)
        self.assertNotIn("evaluation-holdout.json", source)

    def test_retrieval_has_no_question_phrase_alias_table(self):
        retrieval = (Path(__file__).parents[1] / "app" / "retrieval.py").read_text(encoding="utf-8")
        self.assertNotIn("QUERY_ALIASES", retrieval)
        self.assertNotIn("canonical_expansion", retrieval)

    def test_routing_and_retrieval_literals_do_not_copy_holdout_questions(self):
        dataset_candidates = [Path("/datasets/evaluation-marketplaces.json")]
        if len(Path(__file__).parents) > 3:
            dataset_candidates.append(Path(__file__).parents[3] / "datasets" / "evaluation-marketplaces.json")
        dataset_path = next(path for path in dataset_candidates if path.exists())
        questions = [item["message"].casefold() for item in json.loads(dataset_path.read_text(encoding="utf-8"))]
        app_dir = Path(__file__).parents[1] / "app"
        literals = []
        for relative in ("retrieval.py", "omnicare_agent/supervisor.py"):
            tree = ast.parse((app_dir / relative).read_text(encoding="utf-8"))
            literals.extend(node.value.casefold() for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str) and 20 <= len(node.value) <= 240)
        matches = [(literal, question) for literal in literals for question in questions if SequenceMatcher(None, literal, question).ratio() >= 0.90]
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
