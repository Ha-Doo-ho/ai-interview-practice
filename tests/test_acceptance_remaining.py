"""Ordinal and causal interpretation checks against actual report generation."""
import copy
import json

import pytest

from app.analysis import analyze_run
from app.content import DEFINITIONS
from app.game import initial_game_state, aggregate_game
from app.survey import build_survey_record


def snapshot():
    game = initial_game_state(DEFINITIONS["game"])
    game["metrics"] = aggregate_game(game)
    return {"run_id": "synthetic", "user_id": "synthetic", "attempt_id": "attempt",
            "generation": 1, "revision": 1, "runtime_mode": "mock", "records": [],
            "questions": copy.deepcopy(DEFINITIONS["questions"]), "game": game}


@pytest.mark.scenario("SCN-002")
def test_ordinal_positions_preserve_labels_without_interval_score_or_mean():
    run = snapshot()
    for order, (item, position) in enumerate(zip(DEFINITIONS["surveys"][:2], [5, 3]), 1):
        run["records"].append(build_survey_record(
            definition=item, user_id=run["user_id"], run_id=run["run_id"], attempt_id=run["attempt_id"],
            presentation_order=order, response={"selected_position": position}, status="submitted", elapsed_ms=1000))
    report = analyze_run(run, DEFINITIONS)["report"]
    first, second = report["cards"][:2]
    assert first["survey_evidence"]["selected_position"] == 5
    assert first["survey_evidence"]["selected_label_snapshot"] == "그렇다"
    assert second["survey_evidence"]["selected_position"] == 3
    assert second["survey_evidence"]["selected_label_snapshot"] == "그렇지 않은 편이다"
    assert all(card["survey_evidence"]["measurement_level"] == "ordinal" for card in (first, second))
    encoded = json.dumps(report, ensure_ascii=False)
    assert not any(term in encoded for term in ('66.7%', 'personality_score', 'ordinal_mean', 'latent_ability', 'percentile'))
    assert any("간격" in limit or "순서형" in limit for limit in report["limitations"])


@pytest.mark.scenario("SCN-024")
def test_different_round_rewards_do_not_become_causal_effect_of_information():
    run = snapshot()
    rounds = run["game"]["rounds"]
    rounds[1]["game_result"] = {"reward": 8, "opened_information": True, "condition_id": "A", "difficulty": "hard"}
    rounds[2]["game_result"] = {"reward": 5, "opened_information": False, "condition_id": "B", "difficulty": "easy"}
    result = analyze_run(run, DEFINITIONS)
    swapped = copy.deepcopy(run)
    swapped["game"]["rounds"][1]["game_result"]["reward"] = 5
    swapped["game"]["rounds"][2]["game_result"]["reward"] = 8
    second = analyze_run(swapped, DEFINITIONS)
    assert result["comparisons"] == second["comparisons"]
    assert all(card["comparison"]["causal_claim"] is False for card in result["report"]["cards"])
    assert any("인과" in limit for limit in result["report"]["limitations"])
    assert not any(key in json.dumps(result["report"]) for key in ('causal_effect_size', 'reward_uplift', 'collaboration_score'))
