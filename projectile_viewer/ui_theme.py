"""Central color palettes, section/action icons, and a rounded-rectangle
Canvas primitive shared by ui.py's dark/light themes and its card/badge
helpers. Kept separate from ui.py so every color used anywhere in the app
lives in exactly one place (previously ~15 hex literals were scattered
inline across ui.py, only usable in light mode since they never adapted to
dark mode).

Both palettes are deliberately parallel dicts with the same keys so
ui.py's theme-registration code can build either ttk theme from one
generic function fed a `palette` dict, instead of hand-writing the settings
twice (see ui.py's `_register_palette_theme`).
"""

PALETTES = {
    "dark": {
        "bg": "#1e1e1e",
        "surface": "#262626",
        "surface_border": "#3a3a3a",
        "fg": "#e6e6e6",
        "muted_fg": "#9a9a9a",
        "field_bg": "#2b2b2b",
        "button_bg": "#3c3c3c",
        "select_bg": "#3a6ea5",
        "accent": "#e0b24a",
        "accent_fg": "#1e1e1e",
        "accent_active": "#f0c766",
        "success": "#4caf6d",
        "warning": "#d99a3b",
        "danger": "#e5484d",
        "link": "#5cadff",
    },
    "light": {
        "bg": "#f4f5f7",
        "surface": "#ffffff",
        "surface_border": "#dfe2e8",
        "fg": "#1c1f26",
        "muted_fg": "#6b7280",
        "field_bg": "#ffffff",
        "button_bg": "#eceef2",
        "select_bg": "#3a6ea5",
        "accent": "#b8860b",
        "accent_fg": "#ffffff",
        "accent_active": "#a3780a",
        "success": "#1f8a4c",
        "warning": "#a3690a",
        "danger": "#c62828",
        "link": "#1a5fb4",
    },
}

ICONS = {
    # top-level / nested notebook tabs
    "reader": "\U0001F5A5",       # 🖥
    "config": "⚙",           # ⚙
    "battle_sim": "⚔",       # ⚔
    "projectiles": "\U0001F680",  # 🚀
    "units": "\U0001F6E1",        # 🛡
    "hardpoints": "\U0001F527",   # 🔧
    "category_masks": "\U0001F5C2",  # 🗂
    "behaviors": "\U0001F9E0",    # 🧠
    "weapon_rules": "\U0001F4DC",  # 📜
    "weapon_configs": "\U0001F52B",  # 🔫
    # actions
    "save": "\U0001F4BE",   # 💾
    "export": "\U0001F4E4",  # 📤
    "add": "➕",         # ➕
    "remove": "\U0001F5D1",  # 🗑
    "reset": "↺",       # ↺
    "view": "\U0001F441",    # 👁
    "new": "\U0001F195",     # 🆕
    "delete": "\U0001F5D1",  # 🗑
    "search": "\U0001F50D",  # 🔍
    "dark_mode": "\U0001F319",   # 🌙
    "light_mode": "☀",      # ☀
    "project": "\U0001F4C1",     # 📁
    "reload": "\U0001F504",      # 🔄
    "load_files": "\U0001F4C2",  # 📂
    "apply": "✅",           # ✅
    "simulate": "\U0001F3AF",    # 🎯
}


def icon(key: str) -> str:
    """Looks up an icon glyph by semantic key; returns "" for an unknown
    key so a missing/renamed key degrades to plain text instead of raising.
    """
    return ICONS.get(key, "")


def icon_text(key: str, text: str) -> str:
    """Prefixes `text` with the icon for `key` (falls back to bare `text`
    if the key isn't found), for building button/label/tab strings.
    """
    glyph = icon(key)
    return f"{glyph} {text}" if glyph else text


def _rounded_rect_points(x0: float, y0: float, x1: float, y1: float, radius: float) -> list[float]:
    radius = max(0, min(radius, (x1 - x0) / 2, (y1 - y0) / 2))
    return [
        x0 + radius, y0,
        x1 - radius, y0,
        x1, y0,
        x1, y0 + radius,
        x1, y1 - radius,
        x1, y1,
        x1 - radius, y1,
        x0 + radius, y1,
        x0, y1,
        x0, y1 - radius,
        x0, y0 + radius,
        x0, y0,
        x0 + radius, y0,
    ]


def draw_rounded_rect(canvas, x0, y0, x1, y1, radius=12, **kwargs) -> int:
    """Draws a rounded rectangle on `canvas` as a single smoothed polygon
    and returns its item id, so a caller can later reposition it (via
    `update_rounded_rect`) or recolor it (via `canvas.itemconfigure`)
    without redrawing from scratch.
    """
    points = _rounded_rect_points(x0, y0, x1, y1, radius)
    return canvas.create_polygon(points, smooth=True, **kwargs)


def update_rounded_rect(canvas, item_id: int, x0, y0, x1, y1, radius=12) -> None:
    """Repositions an existing rounded-rect polygon (from `draw_rounded_rect`)
    to a new size/position, e.g. in response to a <Configure> event.
    """
    canvas.coords(item_id, *_rounded_rect_points(x0, y0, x1, y1, radius))
