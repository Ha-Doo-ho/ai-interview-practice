"""Rebuild a synthetic mock report using the same exercised API journey as pytest."""
import json
import os
import runpy
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from tools.harness import ScenarioSuite

ROOT = Path(__file__).resolve().parents[1]


def main(*, output_dir: Path | None = None):
    # Check before importing app.main: its module-global app opens a Store.
    if os.getenv("INTERVIEW_OFFLINE_RUN") != "1" or output_dir is None:
        raise SystemExit("Use: python -m tools.run_checks --sample")
    from app.main import create_app

    output = output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    journey = runpy.run_path(str(ROOT / "tests/test_acceptance_journey.py"))
    with TemporaryDirectory() as folder:
        app = create_app(f"sqlite:///{Path(folder) / 'sample.db'}")
        with TestClient(app) as client:
            registered = client.post("/api/register", headers=journey["HEADERS"],
                                     json={"username": "synthetic-sample", "password": "synthetic-only-password"})
            assert registered.status_code == 201
            run, _, _ = journey["complete_synthetic_run"](client)
        app.state.store.engine.dispose()
    sample = {"artifact_kind": "synthetic_mock_example", "contains_real_personal_data": False,
              "run": run}
    (output / "sample-report.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "scenario-schema.json").write_text(json.dumps(ScenarioSuite.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated synthetic mock sample-report.json and scenario-schema.json in {output}")


if __name__ == "__main__":
    main()
