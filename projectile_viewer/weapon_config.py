"""Data model for a Weapon Config - a saved, editable set of "basic" combat
stats reduced from one of two real weapon schemas EAW/FoC units use:

- HardPoint-based (CONTEXT_HARDPOINT): damage lives on the Projectile fired
  via Fire_Projectile_Type; rate-of-fire lives on the standalone <HardPoint>
  element (Fire_Min/Max_Recharge_Seconds, Fire_Pulse_Count/Delay,
  Fire_Inaccuracy_Distance, Fire_SFXEvent). Confirmed on every ship/vehicle
  hardpoint (e.g. HardPoints_Republic_Venator.XML).
- Direct unit-weapon (CONTEXT_UNIT_WEAPON): fields written straight onto the
  Unit element itself, no separate element at all - Projectile_Types,
  Projectile_Fire_Recharge_Seconds (a SINGLE scalar, not a Min/Max pair),
  Projectile_Fire_Pulse_Count/Delay, Targeting_Fire_Inaccuracy. Confirmed on
  Stormtrooper/Scout_Trooper/Plex_Soldier (GROUNDINFANTRY.XML) and
  SPMAT_Walker (GROUNDVEHICLES.XML) - the latter proves a single unit can use
  BOTH schemas simultaneously (its own grenade weapon plus 4 HardPoint lasers).
  This schema has no dedicated firing-SFX tag at all.

`overridden_fields` tracks which of weapon_rules.RULE_FIELDS the user has
hand-edited, so seeding from a hardpoint/unit and applying a category rule
(weapon_rules.apply_rule) never silently clobber a value the user already
customized - both only ever touch fields NOT in this set. `override_notes`
holds an optional tooltip/reason string per overridden field name.
"""

from dataclasses import dataclass, field

from .weapon_modifiers import modifiers_for_context

CONTEXT_HARDPOINT = "hardpoint"
CONTEXT_ABILITY = "ability"
CONTEXT_UNIT_WEAPON = "unit_weapon"


@dataclass
class WeaponConfig:
    name: str
    unit_name: str = ""
    source_projectile_name: str = ""
    source_hardpoint_name: str = ""
    context: str = CONTEXT_HARDPOINT
    category: str = ""
    damage: float = 0.0
    damage_type: str = ""
    fire_min_recharge: float = 0.0
    fire_max_recharge: float = 0.0
    fire_pulse_count: int = 1
    fire_pulse_delay: float = 0.0
    fire_range: float = 0.0
    accuracy_by_category: dict[str, float] = field(default_factory=dict)
    sfx_event: str = ""
    modifiers: dict[str, str] = field(default_factory=dict)
    category_restrictions: list[str] = field(default_factory=list)
    notes: str = ""
    overridden_fields: set[str] = field(default_factory=set)
    override_notes: dict[str, str] = field(default_factory=dict)


def to_float(text: str | None, default: float = 0.0) -> float:
    if not text:
        return default
    try:
        return float(text.strip())
    except ValueError:
        return default


def to_int(text: str | None, default: int = 1) -> int:
    if not text:
        return default
    try:
        return int(float(text.strip()))
    except ValueError:
        return default


def parse_category_value_pairs(raw_values: list[str]) -> dict[str, float]:
    """Parses a list of raw "Category, value" strings (as returned by
    hardpoint_data.extract_fields, which preserves every occurrence of a
    repeated tag) into a {category: value} dict - e.g.
    ["All, 25.0", "Structure, 18.0", "LandHero, 35.0"] ->
    {"All": 25.0, "Structure": 18.0, "LandHero": 35.0}. A later duplicate of
    the same category overrides the earlier one.
    """
    result: dict[str, float] = {}
    for raw in raw_values:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 2:
            continue
        category, value_text = parts
        result[category] = to_float(value_text, result.get(category, 0.0))
    return result


