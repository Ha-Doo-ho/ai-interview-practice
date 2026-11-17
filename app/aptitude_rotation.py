"""Coordinate-based 45-degree transformations for the original practice game.

Screen coordinates use positive y downwards. All numeric and shape choices are
project settings; they are not an official assessment model.
"""
from collections import deque
from copy import deepcopy
import math


COMMANDS = ("left", "right", "flip_h", "flip_v")
_C = math.sqrt(0.5)
_SHAPES = (
    ((-.75, -.9), (.25, -.9), (.25, -.2), (.9, -.2), (.9, .5), (-.75, .5)),
    ((-.8, -.8), (.3, -.8), (.3, -.25), (.9, .15), (.2, .7), (-.8, .4)),
    ((-.9, -.65), (-.2, -.65), (-.2, -.9), (.75, .15), (.2, .8), (-.9, .3)),
)


def transform(points, commands):
    """Apply commands in order without changing the source vertices."""
    if not isinstance(commands, (list, tuple)) or any(c not in COMMANDS for c in commands):
        raise ValueError("invalid_rotation_commands")
    result = [[float(x), float(y)] for x, y in points]
    for command in commands:
        if command == "left":
            result = [[_C * (x + y), _C * (y - x)] for x, y in result]
        elif command == "right":
            result = [[_C * (x - y), _C * (x + y)] for x, y in result]
        elif command == "flip_h":
            result = [[-x, y] for x, y in result]
        else:
            result = [[x, -y] for x, y in result]
    return result


def shapes_equal(first, second, tolerance=1e-7):
    """Compare placed polygon boundaries, allowing vertex order and float drift."""
    if len(first) != len(second):
        return False
    count = len(first)
    if count == 0:
        return True
    for direction in (1, -1):
        for start in range(count):
            if all(abs(first[i][axis] - second[(start + direction * i) % count][axis]) <= tolerance
                   for i in range(count) for axis in (0, 1)):
                return True
    return False


def _key(points):
    return tuple((round(x, 8), round(y, 8)) for x, y in points)


def _states(initial):
    # The rotations/reflections form at most sixteen distinct transformations.
    queue = deque([(deepcopy(initial), [])])
    seen = {_key(initial)}
    while queue:
        points, commands = queue.popleft()
        yield points, commands
        for command in COMMANDS:
            following = transform(points, [command])
            key = _key(following)
            if key not in seen:
                seen.add(key)
                queue.append((following, commands + [command]))


def shortest_solution(initial, target):
    """Return an exact BFS minimum command sequence, or None if unreachable."""
    for points, commands in _states(initial):
        if shapes_equal(points, target):
            return commands
    return None


def generate(rng, number, difficulty, config):
    if difficulty not in ("easy", "hard"):
        raise ValueError("invalid_difficulty")
    initial = transform(rng.choice(_SHAPES), ["right"] * rng.randrange(8))
    candidates = [(points, commands) for points, commands in _states(initial)
                  if (1 <= len(commands) <= 2 if difficulty == "easy" else len(commands) >= 3)]
    target, solution = rng.choice(candidates)
    return {"number": number, "initial_points": initial, "target_points": target,
            "min_operations": len(solution), "solution": solution}


def public_question(q, practice=False):
    public = {"number": q["number"], "initial_points": deepcopy(q["initial_points"]),
              "target_points": deepcopy(q["target_points"]), "available_commands": list(COMMANDS)}
    if practice:
        public["transformed_points"] = transform(q["initial_points"], q.get("commands", []))
    return public


def evaluate(q, response):
    if not isinstance(response, dict):
        raise ValueError("invalid_rotation_response")
    commands = response.get("commands")
    points = transform(q["initial_points"], commands)
    minimum = q["min_operations"]
    return {"correct": shapes_equal(points, q["target_points"]), "metrics": {
        "used_operations": len(commands), "min_operations": minimum,
        "excess_operations": max(0, len(commands) - minimum),
        "rotation_count": sum(c in ("left", "right") for c in commands),
        "flip_count": sum(c in ("flip_h", "flip_v") for c in commands),
    }}
