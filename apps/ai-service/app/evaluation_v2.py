from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


DatasetSplit = Literal["DEVELOPMENT", "REGRESSION", "HOLDOUT", "ADVERSARIAL", "HUMAN_QUALITY"]
Decision = Literal["ANSWER", "CLARIFY", "CONFIRM", "PENDING_APPROVAL", "HANDOFF", "REFUSE"]


class EvaluationTurn(BaseModel):
    message: str = Field(min_length=1)
    page_context: dict[str, Any] = Field(default_factory=dict)
    expected_active_order_id: str | None = None
    select_option_index: int | None = Field(default=None, ge=0)


class ExpectedBehavior(BaseModel):
    intents: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    required_citation_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    decision: Decision = "ANSWER"
    ui_kinds: list[str] = Field(default_factory=list)
    model_profile: Literal["fast", "reasoning", "reviewer"] | None = None
    requires_human: bool | None = None
    max_tool_calls: int = 8


class EvaluationCase(BaseModel):
    id: str = Field(min_length=3)
    cluster_id: str = Field(min_length=3)
    split: DatasetSplit
    category: str
    customer_id: str
    conversation_id: str | None = None
    turns: list[EvaluationTurn] = Field(min_length=1)
    expected: ExpectedBehavior = Field(default_factory=ExpectedBehavior)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tools(self) -> "EvaluationCase":
        overlap = set(self.expected.required_tools).intersection(self.expected.forbidden_tools)
        if overlap:
            raise ValueError(f"Tools cannot be required and forbidden: {sorted(overlap)}")
        return self


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def semantic_fingerprint(case: EvaluationCase) -> str:
    entity_free = re.sub(r"\b(?:ord[-_ ]?)?[a-z0-9]{6,}\b", "<entity>", " ".join(normalize_text(turn.message) for turn in case.turns))
    return hashlib.sha256(f"{case.category}|{entity_free}".encode()).hexdigest()


def validate_dataset(cases: list[EvaluationCase]) -> dict[str, Any]:
    ids = Counter(case.id for case in cases)
    duplicate_ids = sorted(key for key, count in ids.items() if count > 1)
    texts: dict[str, list[str]] = defaultdict(list)
    fingerprints: dict[str, list[str]] = defaultdict(list)
    cluster_splits: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        normalized = " || ".join(normalize_text(turn.message) for turn in case.turns)
        texts[normalized].append(case.id)
        fingerprints[semantic_fingerprint(case)].append(case.id)
        cluster_splits[case.cluster_id].add(case.split)
    duplicate_text = {key: value for key, value in texts.items() if len(value) > 1}
    duplicate_semantic = {key: value for key, value in fingerprints.items() if len(value) > 1}
    split_leakage = {key: sorted(value) for key, value in cluster_splits.items() if len(value) > 1}
    errors = []
    if duplicate_ids:
        errors.append("DUPLICATE_IDS")
    if duplicate_text:
        errors.append("DUPLICATE_TEXT")
    if split_leakage:
        errors.append("CLUSTER_SPLIT_LEAKAGE")
    return {
        "valid": not errors,
        "errors": errors,
        "total": len(cases),
        "splits": dict(Counter(case.split for case in cases)),
        "categories": dict(Counter(case.category for case in cases)),
        "duplicateIds": duplicate_ids,
        "duplicateText": duplicate_text,
        "semanticCollisions": duplicate_semantic,
        "clusterSplitLeakage": split_leakage,
    }


def grade_run(case: EvaluationCase, turns: list[dict[str, Any]]) -> dict[str, Any]:
    final = turns[-1] if turns else {}
    errors: list[str] = []
    tool_calls = [tool for turn in turns for tool in turn.get("toolCalls", [])]
    tool_names = [item.get("name") if isinstance(item, dict) else item for item in tool_calls]
    citations = [citation for turn in turns for citation in turn.get("citations", [])]
    answer = str(final.get("answer") or "")
    intents = {str(turn.get("intent") or "") for turn in turns}
    expected = case.expected
    if not answer.strip():
        errors.append("NO_ANSWER")
    if expected.intents and not intents.intersection(expected.intents):
        errors.append("INTENT_MISMATCH")
    if not set(expected.required_tools).issubset(tool_names):
        errors.append("REQUIRED_TOOL_MISSING")
    if set(expected.forbidden_tools).intersection(tool_names):
        errors.append("FORBIDDEN_TOOL_USED")
    if expected.allowed_tools and not set(tool_names).issubset(expected.allowed_tools):
        errors.append("UNEXPECTED_TOOL_USED")
    if len(tool_names) > expected.max_tool_calls:
        errors.append("TOOL_BUDGET_EXCEEDED")
    if expected.requires_human is not None and bool(final.get("requiresHuman", final.get("requires_human"))) != expected.requires_human:
        errors.append("HANDOFF_MISMATCH")
    citation_text = " ".join(str(item.get("title", "")) + " " + str(item.get("section", "")) for item in citations).casefold()
    if expected.required_citation_terms and not any(term.casefold() in citation_text for term in expected.required_citation_terms):
        errors.append("CITATION_MISSING_OR_IRRELEVANT")
    if any(term.casefold() in answer.casefold() for term in expected.forbidden_terms):
        errors.append("FORBIDDEN_CONTENT")
    ui_kinds = {str(item.get("kind") or item.get("type")) for item in final.get("ui", []) if isinstance(item, dict)}
    if not set(expected.ui_kinds).issubset(ui_kinds):
        errors.append("REQUIRED_UI_MISSING")
    selected_profiles = [turn.get("modelProfile") for turn in turns if turn.get("modelProfile")]
    if expected.model_profile and expected.model_profile not in selected_profiles:
        errors.append("MODEL_PROFILE_MISMATCH")
    repeated_calls = Counter(json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, dict) else str(item) for item in tool_calls)
    if any(count > 1 for count in repeated_calls.values()):
        errors.append("DUPLICATE_TOOL_CALL")
    for index, turn in enumerate(turns):
        expected_order = case.turns[min(index, len(case.turns) - 1)].expected_active_order_id
        if expected_order and turn.get("resolvedOrderId") != expected_order:
            errors.append("CONTEXT_ORDER_MISMATCH")
    return {"passed": not errors, "errors": sorted(set(errors)), "toolCalls": tool_names, "turns": len(turns)}


def release_gate(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(bool(item.get("passed")) for item in results)
    error_counts = Counter(error for item in results for error in item.get("errors", []))
    blockers = {
        "FORBIDDEN_TOOL_USED", "HANDOFF_MISMATCH", "FORBIDDEN_CONTENT",
        "CONTEXT_ORDER_MISMATCH", "CITATION_MISSING_OR_IRRELEVANT",
    }
    blocked = any(error_counts[error] for error in blockers)
    pass_rate = passed / total if total else 0
    return {
        "passed": total > 0 and pass_rate >= 0.92 and not blocked,
        "total": total,
        "passedCases": passed,
        "passRate": round(pass_rate, 4),
        "blockingErrors": {key: error_counts[key] for key in sorted(blockers) if error_counts[key]},
        "errors": dict(error_counts),
    }


def load_cases(path: Path) -> list[EvaluationCase]:
    return [EvaluationCase.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
