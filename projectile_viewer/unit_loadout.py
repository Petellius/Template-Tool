"""Builds a combat-relevant summary of a Unit for the Battle Simulator:
its targetable hardpoints (grouped by identical loadout), combined health,
and shield/armor profile.

A Unit's <HardPoints> tag is a single comma-separated list of hardpoint
names (confirmed on the Venator), and each referenced HardPoint's own
Is_Targetable flag decides whether it's a valid target at all - a turret
hardpoint is commonly non-targetable itself (damage routes to the hull),
while hull/engine/hangar/torpedo-tube/light-cannon hardpoints usually are.
"""

import re
from dataclasses import dataclass

from .hardpoint_data import extract_fields
from .inheritance import InheritanceCycleError, merge_chain, resolve_chain
from .weapon_analysis import WeaponStats, analyze
from .weapon_config import (
    CONTEXT_UNIT_WEAPON,
    WeaponConfig,
    seed_from_hardpoint,
    seed_from_projectile,
    seed_from_unit_weapon,
)

UNIT_WEAPON_FIELD = "Projectile_Types"

HARDPOINTS_FIELD_NAMES = ("HardPoints", "Hardpoints")
_TRAILING_DIGITS = re.compile(r"\d+$")


def parse_hardpoint_names(raw: str) -> list[str]:
    """Splits a Unit's <HardPoints> field text on commas, trimming
    whitespace and dropping blanks. XML comments used to disable entries
    (e.g. wrapping a hardpoint name in <!-- --> in the source file) are
    already invisible here - ElementTree drops comment content entirely
    before .text is even built, so no extra stripping is needed.
    """
    if not raw:
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


def _strip_trailing_index(name: str) -> str:
    return _TRAILING_DIGITS.sub("", name)


def _is_targetable(fields: dict[str, list[str]]) -> bool:
    values = fields.get("Is_Targetable")
    if not values:
        return True  # absent tag defaults to targetable - every non-targetable hardpoint seen sets it explicitly
    return values[0].strip().lower() not in ("no", "false", "0")


def _is_weapon(fields: dict[str, list[str]]) -> bool:
    return bool(fields.get("Fire_Projectile_Type")) or bool(fields.get("Projectile_Damage"))


@dataclass
class HardpointGroup:
    label: str
    count: int
    is_weapon: bool
    is_targetable: bool
    total_health: float
    weapon_config: WeaponConfig | None = None
    stats: WeaponStats | None = None


@dataclass
class UnitLoadout:
    unit_name: str
    tactical_health: float
    armor_type: str
    shield_points: float
    shield_armor_type: str
    shield_refresh_rate: float
    groups: list[HardpointGroup]

    @property
    def weapon_groups(self) -> list[HardpointGroup]:
        return [g for g in self.groups if g.is_weapon]

    @property
    def combined_hardpoint_health(self) -> float:
        """Only targetable hardpoints count toward this total - a
        non-targetable weapon turret's own "health" isn't a separate,
        destructible pool (damage against it isn't possible; it can't be
        selected as an impact point), so including it would overstate how
        much punishment the unit can actually absorb.
        """
        return sum(g.total_health * g.count for g in self.groups if g.is_targetable)


def _to_float(text: str | None, default: float = 0.0) -> float:
    if not text:
        return default
    try:
        return float(text.strip())
    except ValueError:
        return default


