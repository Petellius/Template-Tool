import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from projectile_viewer.hardpoint_assignments import load_assignments, save_assignments
from projectile_viewer.hardpoint_config import KIND_NON_WEAPON, KIND_WEAPON
from projectile_viewer.hardpoint_data import extract_fields
from projectile_viewer.hardpoint_view import (
    compare_to_config, config_from_hardpoint, group_hardpoints, hardpoint_signature, read_unit_hardpoints,
)
from projectile_viewer.xml_loader import Entry, load_files

VENATOR = os.path.join(
    "C:\\", "Program Files (x86)", "Steam", "steamapps", "common", "Star Wars Empire at War", "corruption",
    "Mods", "A-Galaxy-Divided", "AGD_TCW", "Data", "XML", "AGD_Hardpoints", "Republic_Space",
    "HardPoints_Republic_Venator.XML",
)

TURRET = """
<HardPoint Name="{name}">
  <Type>HARD_POINT_WEAPON_LASER</Type>
  <Is_Targetable>No</Is_Targetable><Is_Destroyable>No</Is_Destroyable><Is_Turret>Yes</Is_Turret>
  <Tooltip_Text>TEXT_WEAPON</Tooltip_Text><Health>1.0</Health>
  <Model_To_Attach>VenatorDTL_00.ALO</Model_To_Attach>
  <Attachment_Bone>{bone}</Attachment_Bone><Collision_Mesh>{bone}</Collision_Mesh>
  <Fire_Bone_A>MUZZLEA_00</Fire_Bone_A><Fire_Bone_B>MUZZLEA_00</Fire_Bone_B>
  <Fire_Cone_Width>40.0</Fire_Cone_Width><Fire_Cone_Height>40.0</Fire_Cone_Height>
  <Turret_Rotate_Speed>0.35</Turret_Rotate_Speed><Turret_Bone_Name>TURRET_00</Turret_Bone_Name>
  <Fire_Projectile_Type>Proj_A</Fire_Projectile_Type>
  <Fire_Min_Recharge_Seconds>7.0</Fire_Min_Recharge_Seconds><Fire_Max_Recharge_Seconds>18.0</Fire_Max_Recharge_Seconds>
  <Fire_Pulse_Count>2</Fire_Pulse_Count><Fire_Pulse_Delay_Seconds>1.0</Fire_Pulse_Delay_Seconds>
  <Fire_Range_Distance>{range}</Fire_Range_Distance><Fire_SFXEvent>Generic_HvyTurbolaser</Fire_SFXEvent>
  <Fire_Inaccuracy_Distance> Fighter, 100.0 </Fire_Inaccuracy_Distance>
  <Fire_Inaccuracy_Distance> Capital, 45.0 </Fire_Inaccuracy_Distance>
  <Allow_Opportunity_Fire_When_Idle>True</Allow_Opportunity_Fire_When_Idle>
</HardPoint>"""

SHIELD = """
<HardPoint Name="{name}">
  <Type>HARD_POINT_SHIELD_GENERATOR</Type>
  <Is_Targetable>No</Is_Targetable><Is_Destroyable>No</Is_Destroyable>
  <Tooltip_Text>TEXT_SG</Tooltip_Text><Health>1.0</Health>
  <Attachment_Bone>SHIELDGEN_00</Attachment_Bone><Collision_Mesh>SHIELDGEN_00</Collision_Mesh>
</HardPoint>"""


def entries(*xml_blocks):
    root = ET.fromstring("<HardPoints>" + "".join(xml_blocks) + "</HardPoints>")
    return {el.get("Name"): Entry(element=el, source_file="t.xml") for el in root}


def unit_entries(hardpoints_text):
    unit = ET.Element("SpaceUnit", Name="Ship")
    ET.SubElement(unit, "HardPoints").text = hardpoints_text
    return {"Ship": Entry(element=unit, source_file="u.xml")}


class Reader(unittest.TestCase):
    def test_keeps_every_hardpoint_in_unit_order_and_reports_missing(self):
        hps = entries(TURRET.format(name="T01", bone="Base_00", range="6000.0"), SHIELD.format(name="SG_01"))
        listed, missing = read_unit_hardpoints("Ship", unit_entries("SG_01, T01, Ghost,"), hps)
        self.assertEqual([h.name for h in listed], ["SG_01", "T01"])  # unit order; non-targetable shield kept
        self.assertEqual(missing, ["Ghost"])
        self.assertEqual([h.kind for h in listed], [KIND_NON_WEAPON, KIND_WEAPON])


