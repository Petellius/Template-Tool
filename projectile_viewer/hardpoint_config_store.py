"""Persists saved Hardpoint Configs to a local JSON file, mirroring
weapon_rules.py's atomic load/save pattern. The embedded weapon block reuses
weapon_config_store's WeaponConfig (de)serialiser so both stores always agree
on that shape.

The file is shared presets (like weapon_rules.json), so it lives in
user_data/ and is not git-ignored.
"""

import json
import os
from dataclasses import fields

from .hardpoint_config import KIND_WEAPON, HardpointConfig
from .weapon_config_store import config_to_dict, dict_to_config

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "hardpoint_configs.json"
)
SCHEMA_VERSION = 1

_WEAPON_KEY = "weapon"


def _config_to_dict(config: HardpointConfig) -> dict:
    data = {}
    for f in fields(HardpointConfig):
        if f.name == _WEAPON_KEY:
            continue
        data[f.name] = getattr(config, f.name)
    data[_WEAPON_KEY] = config_to_dict(config.weapon)
    return data


def _dict_to_config(data: dict) -> HardpointConfig:
    """Tolerant of missing keys (older files) and unknown keys (newer ones):
    anything absent keeps the dataclass default."""
    defaults = HardpointConfig(name=data.get("name", "Untitled"))
    kwargs = {}
    for f in fields(HardpointConfig):
        if f.name in (_WEAPON_KEY, "name"):
            continue
        value = data.get(f.name, getattr(defaults, f.name))
        default_value = getattr(defaults, f.name)
        # Never let a stray type slip through (e.g. "Yes" for a bool field).
        if isinstance(default_value, bool):
            value = bool(value)
        elif isinstance(default_value, float):
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = default_value
        kwargs[f.name] = value

    config = HardpointConfig(name=defaults.name, **kwargs)
    weapon_data = data.get(_WEAPON_KEY)
    if isinstance(weapon_data, dict):
        config.weapon = dict_to_config(weapon_data)
    else:
        config.weapon.name = config.name
    if config.kind not in (KIND_WEAPON, "non_weapon"):
        config.kind = KIND_WEAPON
    return config


def load_configs(path: str = DEFAULT_PATH) -> list[HardpointConfig]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    return [_dict_to_config(entry) for entry in data.get("configs", []) if isinstance(entry, dict)]


def save_configs(configs: list[HardpointConfig], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "configs": [_config_to_dict(c) for c in configs]}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
