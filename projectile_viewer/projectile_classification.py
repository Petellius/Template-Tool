"""Classifies projectiles as Template / Base Projectile / Final Projectile.

Based purely on each projectile's OWN (unresolved) XML data and its position
in the Variant_Of_Existing_Type tree - not the merged/inherited data used for
display, since a "template" is defined by what it does NOT itself declare.

- Templates: have variants (other projectiles use them as a base), but
  themselves declare no model and have no parent - a pure abstract base.
- Base Projectiles: have variants, and are either a variant of something else
  themselves, or already carry a model - i.e. everything with children that
  isn't a pure Template.
- Final Projectiles: nothing else varies from them - the leaf/concrete
  projectiles actually referenced by hardpoints.
"""

import xml.etree.ElementTree as ET

from .xml_loader import Entry

MODEL_TAGS = ("Space_Model_Name", "Land_Model_Name")
VARIANT_TAG = "Variant_Of_Existing_Type"

TEMPLATE = "Templates"
BASE = "Base Projectiles"
FINAL = "Final Projectiles"
ALL_CATEGORIES = (TEMPLATE, BASE, FINAL)


def _direct_child_text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    if child is None or not (child.text or "").strip():
        return None
    return child.text.strip()


def build_children_map(entries: dict[str, Entry]) -> dict[str, list[str]]:
    """name -> names of projectiles that declare it as their Variant_Of_Existing_Type."""
    children: dict[str, list[str]] = {}
    for name, entry in entries.items():
        parent = _direct_child_text(entry.element, VARIANT_TAG)
        if parent:
            children.setdefault(parent, []).append(name)
    return children


def classify(name: str, entries: dict[str, Entry], children_map: dict[str, list[str]]) -> str:
    entry = entries[name]
    has_children = bool(children_map.get(name))
    if not has_children:
        return FINAL

    has_parent = _direct_child_text(entry.element, VARIANT_TAG) is not None
    has_model = any(_direct_child_text(entry.element, tag) is not None for tag in MODEL_TAGS)
    if not has_parent and not has_model:
        return TEMPLATE
    return BASE


def classify_all(entries: dict[str, Entry]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Convenience: build the children map and classify every entry in one pass."""
    children_map = build_children_map(entries)
    categories = {name: classify(name, entries, children_map) for name in entries}
    return children_map, categories
