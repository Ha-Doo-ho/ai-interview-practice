"""Synthetic, deterministic behavior checks for the three practice algorithms."""
from copy import deepcopy
import importlib
import importlib.util
from itertools import permutations
import math
import random

import pytest


def module(name):
    qualified = "app.aptitude_" + name
    assert importlib.util.find_spec(qualified) is not None, "Missing game algorithm: " + name
    return importlib.import_module(qualified)


@pytest.mark.parametrize("command,expected", [
    ("right", [math.sqrt(.5), math.sqrt(.5)]),
    ("left", [math.sqrt(.5), -math.sqrt(.5)]),
    ("flip_h", [-1, 0]), ("flip_v", [1, 0]),
])
def test_rotation_applies_coordinates_in_screen_axes(command, expected):
    result = module("rotation").transform([[1, 0]], [command])
    assert result[0] == pytest.approx(expected, abs=1e-8)


def test_rotation_flips_both_axes_and_command_order_matters():
    game = module("rotation")
    assert game.transform([[2, 3]], ["flip_h"]) == [[-2, 3]]
    assert game.transform([[2, 3]], ["flip_v"]) == [[2, -3]]
    a = game.transform([[1, 0]], ["right", "flip_h"])[0]
    b = game.transform([[1, 0]], ["flip_h", "right"])[0]
    assert a == pytest.approx([-math.sqrt(.5), math.sqrt(.5)])
    assert b == pytest.approx([-math.sqrt(.5), -math.sqrt(.5)])


def test_rotation_full_turn_tolerates_rounding_and_does_not_mutate_source():
    game = module("rotation")
    points = [[1.5, -3.4], [2.1, 1.8], [-2.8, 1.1]]
    original = deepcopy(points)
    rotated = game.transform(points, ["right"] * 8)
    assert game.shapes_equal(points, rotated)
    assert points == original
    assert not game.shapes_equal(points, [[x + .01, y] for x, y in points])


def test_rotation_bfs_finds_shortest_not_generation_length():
    game = module("rotation")
    points = [[1, 0], [0, 2], [-3, 1]]
    target = game.transform(points, ["right"] * 7)
    assert game.shortest_solution(points, target) == ["left"]
    assert game.shortest_solution(points, points) == []
    assert game.shortest_solution(points, [[8, 0], [0, 2], [-3, 1]]) is None


@pytest.mark.parametrize("difficulty", ["easy", "hard"])
def test_rotation_generates_nontrivial_reachable_problems_and_correct_metrics(difficulty):
    game = module("rotation")
    for seed in range(32):
        q = game.generate(random.Random(seed), seed + 1, difficulty, {})
        assert q["solution"]
        assert q["min_operations"] == len(game.shortest_solution(q["initial_points"], q["target_points"]))
        result = game.evaluate(q, {"commands": q["solution"]})
        assert result["correct"]
        assert result["metrics"]["excess_operations"] == 0
        assert not game.evaluate(q, {"commands": []})["correct"]
        if difficulty == "hard":
            assert q["min_operations"] >= 3
        else:
            assert q["min_operations"] <= 2


def test_rotation_main_projection_hides_solution_and_current_transformation():
    game = module("rotation")
    q = game.generate(random.Random(1), 1, "easy", {})
    q["commands"] = ["right"]
    public = game.public_question(q)
    assert set(public) == {"number", "initial_points", "target_points", "available_commands"}
    practice = game.public_question(q, practice=True)
    assert practice["transformed_points"] == game.transform(q["initial_points"], ["right"])
    public["initial_points"][0][0] = 999
    assert q["initial_points"][0][0] != 999


@pytest.mark.parametrize("commands", [["rotate_90"], "right", [None], [1]])
def test_rotation_rejects_unknown_or_malformed_commands(commands):
    game = module("rotation")
    with pytest.raises(ValueError):
        game.transform([[1, 2]], commands)


