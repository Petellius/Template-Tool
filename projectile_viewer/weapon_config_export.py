"""Builds real game XML from WeaponConfigs, for the two real weapon schemas
(see weapon_config.py's module docstring). Export is always an explicit,
opt-in action (the caller writes the returned string to a user-chosen file)
- this module never touches an existing mod file itself.

HardPoint elements have NO inheritance at all (confirmed when the Hardpoints
tab was first built - every hardpoint is fully self-contained), so an
exported HardPoint is always a new, independent entry, never a patch of an
existing one - a Variant_Of_Existing_Type tag there would just be ignored by
the game. Units, by contrast, genuinely support Variant_Of_Existing_Type, so
an exported unit-weapon fragment correctly uses it to create a new unit
variant that inherits everything except the weapon fields from the original.

Markup is hand-built (not ElementTree+minidom) so it can match the tabbed,
per-field-commented, blank-line-grouped style of real hand-authored AGD
files - minidom's generic pretty-printer has no way to place a specific
comment above a specific field or leave a blank line between groups.
"""

from xml.sax.saxutils import escape, quoteattr

from .weapon_config import WeaponConfig
from .weapon_modifiers import MODIFIERS_BY_KEY


def _indent(depth: int) -> str:
    return "\t" * depth


def _field(depth: int, tag: str, value) -> str:
    return f"{_indent(depth)}<{tag}>{escape(str(value))}</{tag}>"


def _padded_field(depth: int, tag: str, value) -> str:
    return f"{_indent(depth)}<{tag}> {escape(str(value))} </{tag}>"


def _comment(depth: int, text: str) -> str:
    return f"{_indent(depth)}<!-- {text} -->"


def _join_blocks(blocks: list[list[str]]) -> list[str]:
    """Joins non-empty line-groups with exactly one blank line between them,
    silently dropping any group with nothing to emit (e.g. no accuracy
    entries at all) so no dangling blank line or empty comment appears.
    """
    lines: list[str] = []
    for block in blocks:
        if not block:
            continue
        if lines:
            lines.append("")
        lines.extend(block)
    return lines


def _extras_block(
    depth: int, category_restrictions: list[str], modifiers: dict[str, str], field_attr: str,
) -> list[str]:
    """The trailing, uncommented block shared by both schemas - Fire_Category_Restrictions
    then whichever modifiers apply to this schema (`field_attr` is
    "hardpoint_field" or "unit_weapon_field"), matching the real templates
    (neither is commented in the user's examples).
    """
    lines: list[str] = []
    if category_restrictions:
        lines.append(_padded_field(depth, "Fire_Category_Restrictions", ", ".join(category_restrictions)))
    for key, value in modifiers.items():
        spec = MODIFIERS_BY_KEY.get(key)
        field_name = getattr(spec, field_attr, None) if spec is not None else None
        if field_name is not None:
            lines.append(_field(depth, field_name, value))
    return lines


def _build_hardpoint_lines(config: WeaponConfig, depth: int) -> list[str]:
    """A weapon-only <HardPoint> block: fire-rate fields plus damage. When
    there's no external Projectile, damage is the only source of truth and
    is always written if set (the ability-style/from-scratch case). When a
    Projectile IS connected, damage/damage_type normally live there instead
    - a HardPoint only needs its own Projectile_Damage/Damage_Type when the
    user has deliberately overridden them for this specific mount (real,
    confirmed pattern - e.g. HP_Victory_Weapon_02 sets both alongside its
    Fire_Projectile_Type), tracked via `overridden_fields`. Type/Health/
    Is_Targetable/geometry fields aren't tracked by WeaponConfig and can't be
    inherited (HardPoint has no Variant_Of_Existing_Type support) - a
    comment flags this explicitly instead of emitting a tag the game would
    silently ignore.
    """
    seed = config.source_hardpoint_name or config.source_projectile_name or "(none)"
    header = _comment(depth, (
        f"Weapon-only fragment (seeded from {seed}). HardPoint has no inheritance - "
        "Type/Health/Is_Targetable/geometry fields must be added by hand before use."
    ))

    core = [header, _comment(depth, "Projectile type, this defines range, damage and VFX of the projectile")]
    if config.source_projectile_name:
        core.append(_field(depth, "Fire_Projectile_Type", config.source_projectile_name))
        if "damage" in config.overridden_fields:
            core.append(_field(depth, "Projectile_Damage", config.damage))
    elif config.damage:
        core.append(_field(depth, "Projectile_Damage", config.damage))
    if "damage_type" in config.overridden_fields:
        core.append(_field(depth, "Damage_Type", config.damage_type))

    core.append(_comment(depth, "Reload Rate"))
    core.append(_field(depth, "Fire_Min_Recharge_Seconds", config.fire_min_recharge))
    core.append(_field(depth, "Fire_Max_Recharge_Seconds", config.fire_max_recharge))

    core.append(_comment(depth, "Burst Fire Rate"))
    core.append(_field(depth, "Fire_Pulse_Count", config.fire_pulse_count))
    core.append(_field(depth, "Fire_Pulse_Delay_Seconds", config.fire_pulse_delay))

    if config.fire_range:
        core.append(_comment(depth, "Weapon Range"))
        core.append(_field(depth, "Fire_Range_Distance", config.fire_range))

    if config.sfx_event:
        core.append(_comment(depth, "Weapon Fire Sound Effect"))
        core.append(_field(depth, "Fire_SFXEvent", config.sfx_event))

    accuracy: list[str] = []
    if config.accuracy_by_category:
        accuracy.append(_comment(depth, "Weapon Accuracy: Higher numbers are less accurate."))
        for category, value in config.accuracy_by_category.items():
            accuracy.append(_padded_field(depth, "Fire_Inaccuracy_Distance", f"{category}, {value}"))

    extras = _extras_block(depth, config.category_restrictions, config.modifiers, "hardpoint_field")

    return _join_blocks([core, accuracy, extras])