def resolve_category_value_field(entries: dict, chain: list[str], tag_name: str) -> dict[str, float]:
    """Like parse_category_value_pairs, but for a Unit field that must be
    resolved across a Variant_Of_Existing_Type chain. inheritance.merge_chain
    can't be reused here - it only keeps the LAST occurrence of a repeated
    tag per element, which would silently drop every category but one. This
    walks `chain` root-first and reads each element's own children directly,
    so a later element only overrides the categories it actually mentions -
    categories set on an earlier element and never revisited are preserved.
    """
    result: dict[str, float] = {}
    for link_name in chain:
        entry = entries.get(link_name)
        if entry is None:
            continue
        for child in entry.element:
            if child.tag != tag_name:
                continue
            parts = [p.strip() for p in (child.text or "").split(",")]
            if len(parts) != 2:
                continue
            category, value_text = parts
            result[category] = to_float(value_text, result.get(category, 0.0))
    return result


def parse_category_list(raw: str | None) -> list[str]:
    """Parses Fire_Category_Restrictions - a single tag holding a plain
    comma-separated list of category names (e.g. "Fighter, Bomber,
    Transport", or just "Air") - no value per category, unlike accuracy.
    Dedupes while preserving order.
    """
    if not raw:
        return []
    seen: dict[str, None] = {}
    for part in raw.split(","):
        category = part.strip()
        if category:
            seen[category] = None
    return list(seen)


def seed_from_projectile(config: WeaponConfig, resolved_fields: dict) -> None:
    """Fill in the damage-side "basic" fields from a Projectile's resolved
    field map (as returned by inheritance.merge_chain - values are
    ResolvedField, so `.value` is the actual string). Skips any field
    already in `config.overridden_fields` - a hardpoint/direct-weapon can
    carry its own Projectile_Damage/Damage_Type override on top of the
    projectile it references (confirmed real, e.g. HP_Victory_Weapon_02),
    so re-seeding must never clobber a value the user deliberately set.
    """
    overridden = config.overridden_fields
    if "damage" not in overridden and "Projectile_Damage" in resolved_fields:
        config.damage = to_float(resolved_fields["Projectile_Damage"].value, config.damage)
    if "damage_type" not in overridden and "Damage_Type" in resolved_fields:
        config.damage_type = resolved_fields["Damage_Type"].value or config.damage_type


def seed_from_hardpoint(config: WeaponConfig, fields: dict[str, list[str]]) -> None:
    """Fill in the rate-of-fire "basic" fields from a HardPoint's direct
    field map (as returned by hardpoint_data.extract_fields - values are
    lists of raw strings, one per occurrence of that tag). Skips any field
    already in `config.overridden_fields` - re-seeding never clobbers a
    hand-edited value.
    """
    def first(tag: str) -> str | None:
        values = fields.get(tag)
        return values[0] if values else None

    overridden = config.overridden_fields

    if "fire_min_recharge" not in overridden:
        config.fire_min_recharge = to_float(first("Fire_Min_Recharge_Seconds"), config.fire_min_recharge)
    if "fire_max_recharge" not in overridden:
        config.fire_max_recharge = to_float(first("Fire_Max_Recharge_Seconds"), config.fire_max_recharge)
    if "fire_pulse_count" not in overridden:
        config.fire_pulse_count = to_int(first("Fire_Pulse_Count"), config.fire_pulse_count)
    if "fire_pulse_delay" not in overridden:
        config.fire_pulse_delay = to_float(first("Fire_Pulse_Delay_Seconds"), config.fire_pulse_delay)
    if "accuracy" not in overridden:
        raw_pairs = fields.get("Fire_Inaccuracy_Distance", []) + fields.get("Targeting_Fire_Inaccuracy", [])
        config.accuracy_by_category = parse_category_value_pairs(raw_pairs)
    if "sfx_event" not in overridden:
        config.sfx_event = first("Fire_SFXEvent") or config.sfx_event

    if "fire_range" not in overridden:
        config.fire_range = to_float(first("Fire_Range_Distance"), config.fire_range)
    if not config.source_projectile_name and first("Projectile_Damage"):
        # No external projectile - this hardpoint fires with its own flat
        # damage value (seen on some ability-style/direct-hit hardpoints).
        config.damage = to_float(first("Projectile_Damage"), config.damage)

    if not config.category_restrictions:
        config.category_restrictions = parse_category_list(first("Fire_Category_Restrictions"))

    # Optional behavior modifiers (Allow_Opportunity_Fire_*, Fire_When_*, ...)
    # - never overwrites a value the user already added/edited. Stored under
    # each spec's schema-agnostic key, not the raw tag name, since the same
    # concept can be named differently on the other weapon schema.
    for spec in modifiers_for_context(CONTEXT_HARDPOINT):
        if spec.key in config.modifiers:
            continue
        raw = first(spec.hardpoint_field)
        if raw is not None:
            config.modifiers[spec.key] = raw


