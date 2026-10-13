"""Scans XML files for <Behavior>, <SpaceBehavior>, and <LandBehavior> tags
and extracts the distinct single flag values inside them.

These tags appear on many different element types (units, structures,
projectiles, props) - not tied to any one schema - and hold comma-separated
flag lists, sometimes spanning multiple lines or with a stray XML comment
embedded mid-list (which would truncate ElementTree's default .text capture
at the comment). XML comments are stripped from the whole file first - this
both fixes that truncation risk and correctly excludes entirely-commented-out
tags, which the game never loads - then each tag's value is tokenized on
commas. No per-file/per-list provenance is kept, only the deduplicated
single values.
"""

import re

BEHAVIOR_TAGS = ("Behavior", "SpaceBehavior", "LandBehavior")

_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
# These tags never carry attributes in practice, so the open tag is matched as
# exactly <Tag> (optional whitespace, then '>' immediately) - critically this
# does NOT match a self-closing <Tag/> or <Tag />, which would otherwise be
# mistaken for an opening tag and greedily swallow everything up to some
# unrelated later </Tag> as its "content".
_TAG_PATTERN = re.compile(
    r"<(" + "|".join(BEHAVIOR_TAGS) + r")\s*>(.*?)</\1>", re.DOTALL
)


def scan_file(file_path: str) -> dict[str, set[str]]:
    """Returns {tag_name: {distinct flag values found in this file}}."""
    found: dict[str, set[str]] = {tag: set() for tag in BEHAVIOR_TAGS}
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        return found

    content = _COMMENT_PATTERN.sub("", content)

    for match in _TAG_PATTERN.finditer(content):
        tag_name, raw_value = match.groups()
        for token in raw_value.split(","):
            token = token.strip()
            if token:
                found[tag_name].add(token)

    return found


def scan_files(file_paths: list[str]) -> dict[str, set[str]]:
    """Merge scan_file results across many files into one {tag: {values}} map."""
    combined: dict[str, set[str]] = {tag: set() for tag in BEHAVIOR_TAGS}
    for path in file_paths:
        per_file = scan_file(path)
        for tag, values in per_file.items():
            combined[tag].update(values)
    return combined


CONTEXT_SPACE_ONLY = "Space Only"
CONTEXT_LAND_ONLY = "Land Only"
CONTEXT_SPACE_AND_LAND = "Space+Land"
CONTEXT_GENERAL = "General"


def merge_with_context(combined: dict[str, set[str]]) -> dict[str, str]:
    """Flatten {tag: {values}} into one {value: context_label} map.

    A value found ONLY under SpaceBehavior (never LandBehavior or the plain
    Behavior tag) is "Space Only"; only under LandBehavior is "Land Only";
    under both Space and Land (but never plain Behavior) is "Space+Land";
    anything that ever appears under the plain Behavior tag - or under both
    context-specific tags - is "General".

    Values are canonicalized to UPPERCASE before merging: real flags are
    consistently UPPER_SNAKE_CASE, and an occasional lowercase/mixed-case
    variant seen in the wild (e.g. "Selectable" vs "SELECTABLE") is an
    authoring typo, not a distinct flag - it must not appear as a separate
    row just because its case differs.
    """
    value_to_tags: dict[str, set[str]] = {}
    for tag, values in combined.items():
        for value in values:
            value_to_tags.setdefault(value.upper(), set()).add(tag)

    result: dict[str, str] = {}
    for value, tags in value_to_tags.items():
        if tags == {"SpaceBehavior"}:
            result[value] = CONTEXT_SPACE_ONLY
        elif tags == {"LandBehavior"}:
            result[value] = CONTEXT_LAND_ONLY
        elif tags == {"SpaceBehavior", "LandBehavior"}:
            result[value] = CONTEXT_SPACE_AND_LAND
        else:
            result[value] = CONTEXT_GENERAL
    return result
