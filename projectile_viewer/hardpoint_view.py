"""Logic behind the Unit Hardpoint Viewer: reads every hardpoint a unit
references, groups them (by assigned Hardpoint Config, else by similarity),
turns a hardpoint into a HardpointConfig, and compares a hardpoint's real
XML against the config it's assigned to.

Deliberately separate from unit_loadout.build_loadout, which the Battle Sim
relies on and which intentionally drops non-weapon, non-targetable
hardpoints - the viewer must show *every* hardpoint.
"""

from dataclasses import dataclass, field

from .hardpoint_config import KIND_NON_WEAPON, KIND_WEAPON, HardpointConfig
from .hardpoint_data import extract_fields
from .inheritance import InheritanceCycleError, merge_chain, resolve_chain
from .unit_loadout import HARDPOINTS_FIELD_NAMES, _is_weapon, _strip_trailing_index, parse_hardpoint_names
from .weapon_config import (
    CONTEXT_HARDPOINT, WeaponConfig, parse_category_list, parse_category_value_pairs, seed_from_hardpoint,
    seed_from_projectile, to_float,
)
from .weapon_modifiers import modifiers_for_context

# Per-placement fields: they differ for every instance of an otherwise
# identical hardpoint (e.g. the Venator's eight turrets each attach their own
# VenatorDTL_0N.ALO copy to a different Base_0N bone), so they never take
# part in grouping or comparison.
PLACEMENT_TAGS = ("Attachment_Bone", "Collision_Mesh", "Model_To_Attach")
# Fire bones are placement too - EXCEPT on a turret, where they name a bone
# inside the turret's own model (MUZZLEA_00) and are the same on every mount.
FIRE_BONE_TAGS = ("Fire_Bone_A", "Fire_Bone_B")

_YES = ("yes", "true", "1")
_NO = ("no", "false", "0")


@dataclass
class UnitHardpoint:
    name: str
    fields: dict[str, list[str]]
    order: int
    kind: str
    signature: tuple


@dataclass
class ViewGroup:
    key: tuple
    label: str
    kind: str
    members: list[UnitHardpoint]
    config_name: str = ""  # assigned Hardpoint Config ("" when grouped by similarity)

    @property
    def count(self) -> int:
        return len(self.members)


@dataclass
class Mismatch:
    field: str
    actual: str
    expected: str


# -- normalisation ---------------------------------------------------------------------------------