class Signature(unittest.TestCase):
    def test_ignores_bones_but_not_weapon_values(self):
        a = entries(TURRET.format(name="T01", bone="Base_00", range="6000.0"))["T01"]
        b = entries(TURRET.format(name="T02", bone="Base_07", range="6000.0"))["T02"]
        c = entries(TURRET.format(name="T03", bone="Base_01", range="9000.0"))["T03"]
        sa, sb, sc = (hardpoint_signature(extract_fields(e.element)) for e in (a, b, c))
        self.assertEqual(sa, sb)
        self.assertNotEqual(sa, sc)


class PlacementFields(unittest.TestCase):
    def test_per_mount_model_copy_does_not_split_a_turret_group(self):
        a = TURRET.format(name="T01", bone="Base_00", range="6000.0")
        b = TURRET.format(name="T02", bone="Base_01", range="6000.0").replace("VenatorDTL_00", "VenatorDTL_01")
        e = entries(a, b)
        sigs = {hardpoint_signature(extract_fields(x.element)) for x in e.values()}
        self.assertEqual(len(sigs), 1)

    def test_fire_bones_are_placement_on_fixed_weapons_but_not_on_turrets(self):
        fixed = TURRET.replace("<Is_Turret>Yes</Is_Turret>", "")
        a = entries(fixed.format(name="L1", bone="MuzzleB_00", range="3000.0"))["L1"]
        b = entries(
            fixed.format(name="L2", bone="MuzzleB_01", range="3000.0").replace("MUZZLEA_00", "MUZZLEA_09")
        )["L2"]
        self.assertEqual(
            hardpoint_signature(extract_fields(a.element)), hardpoint_signature(extract_fields(b.element)),
        )

        t1 = entries(TURRET.format(name="T1", bone="Base_00", range="1.0"))["T1"]
        t2 = entries(TURRET.format(name="T2", bone="Base_00", range="1.0").replace("MUZZLEA_00", "MUZZLEA_09"))["T2"]
        self.assertNotEqual(
            hardpoint_signature(extract_fields(t1.element)), hardpoint_signature(extract_fields(t2.element)),
        )


class Grouping(unittest.TestCase):
    def setUp(self):
        self.hps = entries(
            TURRET.format(name="HP_V_Turret01", bone="Base_00", range="6000.0"),
            TURRET.format(name="HP_V_Turret02", bone="Base_01", range="6000.0"),
            TURRET.format(name="HP_V_LC01", bone="Base_02", range="3000.0"),
            SHIELD.format(name="HP_V_SG_01"),
            SHIELD.format(name="HP_V_SG_02"),
        )
        self.listed, _ = read_unit_hardpoints(
            "Ship", unit_entries("HP_V_Turret01, HP_V_Turret02, HP_V_LC01, HP_V_SG_01, HP_V_SG_02"), self.hps,
        )

    def test_similarity_groups(self):
        groups = group_hardpoints(self.listed, {}, {})
        self.assertEqual(
            [(g.label, g.count) for g in groups], [("HP_V_Turret", 2), ("HP_V_LC", 1), ("HP_V_SG", 2)],
        )

    def test_assignment_wins_over_similarity(self):
        groups = group_hardpoints(self.listed, {"HP_V_Turret01": "My Cfg", "HP_V_LC01": "My Cfg"}, {})
        mine = next(g for g in groups if g.config_name == "My Cfg")
        self.assertEqual(sorted(m.name for m in mine.members), ["HP_V_LC01", "HP_V_Turret01"])
        self.assertEqual(mine.label, "My Cfg")


