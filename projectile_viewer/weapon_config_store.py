"""Persists saved Weapon Configs to a local JSON file, mirroring
recent_projects.py's atomic load/save pattern exactly.
"""

import json
import os

from .weapon_config import WeaponConfig

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "weapon_configs.json"
)
SCHEMA_VERSION = 1


def config_to_dict(config: WeaponConfig) -> dict:
    return {
        "name": config.name,
        "unit_name": config.unit_name,
        "source_projectile_name": config.source_projectile_name,
        "source_hardpoint_name": config.source_hardpoint_name,
        "context": config.context,
        "category": config.category,
        "damage": config.damage,
        "damage_type": config.damage_type,
        "fire_min_recharge": config.fire_min_recharge,
        "fire_max_recharge": config.fire_max_recharge,
        "fire_pulse_count": config.fire_pulse_count,
        "fire_pulse_delay": config.fire_pulse_delay,
        "fire_range": config.fire_range,
        "fire_cone_width": config.fire_cone_width,
        "fire_cone_height": config.fire_cone_height,
        "turret_rotate_speed": config.turret_rotate_speed,
        "accuracy_by_category": dict(config.accuracy_by_category),
        "sfx_event": config.sfx_event,
        "modifiers": dict(config.modifiers),
        "category_restrictions": list(config.category_restrictions),
        "notes": config.notes,
        "overridden_fields": sorted(config.overridden_fields),
        "override_notes": dict(config.override_notes),
    }


def dict_to_config(data: dict) -> WeaponConfig:
    return WeaponConfig(
        name=data.get("name", "Untitled"),
        unit_name=data.get("unit_name", ""),
        source_projectile_name=data.get("source_projectile_name", ""),
        source_hardpoint_name=data.get("source_hardpoint_name", ""),
        context=data.get("context", "hardpoint"),
        category=data.get("category", ""),
        damage=data.get("damage", 0.0),
        damage_type=data.get("damage_type", ""),
        fire_min_recharge=data.get("fire_min_recharge", 0.0),
        fire_max_recharge=data.get("fire_max_recharge", 0.0),
        fire_pulse_count=data.get("fire_pulse_count", 1),
        fire_pulse_delay=data.get("fire_pulse_delay", 0.0),
        fire_range=data.get("fire_range", 0.0),
        fire_cone_width=data.get("fire_cone_width", 0.0),
        fire_cone_height=data.get("fire_cone_height", 0.0),
        turret_rotate_speed=data.get("turret_rotate_speed", 0.0),
        accuracy_by_category=dict(data.get("accuracy_by_category", {})),
        sfx_event=data.get("sfx_event", ""),
        modifiers=dict(data.get("modifiers", {})),
        category_restrictions=list(data.get("category_restrictions", [])),
        notes=data.get("notes", ""),
        overridden_fields=set(data.get("overridden_fields", [])),
        override_notes=dict(data.get("override_notes", {})),
    )


# Public names are shared with hardpoint_config_store (embedded weapon block);
# the old private names stay as aliases.
_config_to_dict = config_to_dict
_dict_to_config = dict_to_config


def load_configs(path: str = DEFAULT_PATH) -> list[WeaponConfig]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    return [dict_to_config(entry) for entry in data.get("configs", [])]


def save_configs(configs: list[WeaponConfig], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "configs": [config_to_dict(c) for c in configs]}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
