"""Capture scenario outcomes from pytest itself, not from expected fixture values."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.harness import registrations, summarize, validate_manifest

ROOT = Path(__file__).resolve().parent


def pytest_addoption(parser):
    parser.addoption("--harness-report", default=None, help="Write scenario mapping and actual outcomes to this JSON path")


def pytest_configure(config):
    config.addinivalue_line("markers", "scenario(*ids): acceptance scenario IDs verified by this test")
    config._scenario_nodes = {}
    config._scenario_reports = {}


def pytest_collection_modifyitems(config, items):
    for item in items:
        ids = [sid for mark in item.iter_markers("scenario") for sid in mark.args]
        for sid in ids:
            config._scenario_nodes.setdefault(sid, []).append(item.nodeid)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" or report.failed or report.skipped:
        prior = item.config._scenario_reports.get(item.nodeid)
        if prior and prior["result"] == "failed":
            return
        item.config._scenario_reports[item.nodeid] = {
            "result": "failed" if report.failed else "skipped" if report.skipped else "passed",
            "reason": None if report.passed else str(report.longrepr)[:1500],
        }


def pytest_sessionfinish(session, exitstatus):
    destination = session.config.getoption("--harness-report")
    if not destination:
        return
    cases = json.loads((ROOT / "ai_interview_codex/harness/scenarios.json").read_text(encoding="utf-8"))["cases"]
    manifest = registrations(ROOT)
    errors = validate_manifest(cases, manifest)
    results = []
    for case in cases:
        sid = case["id"]
        row = {"scenario_id": sid, "category": case["category"],
               "tests": [m for m in manifest if m["scenario_id"] == sid]}
        if case["category"] != "deterministic_invariant":
            row.update(result="pending_manual", reason="Independent human study has not been performed.")
        else:
            nodes = session.config._scenario_nodes.get(sid, [])
            runs = [{"nodeid": node, **session.config._scenario_reports.get(node, {"result": "blocked", "reason": "not_executed"})}
                    for node in nodes]
            mapping_errors = [e for e in errors if e["scenario_id"] == sid]
            if mapping_errors or not runs:
                row.update(result="blocked", reason=mapping_errors or "not_collected")
            else:
                priority = {"passed": 0, "skipped": 1, "blocked": 2, "failed": 3}
                worst = max(runs, key=lambda r: priority[r["result"]])
                row.update(result=worst["result"], reason=worst["reason"])
            row["executions"] = runs
        results.append(row)
    artifact = {"generated_at": datetime.now(timezone.utc).isoformat(), "runtime_mode": "mock",
                "database": "SQLite temporary test databases", "pytest_exit_code": int(exitstatus), **summarize(results)}
    if exitstatus != 0 and artifact["overall_status"] == "passed":
        artifact["overall_status"] = "failed"
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