class ConfigAndCompare(unittest.TestCase):
    def setUp(self):
        self.fields = extract_fields(entries(TURRET.format(name="T01", bone="Base_00", range="6000.0"))["T01"].element)

    def test_config_from_turret_hardpoint(self):
        cfg = config_from_hardpoint(self.fields, "Dual Turret", hardpoint_name="T01", theatre="Space")
        self.assertEqual((cfg.kind, cfg.is_turret, cfg.turret_bone_name), (KIND_WEAPON, True, "TURRET_00"))
        self.assertEqual(cfg.model_to_attach, "VenatorDTL_00.ALO")
        w = cfg.weapon
        self.assertEqual((w.fire_range, w.fire_cone_width, w.turret_rotate_speed), (6000.0, 40.0, 0.35))
        self.assertEqual((w.fire_min_recharge, w.fire_max_recharge, w.fire_pulse_count), (7.0, 18.0, 2))
        self.assertEqual(list(w.accuracy_by_category), ["Fighter", "Capital"])
        self.assertEqual(w.source_projectile_name, "Proj_A")
        self.assertTrue(w.modifiers)  # opportunity-fire flag was seeded

    def test_unchanged_hardpoint_has_no_mismatches(self):
        cfg = config_from_hardpoint(self.fields, "Dual Turret")
        self.assertEqual(compare_to_config(self.fields, cfg), [])

    def test_reports_only_changed_field(self):
        cfg = config_from_hardpoint(self.fields, "Dual Turret")
        cfg.weapon.fire_range = 7500.0
        diffs = compare_to_config(self.fields, cfg)
        self.assertEqual(
            [(d.field, d.actual, d.expected) for d in diffs], [("Fire_Range_Distance", "6000.0", "7500.0")],
        )

    def test_accuracy_order_difference_is_a_mismatch(self):
        cfg = config_from_hardpoint(self.fields, "Dual Turret")
        cfg.weapon.accuracy_by_category = {"Capital": 45.0, "Fighter": 100.0}
        self.assertEqual([d.field for d in compare_to_config(self.fields, cfg)], ["Fire_Inaccuracy_Distance"])

    def test_non_weapon_config_ignores_weapon_block(self):
        sg = extract_fields(entries(SHIELD.format(name="SG"))["SG"].element)
        cfg = config_from_hardpoint(sg, "Shield Gen")
        self.assertEqual(cfg.kind, KIND_NON_WEAPON)
        self.assertEqual(compare_to_config(sg, cfg), [])
        cfg.health = 450.0
        self.assertEqual([d.field for d in compare_to_config(sg, cfg)], ["Health"])


class SharedData(unittest.TestCase):
    def setUp(self):
        hps = entries(
            TURRET.format(name="T01", bone="Base_00", range="6000.0"),
            TURRET.format(name="T02", bone="Base_01", range="6000"),
            TURRET.format(name="T03", bone="Base_02", range="9000.0"),
        )
        self.listed, _ = read_unit_hardpoints("Ship", unit_entries("T01, T02, T03"), hps)

    def test_single_hardpoint_shows_everything(self):
        from projectile_viewer.hardpoint_view import summarize_fields
        data = summarize_fields(self.listed[:1])
        self.assertEqual(data.count, 1)
        self.assertEqual(data.varying, {})
        self.assertEqual(data.shared["Fire_Range_Distance"], ["6000.0"])
        self.assertEqual(data.shared["Fire_Inaccuracy_Distance"], ["Fighter, 100.0", "Capital, 45.0"])

    def test_shared_vs_varying_across_a_selection(self):
        from projectile_viewer.hardpoint_view import summarize_fields
        data = summarize_fields(self.listed)
        self.assertIn("Health", data.shared)
        self.assertNotIn("Attachment_Bone", data.shared)           # differs per mount
        self.assertIn("Attachment_Bone", data.varying)
        self.assertIn("Fire_Range_Distance", data.varying)
        ranges = {tuple(v.values): v.members for v in data.varying["Fire_Range_Distance"]}
        self.assertEqual(len(ranges), 2)                          # 6000 == 6000.0 grouped together
        self.assertEqual(sorted(ranges[("6000.0",)]), ["T01", "T02"])
        self.assertEqual(ranges[("9000.0",)], ["T03"])

    def test_tag_missing_on_some_members_is_varying(self):
        from projectile_viewer.hardpoint_view import summarize_fields
        self.listed[0].fields["Extra_Tag"] = ["x"]
        data = summarize_fields(self.listed)
        self.assertIn("Extra_Tag", data.varying)
        notset = [v for v in data.varying["Extra_Tag"] if v.values == []]
        self.assertEqual(len(notset), 1)
        self.assertEqual(len(notset[0].members), 2)


