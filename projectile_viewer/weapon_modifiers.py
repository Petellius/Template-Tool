"""Catalog of optional weapon "modifier" fields - toggles/multipliers a
hardpoint or direct unit-weapon may or may not set, beyond the core
damage/rate-of-fire fields already modeled directly on WeaponConfig.

Real data shows the same underlying concept sometimes has a DIFFERENT raw
field name depending on which of the two weapon schemas hosts it - e.g. the
deployed-state toggle is `Fire_When_Deployed` on a HardPoint but
`Fire_Weapon_When_Deployed` (extra "Weapon" infix) on a direct unit-weapon.
A few concepts only exist on the HardPoint schema (Power-to-Weapons mode,
full-salvo delay, manual firing cooldown, manual target assignment are all
ship/hardpoint-specific mechanics with no direct unit-weapon equivalent).

`ModifierSpec.key` is the stable, schema-agnostic identity WeaponConfig.modifiers
is keyed by; `hardpoint_field`/`unit_weapon_field` are the raw XML tag name
for each schema (None where the concept doesn't apply to that schema) - this
is what lets seeding/export pick the right real tag name per context.

Boolean vocabulary is NOT consistent across concepts (Allow_* fields use
True/False, everything else here uses Yes/No), but IS consistent for a given
concept across both schemas (confirmed on every renamed pair found), so one
true_value/false_value pair per spec is enough - no per-schema vocabulary
variants needed.
"""

from dataclasses import dataclass

KIND_BOOL = "bool"
KIND_FLOAT = "float"


@dataclass
class ModifierSpec:
    key: str
    label: str
    kind: str
    true_value: str = "Yes"
    false_value: str = "No"
    description: str = ""
    hardpoint_field: str | None = None
    unit_weapon_field: str | None = None


MODIFIER_CATALOG: list[ModifierSpec] = [
    ModifierSpec(
        "allow_opportunity_fire_when_targeting", "Allow Opportunity Fire (When Targeting)", KIND_BOOL,
        "True", "False",
        "Fire opportunistically at other targets of opportunity while actively targeting something else.",
        hardpoint_field="Allow_Opportunity_Fire_When_Targeting",
        unit_weapon_field="Allow_Opportunity_Fire_When_Targeting",
    ),
    ModifierSpec(
        "allow_opportunity_fire_when_idle", "Allow Opportunity Fire (When Idle)", KIND_BOOL,
        "True", "False",
        "Fire opportunistically at targets of opportunity while idle (not currently engaged).",
        hardpoint_field="Allow_Opportunity_Fire_When_Idle",
        unit_weapon_field="Allow_Opportunity_Fire_When_Idle",
    ),
    ModifierSpec(
        "fire_when_in_power_to_weapons_mode", "Fire When In Power-to-Weapons Mode", KIND_BOOL, "Yes", "No",
        "This weapon fires while the ship is in Power-to-Weapons mode "
        "(pairs with the delay multiplier below). Ship-only - no direct unit-weapon equivalent exists.",
        hardpoint_field="Fire_When_In_Power_To_Weapons_Mode",
    ),
    ModifierSpec(
        "power_to_weapons_mode_weapon_delay_multiplier", "Power-to-Weapons Mode Delay Multiplier", KIND_FLOAT,
        description="Multiplier applied to this weapon's fire delay while in Power-to-Weapons mode "
                    "(pairs with Fire_When_In_Power_To_Weapons_Mode). Ship-only.",
        hardpoint_field="Power_To_Weapons_Mode_Weapon_Delay_Multiplier",
    ),
    ModifierSpec(
        "fire_when_in_normal_attack_mode", "Fire When In Normal Attack Mode", KIND_BOOL, "Yes", "No",
        "This weapon fires during normal attack mode.",
        hardpoint_field="Fire_When_In_Normal_Attack_Mode",
        unit_weapon_field="Fire_Weapon_When_In_Normal_Attack_Mode",
    ),
    ModifierSpec(
        "fire_when_in_rocket_attack_mode", "Fire When In Rocket/Assault Attack Mode", KIND_BOOL, "Yes", "No",
        "This weapon fires during rocket/assault attack mode.",
        hardpoint_field="Fire_When_In_Rocket_Attack_Mode",
        unit_weapon_field="Fire_Weapon_When_In_Rocket_Attack_Mode",
    ),
    ModifierSpec(
        "fire_when_deployed", "Fire When Deployed", KIND_BOOL, "Yes", "No",
        "This weapon only fires while the unit is deployed (pairs with Fire When Undeployed).",
        hardpoint_field="Fire_When_Deployed",
        unit_weapon_field="Fire_Weapon_When_Deployed",
    ),
    ModifierSpec(
        "fire_when_undeployed", "Fire When Undeployed", KIND_BOOL, "Yes", "No",
        "This weapon only fires while the unit is undeployed (pairs with Fire When Deployed).",
        hardpoint_field="Fire_When_Undeployed",
        unit_weapon_field="Fire_Weapon_When_Undeployed",
    ),
    ModifierSpec(
        "full_salvo_weapon_delay_multiplier", "Full Salvo Delay Multiplier", KIND_FLOAT,
        description="Multiplier applied to this weapon's fire delay when firing a full salvo. HardPoint-only.",
        hardpoint_field="Full_Salvo_Weapon_Delay_Multiplier",
    ),
    ModifierSpec(
        "manual_hardpoint_firing_cooldown_secs", "Manual Firing Cooldown (s)", KIND_FLOAT,
        description="Cooldown (seconds) a player must wait before manually firing this hardpoint again. "
                    "HardPoint-only.",
        hardpoint_field="Manual_Hardpoint_Firing_Cooldown_Secs",
    ),
    ModifierSpec(
        "requires_manual_target_assignment", "Requires Manual Target Assignment", KIND_BOOL, "Yes", "No",
        "This weapon won't auto-target - the player must manually assign its target. HardPoint-only.",
        hardpoint_field="Requires_Manual_Target_Assignment",
    ),
]

MODIFIERS_BY_KEY: dict[str, ModifierSpec] = {m.key: m for m in MODIFIER_CATALOG}


def modifiers_for_context(context: str) -> list[ModifierSpec]:
    """Filters the catalog to specs that actually apply to the given
    WeaponConfig context ("hardpoint" or "unit_weapon") - a spec with no
    field name for that schema doesn't apply there at all.
    """
    field_attr = "hardpoint_field" if context == "hardpoint" else "unit_weapon_field"
    return [m for m in MODIFIER_CATALOG if getattr(m, field_attr) is not None]


def parse_bool(raw: str) -> bool:
    """Case-insensitive; accepts every real-data variant seen (Yes/No,
    True/False, 1/0, including stray whitespace).
    """
    return raw.strip().lower() in ("yes", "true", "1")


def format_modifier_value(spec: ModifierSpec, ui_value) -> str:
    """Converts a UI-level value (a Python bool for KIND_BOOL, a float for
    KIND_FLOAT) into this field's own canonical export string.
    """
    if spec.kind == KIND_BOOL:
        return spec.true_value if ui_value else spec.false_value
    return str(ui_value)
