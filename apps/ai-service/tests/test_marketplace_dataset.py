import json
import unittest
from pathlib import Path


class MarketplaceDatasetTests(unittest.TestCase):
    def test_marketplace_dataset_has_expected_coverage(self):
        candidates = [Path("/datasets/evaluation-marketplaces.json")]
        if len(Path(__file__).parents) > 3:
            candidates.append(Path(__file__).parents[3] / "datasets" / "evaluation-marketplaces.json")
        path = next(item for item in candidates if item.exists())
        cases = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 200)
        counts = {}
        for case in cases:
            counts[case["category"]] = counts.get(case["category"], 0) + 1
        self.assertEqual(counts, {"SOURCE": 30, "POLICY": 40, "SHOPEE_DERIVED": 70, "TIKTOK_DERIVED": 40, "SAFETY": 20})
        self.assertTrue(all(case["customerId"] in {"customer_001", "customer_002"} for case in cases))


if __name__ == "__main__":
    unittest.main()
