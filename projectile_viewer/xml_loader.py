"""Loads EAW-style XML files and indexes elements of a given tag by their Name attribute.

Generic over tag name so the same loader works for Projectile, HardPoint, and
Unit elements in later phases of the template tool.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# Root/element tags this tool ever cares about. A file that fails to parse
# but mentions none of these was never going to contribute data anyway
# (AI templates, story triggers, etc.), so its parse error is noise.
RELEVANT_TAGS = (
    "Projectile", "SpaceUnit", "Squadron", "GroundCompany",
    "Template", "GroundInfantry", "GroundVehicle", "Container",
)


def _mentions_relevant_tag(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return True  # can't check - err on the side of reporting it

    lowered = content.lower()
    return any(f"<{tag.lower()}" in lowered for tag in RELEVANT_TAGS)


@dataclass
class LoadResult:
    # Name -> the resolved (element, source_file) entry actually kept.
    entries: dict[str, "Entry"] = field(default_factory=dict)
    # Names that were defined in more than one loaded file; last-loaded wins.
    duplicate_warnings: list[str] = field(default_factory=list)
    # Same collisions as duplicate_warnings, structured as (name, first_file, second_file)
    # for callers (like project.py) that need the file paths without parsing the message.
    duplicate_collisions: list[tuple[str, str, str]] = field(default_factory=list)
    # Files that failed to parse, with the error message.
    parse_errors: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Entry:
    element: ET.Element
    source_file: str


def load_files(
    file_paths: list[str], tag_name: str | list[str], preferred_files: set[str] | None = None,
) -> LoadResult:
    """Parse each file and collect all `<tag_name Name="...">` elements.

    `tag_name` may be a single tag name or a list of tag names to collect
    together into one Name-keyed pool (e.g. Land units span both
    GroundVehicle and GroundInfantry).

    Later files in `file_paths` take precedence on Name collisions, matching
    how the mod's per-file overrides are meant to behave - UNLESS the file
    that's about to be overwritten is in `preferred_files` (a mod's own
    GAMEOBJECTFILES.XML manifest pinning a Name's real source) and the new
    one isn't, in which case the manifest-pinned file wins regardless of
    processing order. This resolves same-layer collisions against an
    orphaned/duplicate file the way the actual game would, instead of
    arbitrary file order picking the orphan by accident.
    """
    tag_names = [tag_name] if isinstance(tag_name, str) else list(tag_name)
    preferred_files = preferred_files or set()
    result = LoadResult()

    for path in file_paths:
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            if _mentions_relevant_tag(path):
                result.parse_errors.append((path, str(exc)))
            continue

        root = tree.getroot()
        for tag in tag_names:
            for element in root.iter(tag):
                name = element.get("Name")
                if not name:
                    continue
                existing = result.entries.get(name)
                if existing is not None and existing.source_file != path:
                    existing_preferred = existing.source_file in preferred_files
                    new_preferred = path in preferred_files
                    if existing_preferred and not new_preferred:
                        # Keep the manifest-pinned file; record the collision
                        # (new file lost) but don't overwrite.
                        result.duplicate_warnings.append(
                            f"{name!r} also defined in {path!r} - keeping "
                            f"{existing.source_file!r} (pinned by GAMEOBJECTFILES.XML)"
                        )
                        result.duplicate_collisions.append((name, path, existing.source_file))
                        continue

                    result.duplicate_warnings.append(
                        f"{name!r} defined in both {existing.source_file!r} "
                        f"and {path!r} - using the latter"
                    )
                    result.duplicate_collisions.append((name, existing.source_file, path))
                result.entries[name] = Entry(element=element, source_file=path)

    return result
