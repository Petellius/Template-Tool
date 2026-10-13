"""Resolves EAW's Variant_Of_Existing_Type inheritance chains.

A variant element only lists the fields it overrides; everything else comes
from its base. This module walks the chain to the root and flattens it into
one resolved field map, keeping track of which element in the chain last set
each field (its "provenance") so the viewer can show overrides explicitly.
"""

from dataclasses import dataclass

from .xml_loader import Entry

INHERITANCE_TAG = "Variant_Of_Existing_Type"


class InheritanceCycleError(Exception):
    pass


@dataclass
class ResolvedField:
    value: str
    source_name: str


def resolve_chain(entries: dict[str, Entry], name: str) -> list[str]:
    """Return the inheritance chain for `name`, root-first, ending with `name` itself.

    Raises InheritanceCycleError if a Variant_Of_Existing_Type loop is detected.
    """
    chain: list[str] = []
    visited: set[str] = set()
    current = name

    while current is not None:
        if current in visited:
            raise InheritanceCycleError(
                f"Variant_Of_Existing_Type cycle detected involving {current!r}"
            )
        visited.add(current)
        chain.append(current)

        entry = entries.get(current)
        if entry is None:
            break
        parent_element = entry.element.find(INHERITANCE_TAG)
        current = parent_element.text.strip() if parent_element is not None and parent_element.text else None

    chain.reverse()
    return chain


def merge_chain(entries: dict[str, Entry], chain: list[str]) -> dict[str, ResolvedField]:
    """Flatten a root-first chain into resolved {field: ResolvedField} data.

    A tag's mere presence counts as an override, even if empty
    (e.g. `<Projectile_Ground_Detonation_Particle/>` explicitly clears a base value).
    Later elements in the chain overwrite earlier ones.
    """
    resolved: dict[str, ResolvedField] = {}

    for link_name in chain:
        entry = entries.get(link_name)
        if entry is None:
            continue
        for child in entry.element:
            tag = child.tag
            if tag == INHERITANCE_TAG:
                continue
            value = (child.text or "").strip()
            resolved[tag] = ResolvedField(value=value, source_name=link_name)

    return resolved
