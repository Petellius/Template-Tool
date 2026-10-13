"""Persists small app-wide UI preferences (currently just dark mode) to a
local JSON file, mirroring recent_projects.py's atomic load/save pattern.
"""

import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "app_settings.json"
)
SCHEMA_VERSION = 1


def load_dark_mode(path: str = DEFAULT_PATH) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("dark_mode", False))


def save_dark_mode(dark_mode: bool, path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "dark_mode": dark_mode}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
