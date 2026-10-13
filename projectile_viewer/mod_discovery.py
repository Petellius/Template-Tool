"""Discovers mod folders and their loose XML data directories.

A mod's XML data isn't always at a fixed depth (e.g. A-Galaxy-Divided nests
it under an extra "AGD_TCW" folder, others don't), so we search for it
rather than assume a layout.
"""

import os
from dataclasses import dataclass, field


@dataclass
class ModCandidate:
    name: str
    path: str
    xml_roots: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.xml_roots)


def find_xml_roots(folder_path: str, max_depth: int = 4) -> list[str]:
    """Find directories named "xml" (case-insensitive) whose immediate
    parent is named "data" (case-insensitive), searched recursively up to
    max_depth levels below folder_path. Does not recurse into a match.

    Never descends into a "Mods" folder: that's reserved for this game's
    separately-managed mod layers, so scanning a base game folder must not
    pick up mods' own XML as if it belonged to the base/vanilla layer.
    """
    roots: list[str] = []

    def _walk(current: str, depth: int, parent_name: str):
        if depth > max_depth:
            return
        try:
            entries = list(os.scandir(current))
        except OSError:
            return

        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.lower() == "mods":
                continue
            if entry.name.lower() == "xml" and parent_name.lower() == "data":
                roots.append(entry.path)
                continue
            _walk(entry.path, depth + 1, entry.name)

    _walk(folder_path, 0, "")
    return roots


def discover_mods(mods_root: str) -> list[ModCandidate]:
    """List immediate subdirectories of mods_root and resolve each one's
    XML roots. Folders with none (e.g. this tool's own folder) are still
    returned with xml_roots=[] so callers can show them as unusable.
    """
    candidates: list[ModCandidate] = []
    try:
        entries = sorted(os.scandir(mods_root), key=lambda e: e.name.lower())
    except OSError:
        return candidates

    for entry in entries:
        if not entry.is_dir():
            continue
        candidates.append(ModCandidate(
            name=entry.name,
            path=entry.path,
            xml_roots=find_xml_roots(entry.path),
        ))

    return candidates
