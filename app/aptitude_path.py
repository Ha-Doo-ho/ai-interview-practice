"""Deterministic mirror routing and verified original practice boards."""
from copy import deepcopy
from functools import lru_cache
from itertools import combinations, product
import re


DIRECTIONS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}
_REFLECTION = {
    "/": {"N": "E", "E": "N", "S": "W", "W": "S"},
    "\\": {"N": "W", "W": "N", "S": "E", "E": "S"},
}


def reflect(direction, orientation):
    try:
        return _REFLECTION[orientation][direction]
    except (KeyError, TypeError) as error:
        raise ValueError("invalid_path_direction_or_fence") from error


def _fences(fences, size):
    """Normalize validated fence objects or canonical row,col keys."""
    normalized = {}
    if isinstance(fences, dict):
        entries = []
        for key, orientation in fences.items():
            if not isinstance(key, str) or not re.fullmatch(r"(?:0|[1-9]\d*),(?:0|[1-9]\d*)", key):
                raise ValueError("invalid_fence_position")
            row, col = map(int, key.split(","))
            entries.append((row, col, orientation))
    elif isinstance(fences, list):
        entries = []
        for fence in fences:
            if not isinstance(fence, dict):
                raise ValueError("invalid_fence")
            entries.append((fence.get("row"), fence.get("col"), fence.get("orientation")))
    else:
        raise ValueError("invalid_fences")
    for row, col, orientation in entries:
        if (type(row) is not int or type(col) is not int or not 0 <= row < size
                or not 0 <= col < size or orientation not in ("/", "\\") or (row, col) in normalized):
            raise ValueError("invalid_fence")
        normalized[row, col] = orientation
    return normalized


def _simulate(q, fences, *, trace=True):
    size = q["board_size"]
    destinations = {tuple(v["destination"]) for v in q["vehicles"]}
    results = []
    for vehicle in q["vehicles"]:
        row, col = vehicle["start"]
        direction = vehicle["direction"]
        seen, path = set(), []
        while True:
            state = row, col, direction
            if not 0 <= row < size or not 0 <= col < size:
                reason = "out_of_bounds"
                break
            if state in seen:
                reason = "loop"
                break
            seen.add(state)
            if trace:
                path.append([row, col, direction])
            if (row, col) == tuple(vehicle["destination"]):
                reason = "arrived"
                break
            if (row, col) in destinations:
                reason = "wrong_destination"
                break
            if (row, col) in fences:
                direction = reflect(direction, fences[row, col])
            dr, dc = DIRECTIONS[direction]
            row, col = row + dr, col + dc
        results.append({"id": vehicle["id"], "arrived": reason == "arrived", "reason": reason, "path": path})
        if not trace and reason != "arrived":
            return results
    return results


def simulate(q, fences):
    """Independent vehicles can share cells/fences; destinations terminate travel."""
    return _simulate(q, _fences(fences, q["board_size"]))


def minimum_fences(q, upper_bound):
    """Exhaustively find an exact minimum up to a known solution bound.

    Generation needs at most two fences. This helper deliberately makes no
    heuristic lower-bound claim: it checks both orientations at every cell.
    """
    if type(upper_bound) is not int or upper_bound < 0:
        raise ValueError("invalid_fence_bound")
    positions = list(product(range(q["board_size"]), repeat=2))
    for count in range(upper_bound + 1):
        for occupied in combinations(positions, count):
            for orientations in product(("/", "\\"), repeat=count):
                result = _simulate(q, dict(zip(occupied, orientations)), trace=False)
                if len(result) == len(q["vehicles"]) and all(r["arrived"] for r in result):
                    return count
    return None


@lru_cache(maxsize=32)
def _fixture(size, difficulty):
    # These original fixtures remain solvable when the board size changes.
    middle = size // 2
    if difficulty == "easy":
        vehicles = [{"id": "A", "label": "A", "color": "#2563eb", "start": [middle, 0],
                     "direction": "E", "destination": [0, middle]}]
        solution = {f"{middle},{middle}": "/"}
    else:
        vehicles = [
            {"id": "A", "label": "A", "color": "#2563eb", "start": [size - 1, 1],
             "direction": "N", "destination": [size - 1, size - 2]},
            {"id": "B", "label": "B", "color": "#c2410c", "start": [middle, size - 1],
             "direction": "W", "destination": [0, size - 2]},
        ]
        solution = {f"{middle},1": "/", f"{middle},{size - 2}": "\\"}
    q = {"board_size": size, "vehicles": vehicles, "solution": solution}
    if not all(r["arrived"] for r in simulate(q, solution)):
        raise ValueError("unsolved_path_fixture")
    # All smaller counts are searched; the known full solution proves the bound.
    smaller = minimum_fences(q, len(solution) - 1)
    q["minimum_fences"] = len(solution) if smaller is None else smaller
    return q


def generate(rng, number, difficulty, config):
    size = config.get("board_size", 5)
    if type(size) is not int or size < 5:
        raise ValueError("invalid_board_size")
    if difficulty not in ("easy", "hard"):
        raise ValueError("invalid_difficulty")
    q = deepcopy(_fixture(size, difficulty))
    # Square symmetries preserve solvability and the exact minimum fence count.
    turns, flip = rng.randrange(4), rng.choice((False, True))

    def position(point):
        row, col = point
        for _ in range(turns):
            row, col = col, size - 1 - row
        if flip:
            col = size - 1 - col
        return [row, col]

    for v in q["vehicles"]:
        v["start"], v["destination"] = position(v["start"]), position(v["destination"])
        v["direction"] = "NESW"[("NESW".index(v["direction"]) + turns) % 4]
        if flip:
            v["direction"] = {"N": "N", "S": "S", "E": "W", "W": "E"}[v["direction"]]
    solution = {}
    for key, orientation in q["solution"].items():
        row, col = position(map(int, key.split(",")))
        if bool(turns % 2) != flip:
            orientation = "\\" if orientation == "/" else "/"
        solution[f"{row},{col}"] = orientation
    q.update(number=number, solution=solution)
    if not all(r["arrived"] for r in simulate(q, solution)):
        raise ValueError("unsolved_transformed_path_fixture")
    return q


def public_question(q, practice=False):
    return {"number": q["number"], "board_size": q["board_size"], "vehicles": deepcopy(q["vehicles"])}


def evaluate(q, response):
    if not isinstance(response, dict):
        raise ValueError("invalid_path_response")
    fences = _fences(response.get("fences"), q["board_size"])
    results = _simulate(q, fences)
    minimum = q["minimum_fences"]
    return {"correct": all(result["arrived"] for result in results), "metrics": {
        "used_fences": len(fences), "minimum_fences": minimum,
        "excess_fences": max(0, len(fences) - minimum), "vehicle_results": results,
    }}
