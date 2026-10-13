"""Direct (non-inherited) field extraction for HardPoint elements.

Unlike Projectiles/Units, a <HardPoint Name="..."> has no
Variant_Of_Existing_Type - every hardpoint is fully self-contained - so
there's no chain to resolve, just its own children. Some tags legitimately
repeat on one hardpoint (e.g. Fire_Inaccuracy_Distance once per unit
category), so every occurrence is kept rather than the usual "last one wins".
"""

import xml.etree.ElementTree as ET

# Fields that name a Projectile. Fire_Projectile_Type is the common one;
# Blast_Ability_Fire_Projectile_Type is a rarer special-ability variant found
# in the legacy HARDPOINTS_UNDERWORLD.XML file (a hero's "blast" ability
# firing a different projectile than its normal weapon).
PROJECTILE_REFERENCE_TAGS = ("Fire_Projectile_Type", "Blast_Ability_Fire_Projectile_Type")


def extract_fields(element: ET.Element) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for child in element:
        value = (child.text or "").strip()
        fields.setdefault(child.tag, []).append(value)
    return fields
