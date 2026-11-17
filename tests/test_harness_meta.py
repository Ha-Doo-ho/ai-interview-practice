import copy
import json
import re
from pathlib import Path

import pytest

from tools.harness import ScenarioSuite, registrations, summarize, validate_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_fixture_schema_and_requirement_references():
    raw = json.loads((ROOT / "ai_interview_codex/harness/scenarios.json").read_text(encoding="utf-8"))
    suite = ScenarioSuite.model_validate(raw)
    ids = [case.id for case in suite.cases]
    assert len(ids) == len(set(ids)) == 68
    requirements = set(re.findall(r"\| ([A-Z]+-\d{3}) \|", (ROOT / "ai_interview_codex/HARNESS.md").read_text(encoding="utf-8")))
    assert all(set(case.requirement_ids) <= requirements for case in suite.cases)
    assert {c.id for c in suite.cases if c.category != "deterministic_invariant"} == {"SCN-051", "SCN-053"}
    assert validate_manifest(raw["cases"], registrations(ROOT)) == []


@pytest.mark.scenario("SCN-054")
def test_manifest_rejects_missing_mapping_and_assertion_free_tests():
    cases = [{"id": "SCN-021", "category": "deterministic_invariant"},
             {"id": "SCN-022", "category": "deterministic_invariant"}]
    mapping = [{"scenario_id": "SCN-022", "test_file": "tests/example.py", "test_name": "test_no_assert", "assertion_count": 0}]
    assert validate_manifest(cases, mapping) == [
        {"scenario_id": "SCN-021", "reason": "unmapped"},
        {"scenario_id": "SCN-022", "reason": "assertion_free"},
    ]
    registered = registrations(ROOT)
    own = [r for r in registered if r["scenario_id"] == "SCN-054"]
    assert own and own[0]["assertion_count"] > 0
    assert (ROOT / own[0]["test_file"]).is_file()


@pytest.mark.scenario("SCN-055")
def test_results_preserve_failures_blocked_skipped_and_manual():
    results = [{"scenario_id": str(i), "result": "passed", "reason": None} for i in range(40)]
    results += [{"scenario_id": "f1", "result": "failed", "reason": "assertion"},
                {"scenario_id": "f2", "result": "failed", "reason": "assertion"},
                {"scenario_id": "b", "result": "blocked", "reason": "paid_not_authorized"},
                {"scenario_id": "s", "result": "skipped", "reason": "stack_not_applicable"}]
    actual = summarize(results)
    assert actual["counts"] == {"passed": 40, "failed": 2, "blocked": 1, "skipped": 1, "pending_manual": 0}
    assert actual["overall_status"] == "failed"
    assert actual["results"] == results
    assert summarize([results[-1]])["overall_status"] == "incomplete"
    assert summarize([{"result": "pending_manual"}])["counts"]["passed"] == 0
    assert summarize([{"result": "pending_manual"}])["overall_status"] == "incomplete"
