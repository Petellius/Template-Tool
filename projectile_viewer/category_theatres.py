"""User-defined theatre assignments for GameObjectCategoryType masks.

The enum file says nothing about whether a mask is a Space or a Land
concept, so which masks the Weapon Templates tab offers per theatre is
inferred (ui.THEATRE_BASE_CATEGORIES + masks the loaded units carry). This
lets the user override that per mask from the Category Masks tab.

A mask with no entry here keeps the inferred default. An entry is the list of
theatres the mask applies to - [] means "neither", i.e. hidden from both.
Persisted as a small JSON file mirroring weapon_rules.py's atomic pattern;
it's shared across projects since mask meaning is the same game to game.
"""

import json
import os

THEATRES = ("Space", "Land")

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "category_theatres.json"
)
SCHEMA_VERSION = 1


def load_overrides(path: str = DEFAULT_PATH) -> dict[str, list[str]]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    result: dict[str, list[str]] = {}
    for name, theatres in data.get("theatres", {}).items():
        if isinstance(theatres, list):
            result[name] = [t for t in THEATRES if t in theatres]
    return result


def save_overrides(overrides: dict[str, list[str]], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "theatres": {k: list(v) for k, v in sorted(overrides.items())}}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
