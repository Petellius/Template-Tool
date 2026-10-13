"""Categorizes HardPoint fields into display groups.

Mirrors unit_field_groups.py's interface (GROUPS + group_fields). HardPoints
split fairly cleanly into: identity, survivability, attachment/geometry,
turret specifics, weapon/fire behavior (including Fire_Projectile_Type,
rendered specially by the UI as a clickable link to the Projectiles tab),
and a handful of type-specific extras (engine/fighter-bay/special-ability).
"""

OTHER_GROUP_NAME = "Other / Ungrouped"

GROUPS: list[tuple[str, list[str]]] = [
    ("Identity & Text", [
        "Type",
        "Tooltip_Text",
        "Special_Ability_Name",
        "Weapon_Hardpoint",
        "Engine_Hardpoint",
        "Shield_Generator_Hardpoint",
    ]),
    ("Survivability", [
        "Is_Targetable",
        "Is_Destroyable",
        "Health",
        "Death_Explosion_Particles",
        "Death_Explosion_SFXEvent",
        "Death_Breakoff_Prop",
        "Damage_Decal",
        "Damage_Particles",
    ]),
    ("Attachment & Geometry", [
        "Model_To_Attach",
        "Attachment_Bone",
        "Collision_Mesh",
        "Fire_Bone_A",
        "Fire_Bone_B",
        "Fire_Bone_C",
        "Fire_Bone_D",
        "Fire_Bone_E",
        "Randomize_Between_Fire_Bones",
    ]),
    ("Turret", [
        "Is_Turret",
        "Turret_Rest_Angle",
        "Turret_Rotation_Offset",
        "Turret_Rotate_Speed",
        "Turret_Rotate_Extent_Degrees",
        "Turret_Elevate_Extent_Degrees",
        "Turret_Bone_Name",
        "Barrel_Bone_Name",
    ]),
    ("Weapon / Fire Behavior", [
        "Fire_Projectile_Type",
        "Blast_Ability_Fire_Projectile_Type",
        "Fire_Min_Recharge_Seconds",
        "Fire_Max_Recharge_Seconds",
        "Fire_Pulse_Count",
        "Fire_Pulse_Delay_Seconds",
        "Fire_Range_Distance",
        "Fire_Cone_Width",
        "Fire_Cone_Height",
        "Fire_SFXEvent",
        "Fire_Inaccuracy_Distance",
        "Targeting_Fire_Inaccuracy",
        "Fire_Category_Restrictions",
        "Allow_Opportunity_Fire_When_Targeting",
        "Allow_Opportunity_Fire_When_Idle",
        "Fire_When_In_Power_To_Weapons_Mode",
        "Fire_When_In_Normal_Attack_Mode",
        "Fire_When_In_Rocket_Attack_Mode",
        "Fire_When_Deployed",
        "Fire_When_Undeployed",
        "Full_Salvo_Weapon_Delay_Multiplier",
        "Power_To_Weapons_Mode_Weapon_Delay_Multiplier",
        "Manual_Hardpoint_Firing_Cooldown_Secs",
        "Requires_Manual_Target_Assignment",
        "Projectile_Damage",
        "Projectile_Appearance_Delay_Frames",
        "Damage_Type",
    ]),
    ("Type-Specific Extras", [
        "Engine_Particles",
        "Fighter_Bay_Flyout_Distance",
        "Repair_Cost_Per_Frame",
        "Repair_Amount_Per_Frame",
        "Allows_Special_Weapon_Use",
    ]),
]


def group_fields(field_names) -> list[tuple[str, list[str]]]:
    """Bucket the given field names into (group_name, [field_names]) pairs,
    preserving GROUPS order and appending an Other/Ungrouped bucket last.
    Empty groups are omitted.
    """
    remaining = set(field_names)
    grouped: list[tuple[str, list[str]]] = []

    for group_name, known_fields in GROUPS:
        present = [f for f in known_fields if f in remaining]
        if present:
            grouped.append((group_name, present))
            remaining.difference_update(present)

    if remaining:
        grouped.append((OTHER_GROUP_NAME, sorted(remaining)))

    return grouped