class Overrides(unittest.TestCase):
    def setUp(self):
        self.fields = extract_fields(entries(TURRET.format(name="T01", bone="Base_00", range="6000.0"))["T01"].element)
        self.cfg = config_from_hardpoint(self.fields, "Dual Turret")

    def test_apply_overrides_replaces_adds_and_clears(self):
        from projectile_viewer.hardpoint_view import apply_overrides
        out = apply_overrides(
            self.fields, {"Fire_Range_Distance": ["7000"], "New_Tag": ["x"], "Fire_SFXEvent": []},
        )
        self.assertEqual(out["Fire_Range_Distance"], ["7000"])
        self.assertEqual(out["New_Tag"], ["x"])
        self.assertNotIn("Fire_SFXEvent", out)
        self.assertEqual(self.fields["Fire_Range_Distance"], ["6000.0"])  # original untouched

    def test_override_replaces_config_mismatch_with_xml_vs_override(self):
        from projectile_viewer.hardpoint_view import compare_with_overrides
        self.cfg.weapon.fire_range = 9999.0          # config disagrees with the XML (6000)
        # no override: config mismatch is reported
        self.assertEqual(
            [m.field for m in compare_with_overrides(self.fields, self.cfg, {})], ["Fire_Range_Distance"],
        )
        # override matching the XML silences it (the user chose 6000 over the template)
        self.assertEqual(compare_with_overrides(self.fields, self.cfg, {"Fire_Range_Distance": ["6000"]}), [])
        # override differing from the XML reports XML-vs-override instead
        diffs = compare_with_overrides(self.fields, self.cfg, {"Fire_Range_Distance": ["7000"]})
        self.assertEqual([(d.field, d.actual, d.expected) for d in diffs],
                         [("Fire_Range_Distance", "6000.0", "7000")])

    def test_override_without_config_flags_xml_that_lacks_it(self):
        from projectile_viewer.hardpoint_view import compare_with_overrides
        diffs = compare_with_overrides(self.fields, None, {"Fire_Cone_Width": ["55"]})
        self.assertEqual([(d.field, d.actual, d.expected) for d in diffs],
                         [("Fire_Cone_Width", "40.0", "55")])
        self.assertEqual(compare_with_overrides(self.fields, None, {}), [])

    def test_store_round_trip(self):
        from projectile_viewer.hardpoint_overrides import load_overrides, save_overrides
        path = os.path.join(tempfile.mkdtemp(), "o.json")
        save_overrides({"Venator": {"T01": {"Fire_Range_Distance": ["7000"], "Cleared": []}, "T02": {}}}, path)
        self.assertEqual(load_overrides(path), {"Venator": {"T01": {"Fire_Range_Distance": ["7000"], "Cleared": []}}})
        self.assertEqual(load_overrides(path + ".missing"), {})


class Assignments(unittest.TestCase):
    def test_round_trip(self):
        path = os.path.join(tempfile.mkdtemp(), "a.json")
        save_assignments({"Venator": {"T01": "Dual Turret"}, "Empty": {}}, path)
        self.assertEqual(load_assignments(path), {"Venator": {"T01": "Dual Turret"}})
        self.assertEqual(load_assignments(path + ".missing"), {})


@unittest.skipUnless(os.path.isfile(VENATOR), "AGD Venator hardpoint file not present")
class RealVenator(unittest.TestCase):
    def test_venator_file_groups_sensibly(self):
        result = load_files([VENATOR], "HardPoint")
        names = list(result.entries)
        listed, missing = read_unit_hardpoints("Ship", unit_entries(", ".join(names)), result.entries)
        self.assertEqual(len(listed), len(names))
        self.assertEqual(missing, [])
        groups = group_hardpoints(listed, {}, {})
        self.assertLess(len(groups), len(listed))  # similar hardpoints collapse
        self.assertTrue(any(g.count > 1 and g.kind == KIND_WEAPON for g in groups))
        self.assertEqual({g.kind for g in groups}, {KIND_WEAPON, KIND_NON_WEAPON})
        # every hardpoint matches the config built from itself
        for hp in listed:
            cfg = config_from_hardpoint(hp.fields, hp.name)
            self.assertEqual(compare_to_config(hp.fields, cfg), [], hp.name)


if __name__ == "__main__":
    unittest.main()