def build_loadout(
    unit_name: str,
    unit_entries: dict,
    hardpoint_entries: dict,
    projectile_entries: dict,
) -> UnitLoadout:
    chain = resolve_chain(unit_entries, unit_name)
    resolved = merge_chain(unit_entries, chain)

    hardpoints_field = next((f for f in HARDPOINTS_FIELD_NAMES if f in resolved), None)
    hardpoint_names = parse_hardpoint_names(resolved[hardpoints_field].value) if hardpoints_field else []

    grouped: dict[str, HardpointGroup] = {}
    for name in hardpoint_names:
        entry = hardpoint_entries.get(name)
        if entry is None:
            continue
        fields = extract_fields(entry.element)
        is_weapon = _is_weapon(fields)
        targetable = _is_targetable(fields)
        if not is_weapon and not targetable:
            # A non-targetable, non-weapon hardpoint (e.g. a disabled shield-
            # generator placeholder) isn't a real target and doesn't fire -
            # nothing useful to show. Weapons are kept even when the turret
            # itself isn't targetable (damage still routes to the hull), and
            # targetable structural hardpoints are always kept.
            continue

        label = _strip_trailing_index(name)
        health = _to_float((fields.get("Health") or [None])[0])

        existing = grouped.get(label)
        if existing is not None:
            existing.count += 1
            continue

        config = None
        stats = None
        if is_weapon:
            config = WeaponConfig(name=label, source_hardpoint_name=name)
            seed_from_hardpoint(config, fields)
            projectile_name = (fields.get("Fire_Projectile_Type") or [None])[0]
            if projectile_name and projectile_name in projectile_entries:
                config.source_projectile_name = projectile_name
                try:
                    proj_chain = resolve_chain(projectile_entries, projectile_name)
                    proj_resolved = merge_chain(projectile_entries, proj_chain)
                    seed_from_projectile(config, proj_resolved)
                except InheritanceCycleError:
                    pass
            stats = analyze(config)

        grouped[label] = HardpointGroup(
            label=label, count=1, is_weapon=is_weapon, is_targetable=targetable, total_health=health,
            weapon_config=config, stats=stats,
        )

    return UnitLoadout(
        unit_name=unit_name,
        tactical_health=_to_float(resolved["Tactical_Health"].value if "Tactical_Health" in resolved else None),
        armor_type=resolved["Armor_Type"].value if "Armor_Type" in resolved else "",
        shield_points=_to_float(resolved["Shield_Points"].value if "Shield_Points" in resolved else None),
        shield_armor_type=resolved["Shield_Armor_Type"].value if "Shield_Armor_Type" in resolved else "",
        shield_refresh_rate=_to_float(
            resolved["Shield_Refresh_Rate"].value if "Shield_Refresh_Rate" in resolved else None
        ),
        groups=sorted(grouped.values(), key=lambda g: g.label),
    )


def build_unit_weapon_group(
    unit_name: str,
    unit_entries: dict,
    projectile_entries: dict,
) -> HardpointGroup | None:
    """Detects a unit's own direct (non-HardPoint) weapon, from
    Projectile_Types/Projectile_Fire_* fields written straight onto the Unit
    element itself (confirmed real schema on GroundInfantry, e.g.
    Stormtrooper/Scout_Trooper, and GroundVehicle, e.g. SPMAT_Walker - the
    latter proves a unit can have this AND HardPoint-based weapons at once).
    Returns None if the unit has no such field - most ships/vehicles don't.

    Self-sufficient like build_loadout (resolves the unit's own chain
    itself) rather than taking a pre-resolved field map, since
    seed_from_unit_weapon needs the raw chain - not just merge_chain's
    flattened result - to correctly resolve a multi-category
    Targeting_Fire_Inaccuracy.
    """
    chain = resolve_chain(unit_entries, unit_name)
    resolved_fields = merge_chain(unit_entries, chain)

    types_field = resolved_fields.get(UNIT_WEAPON_FIELD)
    if types_field is None or not types_field.value.strip():
        return None

    # Usually exactly one projectile; rare hero/underworld units list more
    # (e.g. "Proj_Hand_Blaster_Bossk, Proj_Bossk_Plasma_Grenade") - only the
    # first is modeled, matching how the rest of this tool reduces
    # multi-value fields to one representative value.
    projectile_name = types_field.value.split(",")[0].strip()

    label = "Direct Weapon"
    config = WeaponConfig(name=label, unit_name=unit_name, context=CONTEXT_UNIT_WEAPON)
    seed_from_unit_weapon(config, resolved_fields, unit_entries, chain)

    if projectile_name and projectile_name in projectile_entries:
        config.source_projectile_name = projectile_name
        try:
            proj_chain = resolve_chain(projectile_entries, projectile_name)
            proj_resolved = merge_chain(projectile_entries, proj_chain)
            seed_from_projectile(config, proj_resolved)
        except InheritanceCycleError:
            pass

    return HardpointGroup(
        label=label, count=1, is_weapon=True, is_targetable=True, total_health=0.0,
        weapon_config=config, stats=analyze(config),
    )
