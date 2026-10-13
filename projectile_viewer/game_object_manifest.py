"""Reads a mod layer's own XML file manifests - GAMEOBJECTFILES.XML for
"game object" data (Units, Structures, etc) and HARDPOINTDATAFILES.XML for
Hardpoints - which list which XML files the game actually loads. Mods
sometimes leave orphaned/duplicate XML files lying around (identical
filename, identical Names inside, wrong folder) that the game never
actually loads. When two files in the same layer define the same Name,
preferring whichever one a manifest pins to a specific path resolves the
ambiguity the same way the real game would, instead of an arbitrary
file-processing order picking the orphan by accident.

There's no equivalent manifest for Projectiles, so this is only relevant to
Units and Hardpoints.
"""

import os
import xml.etree.ElementTree as ET

GAME_OBJECT_MANIFEST_BASENAME = "gameobjectfiles"
HARDPOINT_MANIFEST_BASENAME = "hardpointdatafiles"


def find_manifest(xml_root: str, manifest_basename: str = GAME_OBJECT_MANIFEST_BASENAME) -> str | None:
    """A layer's manifest sits directly at the top of its Data/XML root,
    alongside files like PROJECTILES.XML - not nested in a subfolder.
    """
    try:
        entries = os.listdir(xml_root)
    except OSError:
        return None
    for entry in entries:
        stem, ext = os.path.splitext(entry)
        if stem.lower() == manifest_basename and ext.lower() == ".xml":
            return os.path.join(xml_root, entry)
    return None


def _parse_entries(manifest_path: str) -> list[str]:
    """Raw <File> entry text, in document order. XML comments (including
    disabled `<!-- <File>...</File> -->` entries) are already dropped by
    ElementTree, which is exactly the behavior we want here.
    """
    try:
        tree = ET.parse(manifest_path)
    except ET.ParseError:
        return []
    return [el.text.strip() for el in tree.getroot().iter("File") if el.text and el.text.strip()]


def pinned_files(
    xml_root: str, discovered_files: list[str], manifest_basename: str = GAME_OBJECT_MANIFEST_BASENAME,
) -> set[str]:
    """Returns the subset of `discovered_files` (absolute paths under
    `xml_root`) that the manifest pins to one specific relative path - i.e.
    entries containing a folder (e.g. "AGD_Units/Republic/Space/Foo.xml").
    A bare filename entry (e.g. "Foo.xml") can't disambiguate between
    same-named files in different folders, so it's not treated as a pin -
    only path-qualified entries are strong enough to resolve a collision.
    """
    manifest_path = find_manifest(xml_root, manifest_basename)
    if manifest_path is None:
        return set()

    pinned_rel_paths = set()
    for entry in _parse_entries(manifest_path):
        normalized = entry.replace("/", os.sep).replace("\\", os.sep)
        if os.sep in normalized:
            pinned_rel_paths.add(normalized.lower())

    if not pinned_rel_paths:
        return set()

    result = set()
    for file_path in discovered_files:
        rel = os.path.relpath(file_path, xml_root).lower()
        if rel in pinned_rel_paths:
            result.add(file_path)
    return result
