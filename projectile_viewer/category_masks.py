"""Parses the GameObjectCategoryType enum file - a 64-bit category-mask bitmap.

Unlike Projectile/HardPoint/Unit elements (identified by a Name attribute),
each entry here IS its own XML tag: the tag name is the category name and its
text is the literal hex bitmask value (e.g. <Fighter>0x0000000000000001</Fighter>
is bit 1). Human-readable notes are plain trailing XML comments on the same
line, not a structured field - xml.etree.ElementTree drops comments entirely,
so this needs its own small line-based parser instead of xml_loader's
Name-keyed model.
"""

import re
from dataclasses import dataclass

FILE_BASENAME = "gameobjectcategorytype"

# <Tag> 0xHEX </Tag> [<!-- description -->], where the comment (if any) must
# be on the same line - [ \t]* (no \n) keeps a standalone comment on the next
# line from being misattributed to the preceding entry.
_ENTRY_PATTERN = re.compile(
    r"<(\w+)>\s*(0[xX][0-9A-Fa-f]+)\s*</\1>[ \t]*(?:<!--(.*?)-->)?"
)


@dataclass
class CategoryMaskEntry:
    name: str
    hex_value: str
    bit_number: int | None  # 1-64 for a single-bit flag; None for combos like "All"/"Hero"/"None"
    description: str


def is_category_mask_file(path: str) -> bool:
    import os
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.lower() == FILE_BASENAME


def parse_category_masks(file_path: str) -> list[CategoryMaskEntry]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    entries = []
    for match in _ENTRY_PATTERN.finditer(content):
        name, hex_text, comment = match.groups()
        try:
            value = int(hex_text, 16)
        except ValueError:
            continue
        is_single_bit = value != 0 and (value & (value - 1)) == 0
        entries.append(CategoryMaskEntry(
            name=name,
            hex_value=hex_text,
            bit_number=value.bit_length() if is_single_bit else None,
            description=(comment or "").strip(),
        ))
    return entries
