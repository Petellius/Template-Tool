"""User-authored default presets for a Weapon Config's rate-of-fire/accuracy/
firing-SFX fields, keyed by a free-text weapon category (e.g. "Heavy
Turbolasers").

Real AGD hardpoint data shows these values vary too much even for hardpoints
firing the identical projectile (pulse count 1 vs 2 vs 4, accuracy 8 vs 36,
faction-specific SFX) to be inferred automatically - so a rule is just a
preset the user defines once and applies deliberately, not something derived
from existing game data.
"""

import json
import os
from dataclasses import dataclass, field

from .weapon_config import WeaponConfig

RULE_FIELDS = (
    "accuracy",
    "fire_min_recharge",
    "fire_max_recharge",
    "fire_pulse_count",
    "fire_pulse_delay",
    "sfx_event",
    "modifiers",
    "category_restrictions",
)

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "weapon_rules.json"
)
SCHEMA_VERSION = 1


@dataclass
class WeaponRule:
    category: str
    accuracy_by_category: dict[str, float] = field(default_factory=dict)
    fire_min_recharge: float = 0.0
    fire_max_recharge: float = 0.0
    fire_pulse_count: int = 1
    fire_pulse_delay: float = 0.0
    sfx_event: str = ""
    modifiers: dict[str, str] = field(default_factory=dict)
    category_restrictions: list[str] = field(default_factory=list)


def apply_rule(config: WeaponConfig, rule: WeaponRule) -> None:
    """Fills `config`'s RULE_FIELDS from `rule`, skipping anything already
    in `config.overridden_fields` (a user's hand-edit always wins). "accuracy"
    is the logical field name shared with overridden_fields/the UI's Reset
    button, but the actual attribute (on both WeaponConfig and WeaponRule) is
    accuracy_by_category - a dict, copied rather than aliased. "modifiers"
    and "category_restrictions" are likewise full replacements, not merges,
    for the same reason - a rule's own idea of e.g. what category
    restrictions apply should win outright, not blend with the seeded slot.
    """
    for name in RULE_FIELDS:
        if name in config.overridden_fields:
            continue
        if name == "accuracy":
            config.accuracy_by_category = dict(rule.accuracy_by_category)
        elif name == "modifiers":
            config.modifiers = dict(rule.modifiers)
        elif name == "category_restrictions":
            config.category_restrictions = list(rule.category_restrictions)
        else:
            setattr(config, name, getattr(rule, name))


def _rule_to_dict(rule: WeaponRule) -> dict:
    return {
        "category": rule.category,
        "accuracy_by_category": dict(rule.accuracy_by_category),
        "fire_min_recharge": rule.fire_min_recharge,
        "fire_max_recharge": rule.fire_max_recharge,
        "fire_pulse_count": rule.fire_pulse_count,
        "fire_pulse_delay": rule.fire_pulse_delay,
        "sfx_event": rule.sfx_event,
        "modifiers": dict(rule.modifiers),
        "category_restrictions": list(rule.category_restrictions),
    }


def _dict_to_rule(data: dict) -> WeaponRule:
    return WeaponRule(
        category=data.get("category", "Untitled"),
        accuracy_by_category=dict(data.get("accuracy_by_category", {})),
        fire_min_recharge=data.get("fire_min_recharge", 0.0),
        fire_max_recharge=data.get("fire_max_recharge", 0.0),
        fire_pulse_count=data.get("fire_pulse_count", 1),
        fire_pulse_delay=data.get("fire_pulse_delay", 0.0),
        sfx_event=data.get("sfx_event", ""),
        modifiers=dict(data.get("modifiers", {})),
        category_restrictions=list(data.get("category_restrictions", [])),
    )


def load_rules(path: str = DEFAULT_PATH) -> list[WeaponRule]:
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []

    return [_dict_to_rule(entry) for entry in data.get("rules", [])]


def save_rules(rules: list[WeaponRule], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {"version": SCHEMA_VERSION, "rules": [_rule_to_dict(r) for r in rules]}

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)
