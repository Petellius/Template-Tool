"""Resolves a Project (base game folder + ordered mod layers) into the flat,
ordered file list that xml_loader.load_files expects.

Layer order = load order: base first, then each mod in listed order, so a
later mod overrides an earlier one and the base — matching xml_loader's
existing "last file in the list wins on Name collisions" behavior.
"""

import os
from dataclasses import dataclass, field

from .game_object_manifest import GAME_OBJECT_MANIFEST_BASENAME, HARDPOINT_MANIFEST_BASENAME, pinned_files
from .mod_discovery import find_xml_roots
from .xml_loader import LoadResult


def _find_xml_files(root: str) -> list[str]:
    """Recursively collect *.xml files under root, pruning any "Mods"
    directory along the way — same rule as find_xml_roots, so a whole-folder
    fallback scan of a base game install doesn't pick up its mods' XML.
    """
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() != "mods"]
        for filename in filenames:
            if filename.lower().endswith(".xml"):
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


@dataclass
class ModLayer:
    path: str
    enabled: bool = True


@dataclass
class Project:
    name: str
    base_path: str
    mods: list[ModLayer] = field(default_factory=list)


@dataclass
class LayerResolution:
    label: str
    path: str
    exists: bool
    enabled: bool
    xml_roots: list[str]
    files: list[str]
    used_fallback_scan: bool
    preferred_files: set[str] = field(default_factory=set)


@dataclass
class ResolvedProject:
    layers: list[LayerResolution] = field(default_factory=list)
    all_files: list[str] = field(default_factory=list)
    file_to_layer_index: dict[str, int] = field(default_factory=dict)
    missing_layers: list[str] = field(default_factory=list)
    preferred_files: set[str] = field(default_factory=set)


def _resolve_layer(label: str, path: str, enabled: bool) -> LayerResolution:
    if not os.path.isdir(path):
        return LayerResolution(
            label=label, path=path, exists=False, enabled=enabled,
            xml_roots=[], files=[], used_fallback_scan=False,
        )

    xml_roots = find_xml_roots(path)
    used_fallback_scan = False
    if not xml_roots and enabled:
        # No standard Data/XML layout found — fall back to scanning the
        # whole folder. Safe: xml_loader only pulls elements matching the
        # requested tag, so incidental unrelated XML can't corrupt results.
        xml_roots = [path]
        used_fallback_scan = True

    files: list[str] = []
    preferred: set[str] = set()
    if enabled:
        for root in xml_roots:
            root_files = _find_xml_files(root)
            files.extend(root_files)
            preferred.update(pinned_files(root, root_files, GAME_OBJECT_MANIFEST_BASENAME))
            preferred.update(pinned_files(root, root_files, HARDPOINT_MANIFEST_BASENAME))

    return LayerResolution(
        label=label, path=path, exists=True, enabled=enabled,
        xml_roots=xml_roots, files=files, used_fallback_scan=used_fallback_scan,
        preferred_files=preferred,
    )


def resolve_project(project: Project) -> ResolvedProject:
    resolved = ResolvedProject()

    base_layer = _resolve_layer("Base (vanilla)", project.base_path, enabled=True)
    resolved.layers.append(base_layer)

    for mod in project.mods:
        label = os.path.basename(os.path.normpath(mod.path)) or mod.path
        resolved.layers.append(_resolve_layer(label, mod.path, mod.enabled))

    for index, layer in enumerate(resolved.layers):
        if not layer.exists:
            resolved.missing_layers.append(layer.path)
            continue
        for file_path in layer.files:
            resolved.all_files.append(file_path)
            resolved.file_to_layer_index[file_path] = index
        resolved.preferred_files.update(layer.preferred_files)

    return resolved


@dataclass
class ClassifiedWarning:
    name: str
    from_file: str
    to_file: str
    from_layer_index: int | None
    to_layer_index: int | None
    severity: str  # "expected_override" | "same_layer_conflict"


def classify_duplicate_warnings(
    load_result: LoadResult, resolved: ResolvedProject
) -> list[ClassifiedWarning]:
    """Classify xml_loader's duplicate-name collisions by layer: a later
    layer overriding an earlier one is expected and by design; two files
    inside the SAME layer defining the same Name is a real authoring
    conflict worth flagging more strongly.
    """
    classified: list[ClassifiedWarning] = []

    for name, from_file, to_file in load_result.duplicate_collisions:
        from_index = resolved.file_to_layer_index.get(from_file)
        to_index = resolved.file_to_layer_index.get(to_file)
        severity = (
            "same_layer_conflict"
            if from_index is not None and from_index == to_index
            else "expected_override"
        )
        classified.append(ClassifiedWarning(
            name=name, from_file=from_file, to_file=to_file,
            from_layer_index=from_index, to_layer_index=to_index, severity=severity,
        ))

    return classified
