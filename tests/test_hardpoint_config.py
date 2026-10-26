import json
import os
import tempfile
import unittest

from projectile_viewer.hardpoint_config import (
    KIND_NON_WEAPON, KIND_WEAPON, HardpointConfig, order_projectile_choices, reset_weapon_to_template,
)
from projectile_viewer.hardpoint_config_store import load_configs, save_configs
from projectile_viewer.weapon_config import WeaponConfig
from projectile_viewer.weapon_rules import WeaponRule


class _Resolved:
    def __init__(self, value):
        self.value = value


class StoreRoundTrip(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "hardpoint_configs.json")

    def test_weapon_and_non_weapon_round_trip(self):
        turret = HardpointConfig(
            name="Dual Heavy Turret", hp_type="HARD_POINT_WEAPON_LASER", tooltip_text="TEXT_X",
            health=1.0, is_turret=True, turret_bone_name="TURRET_00", fire_bone_a="MUZZLEA_00",
            model_to_attach="VenatorDTL_00.ALO", weapon_template="Heavy Turbolasers", theatre="Space",
        )
        turret.weapon = WeaponConfig(
            name="Dual Heavy Turret", fire_range=6000.0, turret_rotate_speed=0.35,
            accuracy_by_category={"Fighter": 100.0, "Capital": 45.0},
            overridden_fields={"fire_range"}, override_notes={"fire_range": "longer range"},
            source_projectile_name="AGD_Proj_X",
        )
        shield = HardpointConfig(
            name="Shield Gen", kind=KIND_NON_WEAPON, hp_type="HARD_POINT_SHIELD_GENERATOR",
            is_destroyable=True, health=450.0, attachment_bone="SHIELDGEN_00",
        )
        save_configs([turret, shield], self.path)
        loaded = load_configs(self.path)

        self.assertEqual([c.name for c in loaded], ["Dual Heavy Turret", "Shield Gen"])
        t, s = loaded
        self.assertTrue(t.is_weapon and t.is_turret)
        self.assertEqual(t.weapon.fire_range, 6000.0)
        self.assertEqual(t.weapon.turret_rotate_speed, 0.35)
        self.assertEqual(t.weapon.overridden_fields, {"fire_range"})
        self.assertEqual(t.weapon.override_notes, {"fire_range": "longer range"})
        self.assertEqual(list(t.weapon.accuracy_by_category), ["Fighter", "Capital"])  # priority order kept
        self.assertEqual(t.weapon.source_projectile_name, "AGD_Proj_X")
        self.assertFalse(s.is_weapon)
        self.assertTrue(s.is_destroyable)
        self.assertEqual(s.health, 450.0)

    def test_missing_unknown_and_bad_values_tolerated(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"version": 99, "configs": [
                {"name": "Old", "health": "oops", "is_turret": "yes", "brand_new_field": 1},
                "not a dict",
                {"name": "Bad kind", "kind": "mystery"},
            ]}, f)
        loaded = load_configs(self.path)
        self.assertEqual([c.name for c in loaded], ["Old", "Bad kind"])
        self.assertEqual(loaded[0].health, 1.0)       # bad float -> default
        self.assertTrue(loaded[0].is_turret)          # truthy -> bool
        self.assertEqual(loaded[1].kind, KIND_WEAPON)  # unknown kind -> weapon

    def test_missing_file_and_garbage_file(self):
        self.assertEqual(load_configs(self.path), [])
        with open(self.path, "w") as f:
            f.write("{ not json")
        self.assertEqual(load_configs(self.path), [])


class ResetToTemplate(unittest.TestCase):
    def test_reset_clears_overrides_and_applies_rule(self):
        cfg = HardpointConfig(name="T", weapon_template="Lasers")
        cfg.weapon = WeaponConfig(
            name="T", fire_range=999.0, fire_pulse_count=7,
            overridden_fields={"fire_range", "fire_pulse_count"}, override_notes={"fire_range": "x"},
        )
        rule = WeaponRule(
            category="Lasers", fire_range=6000.0, fire_pulse_count=2, fire_cone_width=40.0,
            accuracy_by_category={"All": 20.0}, default_projectile="P1",
        )
        reset_weapon_to_template(
            cfg, rule, lambda name: {"Projectile_Damage": _Resolved("55"), "Damage_Type": _Resolved("Laser")},
        )
        w = cfg.weapon
        self.assertEqual((w.fire_range, w.fire_pulse_count, w.fire_cone_width), (6000.0, 2, 40.0))
        self.assertEqual(w.accuracy_by_category, {"All": 20.0})
        self.assertEqual(w.source_projectile_name, "P1")
        self.assertEqual((w.damage, w.damage_type), (55.0, "Laser"))
        self.assertEqual(w.overridden_fields, set())
        self.assertEqual(w.override_notes, {})
        self.assertEqual(w.category, "Lasers")

    def test_reset_without_rule_blanks_weapon(self):
        cfg = HardpointConfig(name="T")
        cfg.weapon.fire_range = 5.0
        reset_weapon_to_template(cfg, None)
        self.assertEqual(cfg.weapon.fire_range, 0.0)


class ProjectileOrdering(unittest.TestCase):
    def test_default_then_direct_variants_then_rest(self):
        names = ["Zed", "Base", "Alpha", "Base_Red", "Base_Blue", "Beta"]
        children = {"Base": ["Base_Red", "Base_Blue", "Missing"], "Base_Red": ["Alpha"]}
        self.assertEqual(
            order_projectile_choices(names, children, "Base"),
            ["Base", "Base_Blue", "Base_Red", "Alpha", "Beta", "Zed"],
        )

    def test_no_default_is_alphabetical(self):
        self.assertEqual(order_projectile_choices(["b", "A", "c"], {}, ""), ["A", "b", "c"])

    def test_unknown_default_ignored(self):
        self.assertEqual(order_projectile_choices(["b", "a"], {"x": ["a"]}, "x"), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