def board(vehicles):
    return {"number": 1, "board_size": 5, "vehicles": vehicles, "minimum_fences": 1}


def vehicle(id="A", start=(2, 0), direction="E", destination=(0, 2)):
    return {"id": id, "label": id, "color": "#123456", "start": list(start),
            "direction": direction, "destination": list(destination)}


@pytest.mark.parametrize("direction,mirror,want", [
    ("N", "/", "E"), ("E", "/", "N"), ("S", "/", "W"), ("W", "/", "S"),
    ("N", "\\", "W"), ("W", "\\", "N"), ("S", "\\", "E"), ("E", "\\", "S"),
])
def test_path_reflects_all_eight_direction_and_fence_pairs(direction, mirror, want):
    assert module("path").reflect(direction, mirror) == want


def test_path_arrives_with_fence_and_leaves_board_without_it():
    game = module("path")
    q = board([vehicle()])
    result = game.simulate(q, {"2,2": "/"})
    assert result[0]["arrived"] is True
    assert result[0]["path"][-1][0:2] == [0, 2]
    assert game.simulate(q, {})[0]["reason"] == "out_of_bounds"


def test_path_stops_at_wrong_destination_before_reaching_own():
    game = module("path")
    q = board([vehicle(destination=(2, 4)), vehicle("B", (4, 4), "N", (2, 2))])
    assert game.simulate(q, {})[0]["reason"] == "wrong_destination"


def test_path_detects_loop_from_repeated_position_and_direction():
    game = module("path")
    q = board([vehicle(start=(1, 1), direction="N", destination=(4, 4))])
    fences = {"1,1": "/", "1,3": "\\", "3,3": "/", "3,1": "\\"}
    result = game.simulate(q, fences)[0]
    assert result["reason"] == "loop"
    assert not result["arrived"]
    assert len(result["path"]) <= 4 * 5 * 5 + 1


def test_path_allows_shared_mirror_without_collision_and_requires_every_vehicle():
    game = module("path")
    q = board([vehicle(destination=(0, 2)), vehicle("B", (4, 2), "N", (2, 4))])
    result = game.evaluate(q, {"fences": {"2,2": "/"}})
    assert result["correct"]
    assert result["metrics"]["used_fences"] == 1
    assert all(r["arrived"] for r in result["metrics"]["vehicle_results"])
    q["vehicles"][1]["destination"] = [1, 4]
    assert not game.evaluate(q, {"fences": {"2,2": "/"}})["correct"]


def test_path_minimum_search_includes_all_positions_and_orientations():
    game = module("path")
    assert game.minimum_fences(board([vehicle(destination=(2, 4))]), upper_bound=2) == 0
    assert game.minimum_fences(board([vehicle()]), upper_bound=2) == 1
    hard = board([vehicle(start=(4, 1), direction="N", destination=(4, 3)),
                  vehicle("B", (2, 4), "W", (0, 3))])
    assert game.minimum_fences(hard, upper_bound=1) is None
    assert game.minimum_fences(hard, upper_bound=2) == 2


@pytest.mark.parametrize("size", [5, 6, 8])
@pytest.mark.parametrize("difficulty,vehicle_count,minimum", [("easy", 1, 1), ("hard", 2, 2)])
def test_path_generator_only_returns_solved_verified_difficulty_fixtures(size, difficulty, vehicle_count, minimum):
    game = module("path")
    for seed in range(8):
        q = game.generate(random.Random(seed), seed + 1, difficulty, {"board_size": size})
        assert q["board_size"] == size
        assert len(q["vehicles"]) == vehicle_count
        assert q["minimum_fences"] == minimum
        assert game.evaluate(q, {"fences": q["solution"]})["correct"]
        assert game.minimum_fences(q, upper_bound=minimum - 1) is None
        public = game.public_question(q)
        assert set(public) == {"number", "board_size", "vehicles"}


