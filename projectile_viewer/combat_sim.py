"""Predicts time-to-kill for an allied unit attacking an enemy unit, using
the real damage-type/armor-type multiplier matrix from GAMECONSTANTS.XML.

Shield_Refresh_Rate is treated as points regenerated per
ShieldRechargeIntervalInSecs tick (i.e. points/sec when that interval is the
usual 1.0) - the plain reading of a field literally named "rate". A real CR90
(Shield_Points=1500, Shield_Refresh_Rate=6.25) implies a ~240s full recharge
under this reading, which is a plausible design target; the inverted
reading (treating the field itself as a recharge duration) would imply a
implausibly fast ~240 points/sec regen for the same ship. Still worth a
sanity check against known in-game recharge behavior once this is running.
"""

from dataclasses import dataclass

from .game_constants import DamageMatrix
from .unit_loadout import HardpointGroup, UnitLoadout

DEFAULT_SHIELD_RECHARGE_INTERVAL_SECS = 1.0


@dataclass
class EffectiveWeaponResult:
    group: HardpointGroup
    dps_vs_shield: float
    dps_vs_hull: float


@dataclass
class BattleResult:
    per_weapon: list[EffectiveWeaponResult]
    total_dps_vs_shield: float
    total_dps_vs_hull: float
    shield_regen_per_sec: float
    hull_kill_seconds: float | None

    shield_strip_seconds_no_regen: float | None
    total_ttk_seconds_no_regen: float | None

    shield_strip_seconds_with_regen: float | None
    total_ttk_seconds_with_regen: float | None


def _safe_div(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def simulate(
    ally: UnitLoadout,
    enemy: UnitLoadout,
    matrix: DamageMatrix,
    recharge_interval_secs: float = DEFAULT_SHIELD_RECHARGE_INTERVAL_SECS,
) -> BattleResult:
    per_weapon: list[EffectiveWeaponResult] = []
    total_dps_vs_shield = 0.0
    total_dps_vs_hull = 0.0

    for group in ally.weapon_groups:
        config = group.weapon_config
        stats = group.stats
        if config is None or stats is None:
            continue

        shield_mult = matrix.multiplier(config.damage_type, enemy.shield_armor_type)
        hull_mult = matrix.multiplier(config.damage_type, enemy.armor_type)
        dps_vs_shield = stats.dps_avg * group.count * shield_mult
        dps_vs_hull = stats.dps_avg * group.count * hull_mult

        per_weapon.append(EffectiveWeaponResult(group=group, dps_vs_shield=dps_vs_shield, dps_vs_hull=dps_vs_hull))
        total_dps_vs_shield += dps_vs_shield
        total_dps_vs_hull += dps_vs_hull

    hull_kill_seconds = _safe_div(enemy.tactical_health, total_dps_vs_hull)

    shield_strip_no_regen = _safe_div(enemy.shield_points, total_dps_vs_shield) if enemy.shield_points > 0 else 0.0
    total_ttk_no_regen = (
        shield_strip_no_regen + hull_kill_seconds
        if shield_strip_no_regen is not None and hull_kill_seconds is not None
        else None
    )

    shield_regen_per_sec = enemy.shield_refresh_rate / recharge_interval_secs if recharge_interval_secs > 0 else 0.0
    if enemy.shield_points <= 0:
        shield_strip_with_regen = 0.0
    else:
        net_dps_vs_shield = total_dps_vs_shield - shield_regen_per_sec
        shield_strip_with_regen = _safe_div(enemy.shield_points, net_dps_vs_shield) if net_dps_vs_shield > 0 else None
    total_ttk_with_regen = (
        shield_strip_with_regen + hull_kill_seconds
        if shield_strip_with_regen is not None and hull_kill_seconds is not None
        else None
    )

    return BattleResult(
        per_weapon=per_weapon,
        total_dps_vs_shield=total_dps_vs_shield,
        total_dps_vs_hull=total_dps_vs_hull,
        shield_regen_per_sec=shield_regen_per_sec,
        hull_kill_seconds=hull_kill_seconds,
        shield_strip_seconds_no_regen=shield_strip_no_regen,
        total_ttk_seconds_no_regen=total_ttk_no_regen,
        shield_strip_seconds_with_regen=shield_strip_with_regen,
        total_ttk_seconds_with_regen=total_ttk_with_regen,
    )
