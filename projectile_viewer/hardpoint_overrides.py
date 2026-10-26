"""Per-unit, per-hardpoint field overrides made in the Hardpoint Viewer:
{unit name -> {hardpoint name -> {XML tag -> [values]}}}.

An override sits on top of the hardpoint's template data (its assigned
Hardpoint Config, or just its own XML when unassigned) - the same idea as the
Weapon Configs tab's overridden fields, but for any tag. A repeated tag
(e.g. Fire_Inaccuracy_Distance) is stored as the full list of its values.

Per-mod data, so the file is git-ignored like unit_hardpoint_assignments.json.
Same atomic load/save pattern as weapon_rules.py.
"""

import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "unit_hardpoint_overrides.json"
)
SCHEMA_VERSION = 1

Overrides = dict[str, dict[str, dict[str, list[str]]]]


def load_overrides(path: str = DEFAULT_PATH) -> Overrides:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    result: Overrides = {}
    for unit, hardpoints in data.get("units", {}).items():
        if not isinstance(hardpoints, dict):
            continue
        for hardpoint, tags in hardpoints.items():
            if not isinstance(tags, dict):
                continue
            cleaned = {
                str(tag): [str(v) for v in values]
                for tag, values in tags.items() if isinstance(values, list)
            }
            if cleaned:
                result.setdefault(unit, {})[hardpoint] = cleaned
    return result


def save_overrides(overrides: Overrides, path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cleaned: Overrides = {}
    for unit, hardpoints in sorted(overrides.items()):
        kept = {hp: dict(sorted(tags.items())) for hp, tags in sorted(hardpoints.items()) if tags}
        if kept:
            cleaned[unit] = kept
    payload = {"version": SCHEMA_VERSION, "units": cleaned}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
