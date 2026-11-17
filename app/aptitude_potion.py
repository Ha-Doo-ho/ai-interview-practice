"""Seedable four-card multiset prediction with a private fixed probability model.

The six probabilities and ingredient combinations are original project settings.
An outcome is sampled once when the private question is created, independently
of the submitted choice. Publication reveals it only through settled feedback.
"""


_COMBINATIONS = (
    ("A", ("leaf", "leaf", "crystal", "petal"), .80),
    ("B", ("leaf", "crystal", "crystal", "petal"), .20),
    ("C", ("leaf", "mushroom", "mushroom", "petal"), .65),
    ("D", ("leaf", "mushroom", "petal", "petal"), .35),
    ("E", ("crystal", "mushroom", "mushroom", "petal"), .70),
    ("F", ("crystal", "mushroom", "petal", "petal"), .30),
)


def combination_key(cards):
    """Keep card multiplicity, discard only presentation order."""
    if (not isinstance(cards, (list, tuple)) or len(cards) != 4
            or any(not isinstance(card, str) for card in cards)):
        raise ValueError("invalid_potion_cards")
    return tuple(sorted(cards))


_MODEL = {combination_key(cards): (id, probability) for id, cards, probability in _COMBINATIONS}


def probabilities(cards):
    try:
        _, red = _MODEL[combination_key(cards)]
    except KeyError as error:
        raise ValueError("unknown_potion_combination") from error
    return {"red": red, "blue": 1 - red}


def generate(rng, number, difficulty, config):
    if difficulty not in ("easy", "hard"):
        raise ValueError("invalid_difficulty")
    if type(number) is not int or number < 1:
        raise ValueError("invalid_question_number")
    # Balanced cycles guarantee repeated exposure, even in a twenty-round game.
    # Easier play reduces working-memory load to three recurring combinations.
    count = 3 if difficulty == "easy" else 6
    id, ingredients, red = _COMBINATIONS[(number - 1) % count]
    cards = list(ingredients)
    rng.shuffle(cards)
    outcome = "red" if rng.random() < red else "blue"
    return {"number": number, "cards": cards, "combination_id": id,
            "red_probability": red, "outcome": outcome,
            "favorable_color": "red" if red > .5 else "blue"}


def public_question(q, practice=False):
    # No exception for practice: the latent probabilities remain a learning task.
    return {"number": q["number"], "cards": list(q["cards"]), "combination_id": q["combination_id"]}


def evaluate(q, response):
    if not isinstance(response, dict) or response.get("choice") not in ("red", "blue"):
        raise ValueError("invalid_potion_choice")
    choice = response["choice"]
    return {"correct": choice == q["outcome"], "outcome": q["outcome"], "metrics": {
        "combination_id": q["combination_id"], "choice": choice,
        "actual_outcome": q["outcome"], "favorable_choice": choice == q["favorable_color"],
    }}
