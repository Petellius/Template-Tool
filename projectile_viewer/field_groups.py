"""Categorizes Projectile fields into display groups.

This is the "template group" breakdown the tool is built around: each group
here is a candidate unit of reuse for the future template-builder step. Any
resolved field not listed below still gets shown, under OTHER_GROUP_NAME, so
nothing is ever silently dropped.
"""

OTHER_GROUP_NAME = "Other / Ungrouped"

GROUPS: list[tuple[str, list[str]]] = [
    ("Identity & Metadata", [
        "Text_ID",
        "Encyclopedia_Text",
        "Encyclopedia_Unit_Class",
        "Lua_Script",
    ]),
    ("Movement & Physics", [
        "Max_Speed",
        "Max_Rate_Of_Turn",
        "Projectile_Acceleration_Per_Frame",
        "Mass",
        "LandBehavior",
        "SpaceBehavior",
        "Avoidance_Disabled",
        "Projectile_Max_Flight_Distance",
        "Projectile_Max_Lifetime",
        "Projectile_Max_Scan_Range",
        "Explode_When_Reached_Target_Radius",
        "Projectile_Bomb_Fall_Accel_Rate",
    ]),
    ("Behavior", [
        "Behavior",
        "Projectile_Category",
    ]),
    ("Rocket & Terrain Targeting", [
        "Projectile_Target_Point_On_Terrain",
        "Projectile_Rocket_Curve_Distance",
        "Projectile_Rocket_Curve_Offset",
        "Projectile_Rocket_Straight_Distance",
    ]),
    ("Grenade", [
        "Projectile_Grenade_Gravity",
        "Projectile_Grenade_Gravity_Lob_Mod",
        "Projectile_Grenade_Can_Lob_Slower",
        "Projectile_Grenade_Sticks_On_Collision",
    ]),
    ("Rendering & Model", [
        "Space_Model_Name",
        "Land_Model_Name",
        "Scale_Factor",
        "Projectile_Custom_Render",
        "Projectile_Width",
        "Projectile_Length",
        "Projectile_Texture_Slot",
        "Projectile_Laser_Color",
        "Model_Visible_To_Enemy",
        "Mouse_Collide_Override_Sphere_Radius",
        "Loop_Idle_Anim_00",
        "Is_Decoration",
        "Is_Visible_On_Radar",
    ]),
    ("Damage & Targeting", [
        "Damage_Type",
        "Internal_Damage_Type",
        "Projectile_Damage",
        "Projectile_Energy_Per_Shot",
        "Projectile_Does_Shield_Damage",
        "Projectile_Does_Energy_Damage",
        "Projectile_Does_Hitpoint_Damage",
        "Projectile_Damages_Random_Hard_Points",
        "Friendly_Damage_Amount",
        "Projectile_Damage_Delay_Secs",
        "CategoryMask",
    ]),
    ("Blast / Area Effect", [
        "Projectile_Blast_Area_Damage",
        "Projectile_Blast_Area_Range",
        "Projectile_Blast_Area_Dropoff",
        "Projectile_Blast_Area_Dropoff_Tiers",
        "Projectile_Blast_Area_Max_Victims",
        "Projectile_Blast_Area_Immune_Faction",
        "Max_Secs_For_AE_Delayed_Damage",
    ]),
    ("Detonation & Particles", [
        "Projectile_Object_Detonation_Particle",
        "Projectile_Object_Armor_Reduced_Detonation_Particle",
        "Projectile_Ground_Detonation_Particle",
        "Projectile_Lifetime_Detonation_Particle",
        "Projectile_Absorbed_By_Shields_Particle",
        "Projectile_Object_Creation_Particle",
        "Projectile_Ground_Detonation_SurfaceFX",
    ]),
    ("SFX / Audio", [
        "SFXEvent_Fire",
        "Projectile_SFXEvent_Detonate",
        "Projectile_SFXEvent_Detonate_Reduced_By_Armor",
        "SFXEvent_Engine_Idle_Loop",
        "SFXEvent_Engine_Moving_Loop",
        "Death_SFXEvent_Start_Die",
    ]),
    ("Ion Stun", [
        "Projectile_Ion_Stun_On_Detonation",
        "Projectile_Ion_Stun_Duration",
        "Projectile_Ion_Stun_Radius",
        "Projectile_Ion_Stun_Speed_Reduction_Percent",
        "Projectile_Ion_Stun_Shot_Rate_Reduction_Percent",
        "Projectile_Ion_Stun_Stack_Duration",
        "Projectile_Disables_Engines_When_Power_Drained",
        "Projectile_Disable_Engines_Duration",
    ]),
    ("Physical Stun", [
        "Projectile_Stun_On_Detonation",
        "Projectile_Stun_Duration_Frames",
        "Projectile_Stun_Radius",
        "Projectile_Stun_Spawn_Effect",
        "Projectile_Stun_Victims_Category_Mask",
        "Projectile_Stun_Victims_Unit_Types",
    ]),
    ("Weaken Enemy", [
        "Projectile_Weaken_Enemy_On_Detonation",
        "Projectile_Weaken_Enemy_Duration_Seconds",
        "Projectile_Weaken_Enemy_Radius",
        "Projectile_Weaken_Enemy_Spawn_Effect",
        "Projectile_Weaken_Enemy_Targets_Category_Mask",
        "Projectile_Weaken_Enemy_Cause_Damage_Reduction_Percent",
        "Projectile_Weaken_Enemy_Take_Damage_Increase_Percent",
    ]),
    ("Convert Enemy", [
        "Projectile_Convert_Enemy_On_Detonation",
        "Projectile_Convert_Enemy_Radius",
        "Projectile_Convert_Enemy_Spawn_Effect",
        "Projectile_Convert_Enemy_Targets_Category_Mask",
    ]),
    ("Instant Heal", [
        "Projectile_Instant_Heal_On_Detonation",
        "Projectile_Instant_Heal_Duration_Frames",
        "Projectile_Instant_Heal_Health_Increase",
        "Projectile_Instant_Heal_Radius",
        "Projectile_Instant_Heal_Spawn_Effect",
        "Projectile_Instant_Heal_Targets_Category_Mask",
    ]),
    ("Invulnerability", [
        "Projectile_Cause_Invulnerability_On_Detonation",
        "Projectile_Cause_Invulnerability_Duration_Frames",
        "Projectile_Cause_Invulnerability_Max_Targets",
        "Projectile_Cause_Invulnerability_Radius",
        "Projectile_Cause_Invulnerability_Spawn_Effect",
        "Projectile_Cause_Invulnerability_Targets_Category_Mask",
    ]),
    ("Combat Mod", [
        "Projectile_Combat_Mod",
        "Projectile_Combat_Mod_Category_Mask",
        "Projectile_Combat_Mod_Duration",
        "Projectile_Combat_Mod_Effect",
        "Projectile_Combat_Mod_Value",
    ]),
    ("Misc / Flags & Combat AI", [
        "AI_Combat_Power",
        "Projectile_Block_Chance_Modifier",
        "Projectile_Redirect_Chance_Modifier",
        "Causes_Infection",
        "Death_Explosions",
        "Remove_Upon_Death",
        "IsDeathCloneObstacle",
        "Collidable_By_Projectile_Dead",
        "Collidable_By_Projectile_Living",
        "CanCellStack",
        "UnitCollisionClass",
        "Influences_Capture_Point",
        "Tactical_Health",
        "Dense_FOW_Reveal_Range_Multiplier",
        "Space_FOW_Reveal_Range",
        "Land_FOW_Reveal_Range",
        "Space_Layer",
        "Projectile_Fire_Pulse_Count",
        "Projectile_Fire_Pulse_Delay_Seconds",
        "Projectile_Fire_Recharge_Seconds",
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