def seed_from_unit_weapon(config: WeaponConfig, resolved_fields: dict, entries: dict, chain: list[str]) -> None:
    """Fill in the rate-of-fire "basic" fields from a Unit's own resolved
    field map (as returned by inheritance.merge_chain - values are
    ResolvedField, so `.value` is the actual string) for the direct
    unit-weapon schema (Projectile_Types/Projectile_Fire_*), as opposed to
    seed_from_hardpoint's standalone <HardPoint> schema. Skips any field
    already in `config.overridden_fields`.

    Projectile_Fire_Recharge_Seconds is a single scalar in this schema (no
    Min/Max range) - it's written into both fire_min_recharge and
    fire_max_recharge so weapon_analysis.analyze() needs no special-casing;
    a fixed recharge just yields identical min/avg/max cycle times.

    `entries`/`chain` (the same inputs inheritance.resolve_chain/merge_chain
    take) are needed for accuracy specifically: merge_chain collapses
    repeated tags on one element to the LAST occurrence, which would drop
    all but one of a multi-category Targeting_Fire_Inaccuracy (e.g.
    Infantry/Vehicle/Air/Structure) - resolve_category_value_field walks the
    chain itself instead, to keep every category.
    """
    def field_value(tag: str) -> str | None:
        resolved_field = resolved_fields.get(tag)
        return resolved_field.value if resolved_field is not None else None

    overridden = config.overridden_fields

    if "fire_min_recharge" not in overridden and "fire_max_recharge" not in overridden:
        recharge = to_float(field_value("Projectile_Fire_Recharge_Seconds"), config.fire_min_recharge)
        config.fire_min_recharge = recharge
        config.fire_max_recharge = recharge
    if "fire_pulse_count" not in overridden:
        config.fire_pulse_count = to_int(field_value("Projectile_Fire_Pulse_Count"), config.fire_pulse_count)
    if "fire_pulse_delay" not in overridden:
        config.fire_pulse_delay = to_float(field_value("Projectile_Fire_Pulse_Delay_Seconds"), config.fire_pulse_delay)
    if "accuracy" not in overridden:
        config.accuracy_by_category = resolve_category_value_field(entries, chain, "Targeting_Fire_Inaccuracy")
    # This schema has no per-weapon range/SFX tag - both live on the unit
    # itself instead (Targeting_Max_Attack_Distance/SFXEvent_Fire, confirmed
    # real on Scout_Trooper/Stormtrooper), already resolved through the same
    # Variant_Of_Existing_Type chain as everything else in `resolved_fields`.
    if "fire_range" not in overridden:
        config.fire_range = to_float(field_value("Targeting_Max_Attack_Distance"), config.fire_range)
    if "sfx_event" not in overridden:
        config.sfx_event = field_value("SFXEvent_Fire") or config.sfx_event

    # Optional behavior modifiers, under their direct-unit-weapon field names
    # (some renamed vs the HardPoint schema, e.g. Fire_Weapon_When_Deployed
    # vs Fire_When_Deployed) - stored under the schema-agnostic key, same as
    # seed_from_hardpoint. None of these are repeated/multi-category tags,
    # so a plain single-value read via resolved_fields is enough - no
    # chain-walking needed here.
    for spec in modifiers_for_context(CONTEXT_UNIT_WEAPON):
        if spec.key in config.modifiers:
            continue
        raw = field_value(spec.unit_weapon_field)
        if raw is not None:
            config.modifiers[spec.key] = raw

    if not config.category_restrictions:
        config.category_restrictions = parse_category_list(field_value("Fire_Category_Restrictions"))
