"""Remembers which Hardpoint Config each of a unit's hardpoints is assigned
to: {unit name -> {hardpoint name -> config name}}. Drives the Hardpoint
Viewer's grouping and its mismatch warnings.

Per-mod data (unit/hardpoint names), so the file is git-ignored like
weapon_configs.json. Same atomic load/save pattern as weapon_rules.py.
"""

import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "unit_hardpoint_assignments.json"
)
SCHEMA_VERSION = 1

Assignments = dict[str, dict[str, str]]


def load_assignments(path: str = DEFAULT_PATH) -> Assignments:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    result: Assignments = {}
    for unit, mapping in data.get("units", {}).items():
        if isinstance(mapping, dict):
            result[unit] = {str(hp): str(cfg) for hp, cfg in mapping.items() if cfg}
    return result


def save_assignments(assignments: Assignments, path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cleaned = {unit: dict(sorted(m.items())) for unit, m in sorted(assignments.items()) if m}
    payload = {"version": SCHEMA_VERSION, "units": cleaned}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
