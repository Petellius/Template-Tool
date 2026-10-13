"""Best-effort descriptions for Behavior/SpaceBehavior/LandBehavior flag
values, inferred from their names and usage context (no description field
exists in the source XML for these tags). User edits are persisted as
overrides to a local JSON file, layered on top of these defaults.
"""

import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "user_data", "behavior_descriptions.json"
)

# Inferred, not authoritative - the user can correct any of these via the UI.
DEFAULT_DESCRIPTIONS: dict[str, str] = {
    "ABILITY_COUNTDOWN": "Has an ability with a recharge/cooldown countdown.",
    "AFFECTED_BY_SHIELD": "Can be protected by a base/unit shield effect.",
    "AMBIENT_SFX": "Plays ambient/looping sound effects.",
    "ASTEROID_FIELD_DAMAGE": "Takes damage from asteroid fields.",
    "BARRAGE": "Can perform a barrage-style multi-shot attack.",
    "BASE_SHIELD": "Provides or uses a base/structure shield.",
    "BIKE_LOCOMOTOR": "Uses speeder-bike style movement.",
    "BOMB": "Acts as a bomb (e.g. dropped ordnance).",
    "BUZZ_DROIDS": "Related to buzz droid attachment/behavior.",
    "CAPTURE_POINT": "Acts as a capturable territory/point.",
    "CASH_POINT": "Generates or represents a credits/cash income point.",
    "DAMAGE_TRACKING": "Tracks incoming damage (e.g. for damage states/hit reactions).",
    "DEBRIS": "Acts as space/land debris.",
    "DEMOLITION": "Can perform demolition actions.",
    "DEPLOY_TROOPERS": "Can deploy troopers/infantry.",
    "DISABLE_FORCE_ABILITIES": "Disables Force abilities in its vicinity.",
    "DUMMY_DESTROY_AFTER_BOMBING_RUN": "Placeholder object destroyed after a bombing run completes.",
    "DUMMY_DESTROY_AFTER_PLANETARY_BOMBARD": "Placeholder object destroyed after planetary bombardment.",
    "DUMMY_DESTROY_AFTER_SPECIAL_WEAPON_FIRED": "Placeholder object destroyed after a special weapon fires.",
    "DUMMY_GROUND_BASE": "Placeholder marking a ground base object.",
    "DUMMY_GROUND_COMPANY": "Placeholder marking a ground company object.",
    "DUMMY_GROUND_STRUCTURE": "Placeholder marking a ground structure object.",
    "DUMMY_LAND_BASE_LEVEL_COMPONENT": "Placeholder component of a land base's level/tier.",
    "DUMMY_ORBITAL_STRUCTURE": "Placeholder marking an orbital structure object.",
    "DUMMY_SPACE_FIGHTER_SQUADRON": "Placeholder marking a space fighter squadron object.",
    "DUMMY_SPECIAL_WEAPON_SOURCE": "Placeholder marking the source of a special weapon.",
    "DUMMY_STARSHIP": "Placeholder marking a starship object.",
    "DUMMY_STARSHIP DUMMY_CANT_PATHFIND": (
        "Data issue: two flags (DUMMY_STARSHIP, DUMMY_CANT_PATHFIND) missing a comma "
        "between them in the source XML, so they were captured as one token."
    ),
    "DUMMY_STAR_BASE": "Placeholder marking a star base object.",
    "DUMMY_TACTICAL_SUPER_WEAPON_TARGET": "Placeholder marking a tactical super-weapon target.",
    "DUMMY_TOOLTIP": "Placeholder used only to attach a tooltip.",
    "DUMMY_UPGRADE": "Placeholder marking an upgrade object.",
    "DYNAMIC_TRANSFORM": "Object's position/rotation can change dynamically at runtime.",
    "EARTHQUAKE_TARGET": "Can be affected by an earthquake-style area ability.",
    "EXPLOSION": "Acts as an explosion effect object.",
    "FIGHTER_LOCOMOTOR": "Uses starfighter-style movement.",
    "FLEET": "Belongs to/represents a fleet.",
    "FLEET_LOCOMOTOR": "Uses fleet-level movement logic.",
    "FLYING_LOCOMOTOR": "Uses flying movement (land context, e.g. repulsorlift/air units).",
    "GARRISON_HOVER": "Can be garrisoned into by hovering units.",
    "GARRISON_STRUCTURE": "Can garrison inside a structure.",
    "GARRISON_UNIT": "Can garrison inside a unit.",
    "GARRISON_VEHICLE": "Can garrison inside a vehicle.",
    "GRAVITY_CONTROL_FIELD": "Projects or is affected by a gravity control field.",
    "HARASS": "Used by the AI for harassment-style behavior.",
    "HIDE_WHEN_FOGGED": "Hidden from view while covered by fog of war.",
    "HINT": "Provides an AI/gameplay hint marker.",
    "HOLSTER_WEAPON": "Can holster its weapon (stop actively wielding it).",
    "HUNT": "Used by the AI for hunting/pursuit behavior.",
    "IDLE": "Has an idle animation/state.",
    "IMPOSING_PRESENCE": "Projects a presence effect on nearby units (e.g. an intimidation-style hero ability).",
    "INDIGENOUS_UNIT": "Is a native/indigenous unit type.",
    "INTERDICT": "Can interdict (prevent) enemy hyperspace travel.",
    "ION_STUN_EFFECT": "Can be stunned by ion weapon effects.",
    "JETPACK_LOCOMOTOR": "Uses jetpack-style movement.",
    "LANDBOMBER_LOCOMOTOR": "Uses land-bomber style movement.",
    "LANDING": "Can perform a landing maneuver.",
    "LAND_OBSTACLE": "Acts as a land obstacle.",
    "LAND_TEAM_CONTAINER_LOCOMOTOR": "Movement logic for a land team/container (e.g. a transported squad).",
    "LAND_TEAM_INFANTRY_LOCOMOTOR": "Movement logic for a land infantry team.",
    "LOBBING_SUPERWEAPON": "Fires a lobbed (arcing) superweapon projectile.",
    "LURE": "Used by the AI to lure enemies (e.g. a decoy/bait behavior).",
    "MARKER": "Acts as an invisible marker/reference point.",
    "MOVE": "Can move under its own power (space context).",
    "MULTIPLAYER_BEACON": "Acts as a multiplayer spawn/objective beacon.",
    "NEBULA": "Represents a nebula field effect.",
    "PARTICLE": "Acts as a particle effect object.",
    "PLANET": "Represents a planet object.",
    "POWERED": "Requires/consumes power to function.",
    "PRODUCTION": "Can produce/build units.",
    "PROJECTILE": "Marks this object as a projectile.",
    "PROXIMITY_MINE": "Acts as a proximity mine.",
    "REINFORCEMENT_POINT": "Acts as a reinforcement spawn point.",
    "REVEAL": "Reveals an area of fog of war.",
    "SABILITY_COUNTDOWN": (
        "Likely a typo of ABILITY_COUNTDOWN in the source XML (a missing comma merged it "
        "with a preceding token)."
    ),
    "SELECTABLE": "Can be selected by the player.",
    "SELF_DESTRUCT": "Can self-destruct.",
    "SHIELDED": "Has a shield (hitpoint buffer).",
    "SIMPLE_SPACE_LOCOMOTOR": "Uses simplified space movement logic.",
    "SKY_DOME": "Acts as a sky dome/background object.",
    "SPACE_OBSTACLE": "Acts as a space obstacle.",
    "SPAWN_INDIGENOUS_UNITS": "Can spawn indigenous/native units.",
    "SPAWN_SQUADRON": "Can spawn a squadron of units.",
    "SPECIAL_WEAPON": "Equipped with a special weapon ability.",
    "SQUASH": "Can be squashed/crushed (e.g. by a larger unit).",
    "STUNNABLE": "Can be stunned.",
    "SURFACE_FX": "Displays surface effects (e.g. scorch marks, footprints).",
    "TACTICAL_BUILD_OBJECTS": "Relevant to tactical (in-battle) construction objects.",
    "TACTICAL_SELL": "Can be sold during a tactical battle.",
    "TACTICAL_SUPER_WEAPON": "Is a tactical (in-battle) super weapon.",
    "TACTICAL_UNDER_CONSTRUCTION": "Represents an under-construction state in tactical battle.",
    "TARGETING": "Can target and be targeted in combat.",
    "TEAM": "Belongs to/represents a team grouping.",
    "TEAM_LOCOMOTOR": "Uses team-level movement logic.",
    "TEAM_TARGETING": "Uses team-based targeting logic.",
    "TELEKINESIS_TARGET": "Can be targeted by telekinesis-style Force abilities.",
    "TERRAIN_TEXTURE_MODIFICATION": "Modifies terrain texture (e.g. scorches the ground).",
    "TRANSPORT": "Can transport other units/cargo.",
    "TREAD_SCROLL": "Scrolls tread/track textures to simulate movement.",
    "TURRET": "Has a turret that rotates independently of its base.",
    "UNIT_AI": "Uses standard unit AI behavior logic.",
    "VEHICLE_THIEF": "Can steal/hijack vehicles.",
    "WALK_LOCOMOTOR": "Uses walking movement.",
    "WALL": "Acts as a wall (blocks movement).",
    "WEAPON": "Can fire as a weapon/hardpoint holder.",
    "WIND_DISTURBANCE": "Reacts to or causes wind disturbance effects.",
}


def load_overrides(path: str = DEFAULT_PATH) -> dict[str, str]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_overrides(overrides: dict[str, str], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, sort_keys=True)
    os.replace(tmp_path, path)


def get_description(value: str, overrides: dict[str, str]) -> str:
    if value in overrides:
        return overrides[value]
    return DEFAULT_DESCRIPTIONS.get(value, "")
