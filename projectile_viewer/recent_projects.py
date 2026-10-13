"""Persists recently-used Projects to a local JSON file so past work can be
reopened quickly. Stored alongside the tool (portable, no-install).
"""

import json
import os
from datetime import datetime

from .project import ModLayer, Project

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "recent_projects.json"
)
MAX_RECENT = 10
SCHEMA_VERSION = 1


def _project_to_dict(project: Project, last_opened: str) -> dict:
    return {
        "name": project.name,
        "base_path": project.base_path,
        "mods": [{"path": m.path, "enabled": m.enabled} for m in project.mods],
        "last_opened": last_opened,
    }


def _dict_to_project(data: dict) -> Project:
    return Project(
        name=data.get("name", "Untitled"),
        base_path=data.get("base_path", ""),
        mods=[ModLayer(path=m["path"], enabled=m.get("enabled", True)) for m in data.get("mods", [])],
    )


def load_recent(path: str = DEFAULT_PATH) -> list[Project]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    return [_dict_to_project(entry) for entry in data.get("recent_projects", [])]


def _load_raw(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("recent_projects", [])


def save_recent(projects_raw: list[dict], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "recent_projects": projects_raw}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)


def remember(project: Project, path: str = DEFAULT_PATH) -> list[Project]:
    """Upsert `project` (matched by name, case-insensitive) to the front,
    update its timestamp, truncate to MAX_RECENT, persist atomically.
    Returns the updated list of Projects.
    """
    raw_entries = _load_raw(path)
    raw_entries = [e for e in raw_entries if e.get("name", "").lower() != project.name.lower()]

    new_entry = _project_to_dict(project, last_opened=datetime.now().isoformat())
    raw_entries.insert(0, new_entry)
    raw_entries = raw_entries[:MAX_RECENT]

    save_recent(raw_entries, path)
    return [_dict_to_project(entry) for entry in raw_entries]


def forget(name: str, path: str = DEFAULT_PATH) -> list[Project]:
    """Remove the recent-project entry matching `name` (case-insensitive).
    Persists atomically. Returns the updated list of Projects.
    """
    raw_entries = _load_raw(path)
    raw_entries = [e for e in raw_entries if e.get("name", "").lower() != name.lower()]

    save_recent(raw_entries, path)
    return [_dict_to_project(entry) for entry in raw_entries]