@pytest.mark.parametrize("fences", [{"5,0": "/"}, {"-1,0": "\\"}, {"1,2": "x"},
    {"bad": "/"}, {"1.0,2": "/"}, [{"row": True, "col": 1, "orientation": "/"}],
    [{"row": 1, "col": 1, "orientation": "/"}, {"row": 1, "col": 1, "orientation": "\\"}]])
def test_path_rejects_invalid_fences(fences):
    with pytest.raises(ValueError):
        module("path").simulate(board([vehicle()]), fences)


def test_path_accepts_explicit_fence_objects_and_does_not_mutate_board():
    game = module("path")
    q = board([vehicle()])
    before = deepcopy(q)
    assert game.evaluate(q, {"fences": [{"row": 2, "col": 2, "orientation": "/"}]})["correct"]
    assert q == before


def test_potion_four_card_multiset_probabilities_are_order_independent():
    game = module("potion")
    for number in range(1, 7):
        q = game.generate(random.Random(number), number, "hard", {})
        assert len(q["cards"]) == 4
        for shuffled in permutations(q["cards"]):
            assert game.combination_key(shuffled) == game.combination_key(q["cards"])
            probs = game.probabilities(shuffled)
            assert probs["red"] + probs["blue"] == pytest.approx(1)
            assert probs["red"] == q["red_probability"]
            assert 0 < probs["red"] < 1


def test_potion_repeats_combinations_with_fixed_probabilities_and_seeded_outcomes():
    game = module("potion")
    a_rng, b_rng = random.Random(42), random.Random(42)
    a = [game.generate(a_rng, n, "hard", {}) for n in range(1, 101)]
    b = [game.generate(b_rng, n, "hard", {}) for n in range(1, 101)]
    assert a == b
    assert len({q["combination_id"] for q in a}) == 6
    seen = {}
    for q in a:
        seen.setdefault(q["combination_id"], set()).add(q["red_probability"])
    assert all(len(probabilities) == 1 for probabilities in seen.values())


def test_potion_samples_both_outcomes_and_expected_distribution_for_every_combination():
    game = module("potion")
    rng = random.Random(80231)
    counts = {id: [0, 0] for id in "ABCDEF"}
    probabilities = {}
    for number in range(1, 12001):
        q = game.generate(rng, number, "hard", {})
        counts[q["combination_id"]][q["outcome"] == "red"] += 1
        probabilities[q["combination_id"]] = q["red_probability"]
    for id, (blue, red) in counts.items():
        assert blue > 0 and red > 0
        assert red / (blue + red) == pytest.approx(probabilities[id], abs=.045)


def test_potion_outcome_does_not_depend_on_choice_and_favorable_can_miss():
    game = module("potion")
    q = game.generate(random.Random(1), 1, "hard", {})
    q["outcome"] = "blue"
    red = game.evaluate(q, {"choice": "red"})
    blue = game.evaluate(q, {"choice": "blue"})
    assert red["outcome"] == blue["outcome"] == "blue"
    assert red["correct"] is False and blue["correct"] is True
    assert red["metrics"]["favorable_choice"] is True
    assert blue["metrics"]["favorable_choice"] is False


@pytest.mark.parametrize("practice", [False, True])
def test_potion_public_projection_hides_probability_outcome_and_model_even_in_practice(practice):
    game = module("potion")
    q = game.generate(random.Random(12), 1, "hard", {})
    public = game.public_question(q, practice=practice)
    assert set(public) == {"number", "cards", "combination_id"}
    public["cards"][0] = "modified"
    assert "modified" not in q["cards"]


@pytest.mark.parametrize("choice", ["purple", "RED", None, {}, 1])
def test_potion_rejects_invalid_prediction(choice):
    game = module("potion")
    q = game.generate(random.Random(1), 1, "hard", {})
    with pytest.raises(ValueError):
        game.evaluate(q, {"choice": choice})
