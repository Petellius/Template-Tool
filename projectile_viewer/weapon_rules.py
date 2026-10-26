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
    "fire_range",
    "fire_cone_width",
    "fire_cone_height",
    "turret_rotate_speed",
    "projectile",
)

# RULE_FIELDS whose 0.0 / "" default means "this template doesn't define it"
# - apply_rule leaves the config's own (seeded) value alone for these instead
# of zeroing/blanking it, so templates saved before these fields existed
# keep behaving exactly as they did.
_UNSET_MEANS_SKIP = ("fire_range", "fire_cone_width", "fire_cone_height", "turret_rotate_speed")

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "weapon_rules.json"
)
SCHEMA_VERSION = 2


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
    fire_range: float = 0.0
    fire_cone_width: float = 0.0
    fire_cone_height: float = 0.0
    turret_rotate_speed: float = 0.0
    # The projectile weapons built from this template fire by default; applied
    # to a config's source_projectile_name (callers re-seed damage after).
    default_projectile: str = ""
    # "Space", "Land" or "" (applies to either). Organisational only - it
    # filters the template list and the category choices in the editor, and
    # is deliberately not in RULE_FIELDS (never copied onto a config).
    theatre: str = ""


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
        elif name == "projectile":
            if rule.default_projectile:
                config.source_projectile_name = rule.default_projectile
        elif name in _UNSET_MEANS_SKIP:
            value = getattr(rule, name)
            if value:
                setattr(config, name, value)
        else:
            setattr(config, name, getattr(rule, name))


def rule_from_config(config: WeaponConfig, category: str, theatre: str = "", include_projectile: bool = False) -> WeaponRule:
    """Captures a WeaponConfig's rule-governed fields into a new template
    (the reverse of apply_rule). `include_projectile` also stores the
    config's source projectile as the template's default projectile -
    applying such a template to other weapons swaps their projectile."""
    return WeaponRule(
        category=category,
        accuracy_by_category=dict(config.accuracy_by_category),
        fire_min_recharge=config.fire_min_recharge,
        fire_max_recharge=config.fire_max_recharge,
        fire_pulse_count=config.fire_pulse_count,
        fire_pulse_delay=config.fire_pulse_delay,
        sfx_event=config.sfx_event,
        modifiers=dict(config.modifiers),
        category_restrictions=list(config.category_restrictions),
        fire_range=config.fire_range,
        fire_cone_width=config.fire_cone_width,
        fire_cone_height=config.fire_cone_height,
        turret_rotate_speed=config.turret_rotate_speed,
        default_projectile=config.source_projectile_name if include_projectile else "",
        theatre=theatre,
    )


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
        "fire_range": rule.fire_range,
        "fire_cone_width": rule.fire_cone_width,
        "fire_cone_height": rule.fire_cone_height,
        "turret_rotate_speed": rule.turret_rotate_speed,
        "default_projectile": rule.default_projectile,
        "theatre": rule.theatre,
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
        fire_range=data.get("fire_range", 0.0),
        fire_cone_width=data.get("fire_cone_width", 0.0),
        fire_cone_height=data.get("fire_cone_height", 0.0),
        turret_rotate_speed=data.get("turret_rotate_speed", 0.0),
        default_projectile=data.get("default_projectile", ""),
        theatre=data.get("theatre", ""),
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
