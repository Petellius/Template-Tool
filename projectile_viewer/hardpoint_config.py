"""Data model for a Hardpoint Config - a reusable, named description of one
kind of <HardPoint> (e.g. "Dual Heavy Turbolaser Turret", "Shield Generator").

A config carries three groups of data:

- Hardpoint data every <HardPoint> has: Type, Tooltip_Text, Is_Targetable,
  Is_Destroyable, Health, death effects, and the optional placement defaults
  Attachment_Bone / Collision_Mesh (a unit overwrites those when the config
  is placed on its model - ALO bone assignment is a later milestone).
- Model-intrinsic data, fixed by the attached weapon/turret model and so
  reusable on any ship: Model_To_Attach, Fire_Bone_A/B, turret bones and
  extents.
- For weapon hardpoints only, a weapon block: a link to a Weapon Template
  (weapon_rules.WeaponRule, by category name) plus the embedded WeaponConfig
  holding the effective values. Its `overridden_fields` track which values
  the user hand-edited - exactly like the per-slot Weapon Configs - so
  re-applying the template never clobbers them, and "reset" returns every
  variable to the template's defaults.
"""

from dataclasses import dataclass, field

from .weapon_config import CONTEXT_HARDPOINT, WeaponConfig, seed_from_projectile
from .weapon_rules import WeaponRule, apply_rule

KIND_WEAPON = "weapon"
KIND_NON_WEAPON = "non_weapon"
KINDS = (KIND_WEAPON, KIND_NON_WEAPON)

# Types seen in real AGD hardpoint files (HardPoints_Republic_Venator.XML).
# The editor offers these but stays free-text, so any other game type works.
HARDPOINT_TYPES = (
    "HARD_POINT_WEAPON_LASER",
    "HARD_POINT_WEAPON_MASS_DRIVER",
    "HARD_POINT_WEAPON_TORPEDO",
    "HARD_POINT_WEAPON_MISSILE",
    "HARD_POINT_WEAPON_ION_CANNON",
    "HARD_POINT_FIGHTER_BAY",
    "HARD_POINT_SHIELD_GENERATOR",
    "HARD_POINT_ENGINE",
    "HARD_POINT_DUMMY_ART",
)


@dataclass
class HardpointConfig:
    name: str
    kind: str = KIND_WEAPON
    hp_type: str = "HARD_POINT_WEAPON_LASER"
    tooltip_text: str = ""
    notes: str = ""
    theatre: str = ""  # "", "Space" or "Land"

    # Survivability
    is_targetable: bool = False
    is_destroyable: bool = False
    health: float = 1.0
    death_explosion_particles: str = ""
    death_explosion_sfx: str = ""
    damage_decal: str = ""
    damage_particles: str = ""

    # Model-intrinsic (fixed by the attached model)
    model_to_attach: str = ""
    fire_bone_a: str = ""
    fire_bone_b: str = ""
    is_turret: bool = False
    turret_bone_name: str = ""
    barrel_bone_name: str = ""
    turret_rest_angle: str = ""
    turret_rotation_offset: str = ""
    turret_rotate_extent_degrees: float = 0.0
    turret_elevate_extent_degrees: float = 0.0

    # Placement defaults (set per unit when placed on a model's bones)
    attachment_bone: str = ""
    collision_mesh: str = ""

    # Weapon block - only meaningful when kind == KIND_WEAPON
    weapon_template: str = ""
    weapon: WeaponConfig = field(default_factory=lambda: WeaponConfig(name="", context=CONTEXT_HARDPOINT))

    @property
    def is_weapon(self) -> bool:
        return self.kind == KIND_WEAPON


def reset_weapon_to_template(config: HardpointConfig, rule: WeaponRule | None, projectile_resolver=None) -> None:
    """Returns every weapon variable to the linked template's defaults: a
    fresh WeaponConfig with all overrides (and their notes) cleared, the
    rule applied on top, and - when the rule names a default projectile and
    `projectile_resolver(name)` can resolve it to its merged field map -
    damage/damage_type re-seeded from that projectile.

    With no rule the weapon block is simply blanked to a fresh config.
    """
    fresh = WeaponConfig(name=config.name, context=CONTEXT_HARDPOINT, category=config.weapon_template)
    if rule is not None:
        apply_rule(fresh, rule)
        if projectile_resolver is not None and fresh.source_projectile_name:
            resolved = projectile_resolver(fresh.source_projectile_name)
            if resolved is not None:
                seed_from_projectile(fresh, resolved)
    config.weapon = fresh


def order_projectile_choices(
    names: list[str], children_map: dict[str, list[str]], default_projectile: str = "",
) -> list[str]:
    """Orders a projectile dropdown so the template's default projectile and
    its direct variants (projectiles declaring it as Variant_Of_Existing_Type)
    come first, then every other projectile alphabetically.
    """
    available = set(names)
    head: list[str] = []
    if default_projectile and default_projectile in available:
        head.append(default_projectile)
    variants = sorted(
        (v for v in children_map.get(default_projectile, []) if v in available and v not in head),
        key=str.lower,
    ) if default_projectile else []
    head.extend(variants)

    seen = set(head)
    rest = sorted((n for n in names if n not in seen), key=str.lower)
    return head + rest
