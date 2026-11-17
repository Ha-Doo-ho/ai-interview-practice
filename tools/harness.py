"""Acceptance registration and honest aggregation of real pytest results."""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^SCN-\d{3}$")
    requirement_ids: list[str] = Field(min_length=1)
    category: Literal["deterministic_invariant", "human_review", "effectiveness_review"]
    input: dict
    expected: list[str] = Field(min_length=1)
    forbidden: list[str] = Field(min_length=1)


class ScenarioSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str | int
    artifact_kind: str
    cases: list[Scenario]


def registrations(root: Path) -> list[dict]:
    """Extract explicit scenario decorators and assertion metadata, never test results."""
    result = []
    for path in sorted((root / "tests").rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == "scenario"):
                    continue
                assertions = sum(isinstance(n, ast.Assert) for n in ast.walk(node))
                assertions += sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                  and n.func.attr == "raises" for n in ast.walk(node))
                for arg in decorator.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        result.append({"scenario_id": arg.value, "test_file": path.relative_to(root).as_posix(),
                                       "test_name": node.name, "assertion_count": assertions})
    return result


def validate_manifest(cases: list[dict], manifest: list[dict]) -> list[dict]:
    errors = []
    known = {case["id"] for case in cases}
    for entry in manifest:
        if entry.get("scenario_id") not in known:
            errors.append({"scenario_id": entry.get("scenario_id"), "reason": "unknown_scenario"})
    for case in cases:
        if case["category"] != "deterministic_invariant":
            continue
        entries = [e for e in manifest if e.get("scenario_id") == case["id"]]
        if not entries or any(not e.get("test_file") or not e.get("test_name") for e in entries):
            errors.append({"scenario_id": case["id"], "reason": "unmapped"})
        elif any(e.get("assertion_count", 0) < 1 for e in entries):
            errors.append({"scenario_id": case["id"], "reason": "assertion_free"})
    return errors


def summarize(results: list[dict]) -> dict:
    valid = {"passed", "failed", "blocked", "skipped", "pending_manual"}
    if any(row.get("result") not in valid for row in results):
        raise ValueError("unknown_result_status")
    counts = {status: sum(row["result"] == status for row in results) for status in sorted(valid)}
    overall = "failed" if counts["failed"] else "incomplete" if counts["blocked"] or counts["skipped"] or counts["pending_manual"] else "passed"
    return {"overall_status": overall, "counts": counts, "results": results}
