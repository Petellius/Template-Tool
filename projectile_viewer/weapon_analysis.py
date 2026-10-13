"""Combat-stat analysis for a WeaponConfig: burst/cycle timing and DPS.

A "cycle" is one full burst: `fire_pulse_count` shots, each separated by
`fire_pulse_delay` seconds, followed by a recharge before the next burst
starts. Recharge is a Min/Max range in the source data (the engine appears to
pick randomly within it), so cycle time and DPS are reported as min/avg/max.
"""

from dataclasses import dataclass

from .weapon_config import WeaponConfig


@dataclass
class WeaponStats:
    shots_per_cycle: int
    damage_per_shot: float
    damage_per_cycle: float
    cycle_time_min: float
    cycle_time_avg: float
    cycle_time_max: float
    dps_min: float
    dps_avg: float
    dps_max: float


def _cycle_time(recharge: float, pulse_count: int, pulse_delay: float) -> float:
    return recharge + max(pulse_count - 1, 0) * pulse_delay


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def analyze(config: WeaponConfig) -> WeaponStats:
    pulse_count = max(config.fire_pulse_count, 1)
    damage_per_cycle = config.damage * pulse_count

    time_min = _cycle_time(config.fire_min_recharge, pulse_count, config.fire_pulse_delay)
    time_max = _cycle_time(config.fire_max_recharge, pulse_count, config.fire_pulse_delay)
    time_avg = (time_min + time_max) / 2

    return WeaponStats(
        shots_per_cycle=pulse_count,
        damage_per_shot=config.damage,
        damage_per_cycle=damage_per_cycle,
        cycle_time_min=time_min,
        cycle_time_avg=time_avg,
        cycle_time_max=time_max,
        # A longer cycle time means fewer cycles per second, so the *max*
        # cycle time yields the *min* DPS, and vice versa.
        dps_min=_safe_div(damage_per_cycle, time_max),
        dps_avg=_safe_div(damage_per_cycle, time_avg),
        dps_max=_safe_div(damage_per_cycle, time_min),
    )
