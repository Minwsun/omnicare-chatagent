import json
from pathlib import Path

from .policies import classify_intent, risk_flags


def run_dataset(path: Path) -> dict:
    cases = json.loads(path.read_text(encoding="utf-8"))
    results = []
    for case in cases:
        intent = classify_intent(case["message"])
        risks = risk_flags(case["message"])
        passed = intent == case.get("expectedIntent", intent) and case.get("expectedRisk", risks[0] if risks else None) in risks + [None]
        results.append({"id": case["id"], "passed": passed, "intent": intent, "riskFlags": risks})
    return {"total": len(results), "passed": sum(item["passed"] for item in results), "results": results}