def _norm(value) -> str:
    """Canonical text for comparing hardpoint XML text against config values:
    case-insensitive, Yes/No/True/False/1/0 unified, numbers compared
    numerically (so "6000" == "6000.0")."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    text = str(value).strip()
    lowered = text.lower()
    if lowered in _YES:
        return "yes"
    if lowered in _NO:
        return "no"
    try:
        number = float(text)
    except ValueError:
        return lowered
    return repr(int(number)) if number == int(number) else repr(number)


def _truthy(text: str) -> bool:
    return _norm(text) == "yes"


def _first(fields: dict[str, list[str]], tag: str) -> str:
    values = fields.get(tag)
    return values[0] if values else ""


def hardpoint_kind(fields: dict[str, list[str]]) -> str:
    hp_type = _first(fields, "Type").upper()
    if hp_type.startswith("HARD_POINT_WEAPON") or _is_weapon(fields):
        return KIND_WEAPON
    return KIND_NON_WEAPON


def placement_tags(fields: dict[str, list[str]]) -> tuple[str, ...]:
    if _truthy(_first(fields, "Is_Turret")):
        return PLACEMENT_TAGS
    return PLACEMENT_TAGS + FIRE_BONE_TAGS


def hardpoint_signature(fields: dict[str, list[str]]) -> tuple:
    """Everything that defines what *kind* of hardpoint this is, ignoring
    per-placement bones. Tags are sorted so source order doesn't matter, but
    repeated tags (per-category accuracy) keep their own order."""
    items = []
    skipped = placement_tags(fields)
    for tag in sorted(fields):
        if tag in skipped:
            continue
        items.append((tag, tuple(_norm(v) for v in fields[tag])))
    return tuple(items)


# -- reading a unit's hardpoints -------------------------------------------------------------------


def read_unit_hardpoints(
    unit_name: str, unit_entries: dict, hardpoint_entries: dict,
) -> tuple[list[UnitHardpoint], list[str]]:
    """Every hardpoint the unit lists, in the unit's own order (a dummy
    hardpoint must come first in the game's list, so order is meaningful),
    plus the names it references that no loaded file defines."""
    try:
        resolved = merge_chain(unit_entries, resolve_chain(unit_entries, unit_name))
    except InheritanceCycleError:
        return [], []

    list_field = next((f for f in HARDPOINTS_FIELD_NAMES if f in resolved), None)
    names = parse_hardpoint_names(resolved[list_field].value) if list_field else []

    hardpoints: list[UnitHardpoint] = []
    missing: list[str] = []
    seen: set[str] = set()
    for order, name in enumerate(names):
        if name in seen:
            continue
        seen.add(name)
        entry = hardpoint_entries.get(name)
        if entry is None:
            missing.append(name)
            continue
        fields = extract_fields(entry.element)
        hardpoints.append(UnitHardpoint(
            name=name, fields=fields, order=order, kind=hardpoint_kind(fields),
            signature=hardpoint_signature(fields),
        ))
    return hardpoints, missing


def _common_label(names: list[str]) -> str:
    stems = [_strip_trailing_index(n).rstrip("_") for n in names]
    if len(set(stems)) == 1:
        return stems[0]
    prefix = stems[0]
    for stem in stems[1:]:
        while prefix and not stem.startswith(prefix):
            prefix = prefix[:-1]
    prefix = prefix.rstrip("_0123456789")
    return prefix or stems[0]


def group_hardpoints(
    hardpoints: list[UnitHardpoint], assignments: dict[str, str], configs: dict[str, HardpointConfig],
) -> list[ViewGroup]:
    """Groups by assigned Hardpoint Config first, then by identical
    signature. Groups keep the order of their first member."""
    groups: dict[tuple, ViewGroup] = {}
    for hp in hardpoints:
        assigned = assignments.get(hp.name, "")
        key = ("config", assigned) if assigned else ("sim", hp.signature)
        group = groups.get(key)
        if group is None:
            group = ViewGroup(key=key, label="", kind=hp.kind, members=[], config_name=assigned)
            groups[key] = group
        group.members.append(hp)

    result = sorted(groups.values(), key=lambda g: g.members[0].order)
    for group in result:
        group.label = group.config_name or _common_label([m.name for m in group.members])
    return result


# -- hardpoint -> config ---------------------------------------------------------------------------


def config_from_hardpoint(
    fields: dict[str, list[str]], name: str, hardpoint_name: str = "", projectile_entries: dict | None = None,
    theatre: str = "",
) -> HardpointConfig:
    """Builds a HardpointConfig from one hardpoint's raw tag map. The weapon
    block is seeded exactly like the per-slot Weapon Configs are (hardpoint
    fields, then damage/damage type from the fired projectile)."""
    first = lambda tag: _first(fields, tag)  # noqa: E731
    kind = hardpoint_kind(fields)

    config = HardpointConfig(
        name=name, kind=kind, hp_type=first("Type") or HardpointConfig(name="").hp_type,
        tooltip_text=first("Tooltip_Text"), theatre=theatre,
        is_targetable=_truthy(first("Is_Targetable")), is_destroyable=_truthy(first("Is_Destroyable")),
        health=to_float(first("Health"), 1.0),
        death_explosion_particles=first("Death_Explosion_Particles"),
        death_explosion_sfx=first("Death_Explosion_SFXEvent"),
        damage_decal=first("Damage_Decal"), damage_particles=first("Damage_Particles"),
        model_to_attach=first("Model_To_Attach"), fire_bone_a=first("Fire_Bone_A"), fire_bone_b=first("Fire_Bone_B"),
        is_turret=_truthy(first("Is_Turret")), turret_bone_name=first("Turret_Bone_Name"),
        barrel_bone_name=first("Barrel_Bone_Name"), turret_rest_angle=first("Turret_Rest_Angle"),
        turret_rotation_offset=first("Turret_Rotation_Offset"),
        turret_rotate_extent_degrees=to_float(first("Turret_Rotate_Extent_Degrees")),
        turret_elevate_extent_degrees=to_float(first("Turret_Elevate_Extent_Degrees")),
        attachment_bone=first("Attachment_Bone"), collision_mesh=first("Collision_Mesh"),
    )

    weapon = WeaponConfig(name=name, context=CONTEXT_HARDPOINT, source_hardpoint_name=hardpoint_name)
    if kind == KIND_WEAPON:
        seed_from_hardpoint(weapon, fields)
        projectile = first("Fire_Projectile_Type")
        if projectile:
            weapon.source_projectile_name = projectile
            entries = projectile_entries or {}
            if projectile in entries:
                try:
                    seed_from_projectile(weapon, merge_chain(entries, resolve_chain(entries, projectile)))
                except InheritanceCycleError:
                    pass
    config.weapon = weapon
    return config


# -- comparison ------------------------------------------------------------------------------------

# (XML tag, HardpointConfig attribute) for the hardpoint-level fields compared.
_HARDPOINT_FIELDS = (
    ("Type", "hp_type"),
    ("Tooltip_Text", "tooltip_text"),
    ("Is_Targetable", "is_targetable"),
    ("Is_Destroyable", "is_destroyable"),
    ("Health", "health"),
    ("Death_Explosion_Particles", "death_explosion_particles"),
    ("Death_Explosion_SFXEvent", "death_explosion_sfx"),
    ("Damage_Decal", "damage_decal"),
    ("Damage_Particles", "damage_particles"),
    ("Fire_Bone_A", "fire_bone_a"),
    ("Fire_Bone_B", "fire_bone_b"),
    ("Is_Turret", "is_turret"),
    ("Turret_Bone_Name", "turret_bone_name"),
    ("Barrel_Bone_Name", "barrel_bone_name"),
    ("Turret_Rest_Angle", "turret_rest_angle"),
    ("Turret_Rotation_Offset", "turret_rotation_offset"),
    ("Turret_Rotate_Extent_Degrees", "turret_rotate_extent_degrees"),
    ("Turret_Elevate_Extent_Degrees", "turret_elevate_extent_degrees"),
)

# (XML tag, WeaponConfig attribute) for the weapon block's scalar fields.
_WEAPON_FIELDS = (
    ("Fire_Projectile_Type", "source_projectile_name"),
    ("Fire_Min_Recharge_Seconds", "fire_min_recharge"),
    ("Fire_Max_Recharge_Seconds", "fire_max_recharge"),
    ("Fire_Pulse_Count", "fire_pulse_count"),
    ("Fire_Pulse_Delay_Seconds", "fire_pulse_delay"),
    ("Fire_Range_Distance", "fire_range"),
    ("Fire_Cone_Width", "fire_cone_width"),
    ("Fire_Cone_Height", "fire_cone_height"),
    ("Turret_Rotate_Speed", "turret_rotate_speed"),
    ("Fire_SFXEvent", "sfx_event"),
)


def compare_to_config(fields: dict[str, list[str]], config: HardpointConfig) -> list[Mismatch]:
    """Differences between a unit hardpoint's real XML and the config it is
    assigned to. A tag the hardpoint doesn't write at all matches a config
    value that is empty or still at its dataclass default; a tag it does
    write must equal the config's value (numbers compared numerically,
    Yes/No/True/False unified). Placement bones are never compared.
    """
    mismatches: list[Mismatch] = []
    base = HardpointConfig(name="")

    def check(tag: str, expected_value, default_value):
        raw = _first(fields, tag)
        present = raw != ""
        expected_norm = _norm(expected_value)
        if not present:
            if expected_norm == "" or expected_norm == _norm(default_value):
                return
            mismatches.append(Mismatch(field=tag, actual="(not set)", expected=str(expected_value)))
        elif _norm(raw) != expected_norm:
            mismatches.append(Mismatch(
                field=tag, actual=raw, expected="(not set)" if expected_norm == "" else str(expected_value),
            ))

    skipped = placement_tags(fields)
    for tag, attr in _HARDPOINT_FIELDS:
        if tag in skipped:
            continue
        check(tag, getattr(config, attr), getattr(base, attr))

    if config.kind == KIND_WEAPON and hardpoint_kind(fields) == KIND_WEAPON:
        weapon = config.weapon
        weapon_base = WeaponConfig(name="")
        for tag, attr in _WEAPON_FIELDS:
            check(tag, getattr(weapon, attr), getattr(weapon_base, attr))

        actual_acc = list(parse_category_value_pairs(fields.get("Fire_Inaccuracy_Distance", [])).items())
        expected_acc = list(weapon.accuracy_by_category.items())
        if [(c, float(v)) for c, v in actual_acc] != [(c, float(v)) for c, v in expected_acc]:
            mismatches.append(Mismatch(
                field="Fire_Inaccuracy_Distance",
                actual=", ".join(f"{c} {v:g}" for c, v in actual_acc) or "(not set)",
                expected=", ".join(f"{c} {v:g}" for c, v in expected_acc) or "(not set)",
            ))

        actual_res = parse_category_list(_first(fields, "Fire_Category_Restrictions"))
        if sorted(a.lower() for a in actual_res) != sorted(r.lower() for r in weapon.category_restrictions):
            mismatches.append(Mismatch(
                field="Fire_Category_Restrictions",
                actual=", ".join(actual_res) or "(not set)",
                expected=", ".join(weapon.category_restrictions) or "(not set)",
            ))

        for spec in modifiers_for_context(CONTEXT_HARDPOINT):
            tag = spec.hardpoint_field
            if not tag:
                continue
            actual = _norm(_first(fields, tag))
            expected = _norm(weapon.modifiers.get(spec.key, ""))
            if actual != expected:
                mismatches.append(Mismatch(
                    field=tag, actual=_first(fields, tag) or "(not set)",
                    expected=weapon.modifiers.get(spec.key) or "(not set)",
                ))

    return mismatches


# -- overrides -------------------------------------------------------------------------------------


def apply_overrides(fields: dict[str, list[str]], overrides: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """The hardpoint's data with its overrides laid on top. An override whose
    value list is empty clears the tag."""
    result = {tag: list(values) for tag, values in fields.items()}
    for tag, values in (overrides or {}).items():
        if values:
            result[tag] = list(values)
        else:
            result.pop(tag, None)
    return result


def compare_with_overrides(
    fields: dict[str, list[str]], config: HardpointConfig | None, overrides: dict[str, list[str]] | None,
) -> list[Mismatch]:
    """Where the hardpoint's real XML differs from the data it *should* have:
    its assigned config's values with the user's overrides on top (or just
    the overrides when no config is assigned). An override replaces whatever
    the config says for that tag, so the config's mismatch on a tag the user
    deliberately overrode is dropped and replaced by XML-vs-override."""
    overrides = overrides or {}
    result = [m for m in (compare_to_config(fields, config) if config is not None else []) if m.field not in overrides]
    for tag, values in overrides.items():
        actual = fields.get(tag, [])
        if [_norm(v) for v in actual] != [_norm(v) for v in values]:
            result.append(Mismatch(
                field=tag, actual=" | ".join(actual) or "(not set)", expected=" | ".join(values) or "(not set)",
            ))
    return result


# -- shared data across a selection ----------------------------------------------------------------


@dataclass
class FieldVariation:
    """One distinct value-set a tag takes across the selected hardpoints."""
    values: list[str]
    members: list[str]


@dataclass
class SelectionData:
    """What a selection of hardpoints has in common, and where it differs."""
    count: int
    shared: dict[str, list[str]] = field(default_factory=dict)
    varying: dict[str, list[FieldVariation]] = field(default_factory=dict)


def summarize_fields(members: list[UnitHardpoint]) -> SelectionData:
    """Fields every selected hardpoint has with the same value(s) go in
    `shared` (numbers compared numerically, so 6000 == 6000.0); any tag that
    is missing on some members or takes different values is listed under
    `varying` with each distinct value-set and which hardpoints use it. For a
    single hardpoint this is simply all of its data."""
    data = SelectionData(count=len(members))
    if not members:
        return data

    tags: list[str] = []
    for member in members:
        for tag in member.fields:
            if tag not in tags:
                tags.append(tag)

    for tag in tags:
        per_member = [(m.name, list(m.fields.get(tag, []))) for m in members]
        keys = {tuple(_norm(v) for v in values) for _name, values in per_member}
        if len(keys) == 1:
            data.shared[tag] = per_member[0][1]
            continue

        variations: dict[tuple, FieldVariation] = {}
        for name, values in per_member:
            key = tuple(_norm(v) for v in values)
            variation = variations.get(key)
            if variation is None:
                variation = FieldVariation(values=values, members=[])
                variations[key] = variation
            variation.members.append(name)
        data.varying[tag] = list(variations.values())
    return data