def _build_unit_weapon_lines(config: WeaponConfig, depth: int) -> list[str]:
    """A new unit variant carrying just the direct-weapon fields
    (Projectile_Types/Projectile_Fire_*/Targeting_Fire_Inaccuracy) - unlike
    HardPoint, Units genuinely support Variant_Of_Existing_Type, so this
    correctly inherits everything else (model, health, hardpoints, ...) from
    `config.unit_name`. No Fire_SFXEvent - this schema has no dedicated
    firing-SFX tag (confirmed: these units reuse a generic, weapon-unrelated
    SFXEvent_Fire tag instead). Projectile_Damage/Damage_Type use the SAME
    field names as the HardPoint schema (confirmed on GROUNDVEHICLES.XML's
    Snowspeeder entry) and the same override-only-when-edited condition.
    Unlike HardPoint's combined "Burst Fire Rate" comment, the real
    direct-weapon template comments pulse count and pulse delay separately
    ("Burst Rate" / "Fire Rate").
    """
    core: list[str] = []
    if config.unit_name:
        core.append(_field(depth, "Variant_Of_Existing_Type", config.unit_name))

    core.append(_comment(depth, "Projectile type, this defines range, damage and VFX of the projectile"))
    if config.source_projectile_name:
        core.append(_field(depth, "Projectile_Types", config.source_projectile_name))
        if "damage" in config.overridden_fields:
            core.append(_field(depth, "Projectile_Damage", config.damage))
    elif config.damage:
        core.append(_field(depth, "Projectile_Damage", config.damage))
    if "damage_type" in config.overridden_fields:
        core.append(_field(depth, "Damage_Type", config.damage_type))

    # Projectile_Fire_Recharge_Seconds is a single scalar in this schema (no
    # Min/Max range) - fire_min_recharge and fire_max_recharge are kept
    # equal by seed_from_unit_weapon, so either one is the value to write.
    core.append(_comment(depth, "Reload Rate"))
    core.append(_field(depth, "Projectile_Fire_Recharge_Seconds", config.fire_min_recharge))

    core.append(_comment(depth, "Burst Rate"))
    core.append(_field(depth, "Projectile_Fire_Pulse_Count", config.fire_pulse_count))

    core.append(_comment(depth, "Fire Rate"))
    core.append(_field(depth, "Projectile_Fire_Pulse_Delay_Seconds", config.fire_pulse_delay))

    # Range/fire-sound both live on the unit itself here (Targeting_Max_Attack_Distance/
    # SFXEvent_Fire), not on the weapon - the new variant already inherits
    # both from its base unit via Variant_Of_Existing_Type, so only emit
    # them when the user has deliberately overridden the seeded value.
    if "fire_range" in config.overridden_fields:
        core.append(_field(depth, "Targeting_Max_Attack_Distance", config.fire_range))
    if "sfx_event" in config.overridden_fields:
        core.append(_field(depth, "SFXEvent_Fire", config.sfx_event))

    accuracy: list[str] = []
    if config.accuracy_by_category:
        accuracy.append(_comment(depth, "Weapon Accuracy: Higher numbers are less accurate"))
        for category, value in config.accuracy_by_category.items():
            accuracy.append(_padded_field(depth, "Targeting_Fire_Inaccuracy", f"{category}, {value}"))

    extras = _extras_block(depth, config.category_restrictions, config.modifiers, "unit_weapon_field")

    return _join_blocks([core, accuracy, extras])


def _wrap(tag: str, name: str, depth: int, lines: list[str]) -> str:
    body = "\n".join(lines)
    open_tag = f'{_indent(depth)}<{tag} Name={quoteattr(name)}>'
    close_tag = f"{_indent(depth)}</{tag}>"
    return f"{open_tag}\n{body}\n{close_tag}"


def build_hardpoints_file_xml(configs: list[WeaponConfig]) -> str:
    """Wraps every config's <HardPoint> element under a <HardPoints> root,
    matching the real file convention (e.g. HardPoints_Republic_Venator.XML).
    """
    parts = [_wrap("HardPoint", c.name, 1, _build_hardpoint_lines(c, 2)) for c in configs]
    return "<HardPoints>\n" + "\n".join(parts) + "\n</HardPoints>\n"


def build_unit_weapons_file_xml(base_unit_tag: str, configs: list[WeaponConfig]) -> str:
    """Wraps every config's unit-variant element under a <{base_unit_tag}_Units>
    root, matching the real file convention (e.g. GroundInfantry_Units).
    """
    root_tag = f"{base_unit_tag}_Units"
    parts = [_wrap(base_unit_tag, c.name, 1, _build_unit_weapon_lines(c, 2)) for c in configs]
    return f"<{root_tag}>\n" + "\n".join(parts) + f"\n</{root_tag}>\n"
