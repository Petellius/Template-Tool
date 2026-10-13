"""Parses GAMECONSTANTS.XML for the damage-type vs armor/shield-type
multiplier matrix ("armour piercing percentages") and the global shield
recharge tick interval.

Unlike Projectile/HardPoint/Unit elements, the matrix is a flat list of
repeated <Damage_To_Armor_Mod> tags with comma-separated text content
(damage_type, target_type, multiplier) rather than a Name-keyed or
attribute-based schema, so it needs its own small parser.
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

FILE_BASENAME = "gameconstants"
DAMAGE_DEFAULT = "Damage_Default"
DEFAULT_SHIELD_RECHARGE_INTERVAL = 1.0


def is_game_constants_file(path: str) -> bool:
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.lower() == FILE_BASENAME


def find_game_constants_file(file_paths: list[str]) -> str | None:
    """Last match wins, same later-layer-overrides-earlier convention used
    everywhere else in this tool.
    """
    matches = [p for p in file_paths if is_game_constants_file(p)]
    return matches[-1] if matches else None


@dataclass
class DamageMatrix:
    entries: dict[tuple[str, str], float] = field(default_factory=dict)
    defaults: dict[str, float] = field(default_factory=dict)

    def multiplier(self, damage_type: str, target_type: str) -> float:
        if not damage_type or not target_type:
            return 1.0
        exact = self.entries.get((damage_type, target_type))
        if exact is not None:
            return exact
        return self.defaults.get(target_type, 1.0)


def all_target_types(matrix: DamageMatrix) -> list[str]:
    """Every target-type name the matrix knows about, from either an exact
    (damage_type, target_type) entry or a Damage_Default fallback. The raw
    schema never distinguishes "armor type" from "shield-armor type" - both
    are just target_type strings in the same Damage_To_Armor_Mod rows - so
    this one combined list is what backs both a "target armor" and a
    "target shield" picker.
    """
    return sorted({target_type for _, target_type in matrix.entries} | set(matrix.defaults))


def parse_damage_matrix(path: str) -> DamageMatrix:
    tree = ET.parse(path)
    matrix = DamageMatrix()

    for element in tree.getroot().iter("Damage_To_Armor_Mod"):
        text = (element.text or "").strip()
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 3:
            continue
        damage_type, target_type, multiplier_text = parts
        try:
            multiplier = float(multiplier_text)
        except ValueError:
            continue

        if damage_type == DAMAGE_DEFAULT:
            matrix.defaults[target_type] = multiplier
        else:
            matrix.entries[(damage_type, target_type)] = multiplier

    return matrix


def parse_shield_recharge_interval(path: str) -> float:
    tree = ET.parse(path)
    element = tree.getroot().find("ShieldRechargeIntervalInSecs")
    if element is None or not (element.text or "").strip():
        return DEFAULT_SHIELD_RECHARGE_INTERVAL
    try:
        return float(element.text.strip())
    except ValueError:
        return DEFAULT_SHIELD_RECHARGE_INTERVAL
