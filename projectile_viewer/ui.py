"""Tkinter UI for the Projectile Template Viewer."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import app_settings, field_groups, recent_projects, unit_field_groups, hardpoint_field_groups
from .ui_theme import PALETTES, draw_rounded_rect, icon, icon_text, update_rounded_rect
from .behaviors import scan_files, merge_with_context
from .behavior_descriptions import get_description, load_overrides, save_overrides
from .category_masks import CategoryMaskEntry, is_category_mask_file, parse_category_masks
from .hardpoint_data import PROJECTILE_REFERENCE_TAGS, extract_fields
from .inheritance import InheritanceCycleError, merge_chain, resolve_chain
from .project import ClassifiedWarning, Project, ResolvedProject, classify_duplicate_warnings, resolve_project
from .projectile_classification import ALL_CATEGORIES, build_children_map, classify_all
from .xml_loader import LoadResult, load_files
from .project_dialog import ProjectDialog
from .weapon_analysis import analyze as analyze_weapon_config
from .weapon_config import (
    CONTEXT_HARDPOINT,
    CONTEXT_UNIT_WEAPON,
    WeaponConfig,
    seed_from_hardpoint,
    seed_from_projectile,
    seed_from_unit_weapon,
    to_float as weapon_config_to_float,
    to_int as weapon_config_to_int,
)
from .weapon_modifiers import (
    KIND_BOOL,
    MODIFIER_CATALOG,
    MODIFIERS_BY_KEY,
    format_modifier_value,
    modifiers_for_context,
    parse_bool,
)
from .weapon_config_export import build_hardpoints_file_xml, build_unit_weapons_file_xml
from .weapon_config_store import load_configs as load_weapon_configs, save_configs as save_weapon_configs
from .weapon_rules import RULE_FIELDS, WeaponRule, apply_rule, load_rules as load_weapon_rules, save_rules as save_weapon_rules
from .combat_sim import simulate as simulate_battle
from .game_constants import (
    DamageMatrix,
    all_target_types,
    find_game_constants_file,
    parse_damage_matrix,
    parse_shield_recharge_interval,
)
from .unit_loadout import HardpointGroup, UnitLoadout, build_loadout, build_unit_weapon_group

PROJECTILE_TAG = "Projectile"
SPACEUNIT_TAG = "SpaceUnit"
GROUNDVEHICLE_TAG = "GroundVehicle"
GROUNDINFANTRY_TAG = "GroundInfantry"
GROUNDCOMPANY_TAG = "GroundCompany"
CONTAINER_TAG = "Container"
SQUADRON_TAG = "Squadron"

THEATRE_SPACE = "Space"
THEATRE_LAND = "Land"

UNIT_KIND_UNITS = "Units"
UNIT_KIND_TEAMS = "Teams"
UNIT_KIND_COMPANIES = "Companies"

# (theatre, kind) -> tags to load. Some combinations have no equivalent in
# this mod's schema (e.g. Space has no "company" concept) and simply yield
# an empty list, which the loader safely returns zero entries for.
THEATRE_UNIT_TAGS = {
    (THEATRE_SPACE, UNIT_KIND_UNITS): [SPACEUNIT_TAG],
    (THEATRE_SPACE, UNIT_KIND_TEAMS): [CONTAINER_TAG],
    (THEATRE_SPACE, UNIT_KIND_COMPANIES): [SQUADRON_TAG],
    (THEATRE_LAND, UNIT_KIND_UNITS): [GROUNDVEHICLE_TAG, GROUNDINFANTRY_TAG],
    (THEATRE_LAND, UNIT_KIND_TEAMS): [CONTAINER_TAG],
    (THEATRE_LAND, UNIT_KIND_COMPANIES): [GROUNDCOMPANY_TAG],
}
UNIT_ABILITIES_TAG = "Unit_Abilities_Data"
UNIT_ABILITY_TAG = "Unit_Ability"
HARDPOINT_TAG = "HardPoint"
PROJECTILE_LINK_TAG = "projectile-link"
MAX_SHOWN_PARSE_ERRORS = 10
CATEGORY_ALL = "All"
TARGET_TYPE_NONE = "(none)"

DARK_THEME_NAME = "agd_dark"
LIGHT_THEME_NAME = "agd_light"


def _display_folder(folder: str) -> str:
    """Shorten a folder path to start right after its "Data/XML" segment
    (e.g. ".../AGD_TCW/Data/XML/AGD_Units/Republic/Space" -> "AGD_Units/Republic/Space"),
    dropping both the mod/install path above it and the "Data/XML" base
    itself, since every layer has one and it adds no information. Falls
    back to starting at "Data" (or the full path) if no "Data/XML" pair is
    found - e.g. a manually-added folder outside the usual layout.
    """
    parts = os.path.normpath(folder).split(os.sep)
    for i, part in enumerate(parts):
        if part.lower() == "data" and i + 1 < len(parts) and parts[i + 1].lower() == "xml":
            remainder = parts[i + 2:]
            return os.sep.join(remainder) if remainder else "(Data/XML root)"
    for i, part in enumerate(parts):
        if part.lower() == "data":
            return os.sep.join(parts[i:])
    return folder


def render_name_tree(tree: ttk.Treeview, names: list[str], entries: dict, query: str, grouped: bool):
    """Populate `tree` (a Treeview whose leaf item ids are the entry names
    themselves) with `names`, filtered by `query` (case-insensitive
    substring). When `grouped` is True, leaves are nested under collapsible
    Folder -> XML file heading nodes (derived from each entry's source
    file); otherwise it's a flat alphabetical list, same as before.
    """
    tree.delete(*tree.get_children())
    query = query.strip().lower()
    matched = sorted(n for n in names if not query or query in n.lower())

    if not grouped:
        for name in matched:
            tree.insert("", tk.END, iid=name, text=name)
        return

    by_folder: dict[str, dict[str, list[str]]] = {}
    for name in matched:
        source = entries[name].source_file
        folder = os.path.dirname(source)
        filename = os.path.basename(source)
        by_folder.setdefault(folder, {}).setdefault(filename, []).append(name)

    auto_open = bool(query)

    for folder in sorted(by_folder):
        folder_id = f"folder::{folder}"
        tree.insert("", tk.END, iid=folder_id, text=_display_folder(folder), open=auto_open)
        for filename in sorted(by_folder[folder]):
            file_id = f"file::{folder}::{filename}"
            tree.insert(folder_id, tk.END, iid=file_id, text=filename, open=auto_open)
            for name in sorted(by_folder[folder][filename]):
                tree.insert(file_id, tk.END, iid=name, text=name)


def _set_open_recursive(tree: ttk.Treeview, item: str, open_: bool):
    for child in tree.get_children(item):
        tree.item(child, open=open_)
        _set_open_recursive(tree, child, open_)


def _expand_all(tree: ttk.Treeview):
    _set_open_recursive(tree, "", True)


def _collapse_all(tree: ttk.Treeview):
    _set_open_recursive(tree, "", False)


def _collapse_all_except(tree: ttk.Treeview, keep_id: str | None):
    """Collapse every heading except the chain of ancestors leading to
    `keep_id` (which is left open too, if it has children of its own).
    """
    _collapse_all(tree)
    node = keep_id
    while node:
        tree.item(node, open=True)
        node = tree.parent(node)


class _Tooltip:
    """A small hover-only popup showing whatever `text_getter()` returns at
    the moment the pointer enters `widget` - used for override-note tooltips
    on the Weapon Configs tab. Shows nothing when `text_getter()` is empty.
    """

    def __init__(self, widget, text_getter):
        self.widget = widget
        self.text_getter = text_getter
        self.tip_window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        text = self.text_getter()
        if not text or self.tip_window is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tw, text=text, background="#ffffe0", foreground="#000000",
            relief=tk.SOLID, borderwidth=1, padx=4, pady=2,
        ).pack()

    def _hide(self, _event=None):
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


def _autosize_combobox_popdown(combo: ttk.Combobox):
    """Widens `combo`'s dropdown LIST to fit its longest value, without
    changing the combobox's own closed-field width. ttk gives no public API
    for this - the popup listbox defaults to the widget's own width and
    truncates anything longer (a real problem once values are 30+ character
    unit/projectile names) - so this reaches into Tk's internal popdown
    widget directly. Best-effort: silently does nothing if that internal
    path ever changes across Tk versions.
    """
    values = combo.cget("values")
    if not values:
        return
    width = max(len(str(v)) for v in values)
    try:
        popdown = combo.tk.eval(f"ttk::combobox::PopdownWindow {combo}")
        combo.tk.call(f"{popdown}.f.l", "configure", "-width", width)
    except tk.TclError:
        pass


class ProjectileViewerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AGD Projectile Template Viewer")
        self.root.geometry("1100x700")

        self.load_result = LoadResult()
        self.all_names: list[str] = []
        self.current_project: Project | None = None
        self.resolved_project: ResolvedProject | None = None
        self.category_mask_entries: list[CategoryMaskEntry] = []
        self.children_map: dict[str, list[str]] = {}
        self.name_categories: dict[str, str] = {}
        self._current_projectile_name: str | None = None
        self._current_unit_name: str | None = None
        self.unit_load_result = LoadResult()
        self.all_unit_names: list[str] = []
        self.unit_children_map: dict[str, list[str]] = {}
        self._last_unit_file_paths: list[str] = []
        self._last_unit_preferred_files: set[str] = set()
        self.hardpoint_load_result = LoadResult()
        self.all_hardpoint_names: list[str] = []
        self._current_hardpoint_name: str | None = None
        self.behavior_context: dict[str, str] = {}
        self.behavior_description_overrides: dict[str, str] = load_overrides()
        self._active_behavior_edit: dict | None = None

        self.weapon_configs: dict[str, WeaponConfig] = {c.name: c for c in load_weapon_configs()}
        self._weapon_config_field_traces_suspended = False
        self._weapon_config_overridden_fields: set[str] = set()
        self._weapon_config_override_notes: dict[str, str] = {}
        self._weapon_config_accuracy: dict[str, float] = {}
        self._weapon_config_modifiers: dict[str, str] = {}
        self._weapon_config_modifier_context: str = CONTEXT_HARDPOINT
        self._weapon_config_category_restrictions: list[str] = []
        self._weapon_config_field_badges: dict[str, tk.Label] = {}
        self._weapon_config_field_badge_kind: dict[str, str] = {}
        self._weapon_config_field_rows: dict[str, list[tk.Widget]] = {}
        self._category_name_combos: list[ttk.Combobox] = []
        self._current_wc_unit_name: str | None = None
        self._current_unit_slots: list[HardpointGroup] = []
        self._current_slot_index: int | None = None

        self.weapon_rules: dict[str, WeaponRule] = {r.category: r for r in load_weapon_rules()}
        self._current_rule_category: str | None = None

        self.combat_unit_load_result = LoadResult()
        self.all_combat_unit_names: list[str] = []
        self.damage_matrix = DamageMatrix()
        self.shield_recharge_interval_secs = 1.0
        self._battle_sim_ally_loadout: UnitLoadout | None = None
        self._battle_sim_enemy_loadout: UnitLoadout | None = None

        style = ttk.Style(self.root)
        self._register_palette_theme(style, DARK_THEME_NAME, PALETTES["dark"])
        self._register_palette_theme(style, LIGHT_THEME_NAME, PALETTES["light"])
        self.dark_mode_var = tk.BooleanVar(value=app_settings.load_dark_mode())
        self._theme_refresh_callbacks: list = []
        self._current_palette = PALETTES["dark"] if self.dark_mode_var.get() else PALETTES["light"]

        self._build_widgets()
        self._refresh_recent_menu()
        self._apply_theme(self.dark_mode_var.get())

    # -- widget construction -------------------------------------------------

    def _build_widgets(self):
        top_bar = ttk.Frame(self.root, padding=8)
        top_bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(
            top_bar, text=icon_text("project", "Project..."), style="Accent.TButton",
            command=self._on_open_project_dialog,
        ).pack(side=tk.LEFT)

        self.recent_button = ttk.Menubutton(top_bar, text=icon_text("recent", "Recent"))
        self.recent_button.pack(side=tk.LEFT, padx=(4, 0))
        self.recent_menu = tk.Menu(self.recent_button, tearoff=False)
        self.recent_button.config(menu=self.recent_menu)

        self.reload_button = ttk.Button(
            top_bar, text=icon_text("reload", "Reload"), command=self._on_reload, state=tk.DISABLED,
        )
        self.reload_button.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Button(
            top_bar, text=icon_text("load_files", "Load Individual Files..."), command=self._on_load_files,
        ).pack(side=tk.LEFT, padx=(16, 0))

        self.loaded_files_label = ttk.Label(top_bar, text="No project loaded", style="Muted.TLabel")
        self.loaded_files_label.pack(side=tk.LEFT, padx=12)

        self.dark_mode_button = ttk.Button(top_bar, command=self._on_dark_mode_button_clicked)
        self.dark_mode_button.pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        reader_tab = ttk.Frame(self.notebook)
        self.notebook.add(reader_tab, text=icon_text("reader", "Reader"))
        self.reader_tab_widget = reader_tab

        config_tab = ttk.Frame(self.notebook)
        self.notebook.add(config_tab, text=icon_text("config", "Config"))
        self.config_tab_widget = config_tab

        self.reader_notebook = ttk.Notebook(reader_tab)
        self.reader_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        projectiles_tab = ttk.Frame(self.reader_notebook)
        self.reader_notebook.add(projectiles_tab, text=icon_text("projectiles", "Projectiles"))
        self._build_projectiles_tab(projectiles_tab)
        self.projectiles_tab_widget = projectiles_tab

        units_tab = ttk.Frame(self.reader_notebook)
        self.reader_notebook.add(units_tab, text=icon_text("units", "Units"))
        self._build_units_tab(units_tab)

        hardpoints_tab = ttk.Frame(self.reader_notebook)
        self.reader_notebook.add(hardpoints_tab, text=icon_text("hardpoints", "Hardpoints"))
        self._build_hardpoints_tab(hardpoints_tab)
        self.hardpoints_tab_widget = hardpoints_tab

        category_masks_tab = ttk.Frame(self.reader_notebook)
        self.reader_notebook.add(category_masks_tab, text=icon_text("category_masks", "Category Masks"))
        self._build_category_masks_tab(category_masks_tab)

        behaviors_tab = ttk.Frame(self.reader_notebook)
        self.reader_notebook.add(behaviors_tab, text=icon_text("behaviors", "Behaviors"))
        self._build_behaviors_tab(behaviors_tab)

        self.config_notebook = ttk.Notebook(config_tab)
        self.config_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        weapon_rules_tab = ttk.Frame(self.config_notebook)
        self.config_notebook.add(weapon_rules_tab, text=icon_text("weapon_rules", "Weapon Templates"))
        self._build_weapon_rules_tab(weapon_rules_tab)

        weapon_configs_tab = ttk.Frame(self.config_notebook)
        self.config_notebook.add(weapon_configs_tab, text=icon_text("weapon_configs", "Weapon Configs"))
        self._build_weapon_configs_tab(weapon_configs_tab)

        battle_sim_tab = ttk.Frame(self.notebook)
        self.notebook.add(battle_sim_tab, text=icon_text("battle_sim", "Battle Sim"))
        self._build_battle_sim_tab(battle_sim_tab)

        status_bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = ttk.Label(status_bar, text="", style="Warning.TLabel")
        self.status_label.pack(anchor=tk.W)

    # -- dark mode --------------------------------------------------------------

    def _register_palette_theme(self, style: ttk.Style, theme_name: str, palette: dict):
        """Builds one full ttk theme (cloned from 'clam', which - unlike
        Windows' native 'vista' theme - actually honors color overrides)
        from a `palette` dict (see ui_theme.PALETTES), so dark and light
        mode are two instances of the same settings shape fed different
        colors, instead of hand-duplicated style blocks. Also defines the
        named styles used throughout the app (accent buttons, muted/
        warning/danger/link text, the card title, the surface-bordered
        panel wrapper) so both modes support them identically. Registered
        once at startup for both theme names - switching between them at
        runtime is just `style.theme_use(...)`.
        """
        try:
            style.theme_create(theme_name, parent="clam", settings={
                ".": {"configure": {
                    "background": palette["bg"], "foreground": palette["fg"], "fieldbackground": palette["field_bg"],
                }},
                "TFrame": {"configure": {"background": palette["bg"]}},
                "TLabel": {"configure": {"background": palette["bg"], "foreground": palette["fg"]}},
                "TCheckbutton": {"configure": {"background": palette["bg"], "foreground": palette["fg"]}},
                "TButton": {
                    "configure": {"background": palette["button_bg"], "foreground": palette["fg"]},
                    "map": {"background": [("active", palette["select_bg"])]},
                },
                "TMenubutton": {"configure": {"background": palette["button_bg"], "foreground": palette["fg"]}},
                "TEntry": {"configure": {
                    "fieldbackground": palette["field_bg"], "foreground": palette["fg"], "insertcolor": palette["fg"],
                }},
                "TCombobox": {
                    "configure": {
                        "fieldbackground": palette["field_bg"], "foreground": palette["fg"], "background": palette["button_bg"],
                    },
                    "map": {
                        "fieldbackground": [("readonly", palette["field_bg"]), ("disabled", palette["bg"])],
                        "foreground": [("readonly", palette["fg"]), ("disabled", palette["muted_fg"])],
                    },
                },
                "TNotebook": {"configure": {"background": palette["bg"], "borderwidth": 0}},
                "TNotebook.Tab": {
                    "configure": {"background": palette["button_bg"], "foreground": palette["fg"], "padding": (8, 4)},
                    "map": {
                        "background": [("selected", palette["select_bg"])],
                        "foreground": [("selected", "#ffffff")],
                    },
                },
                "Treeview": {
                    "configure": {
                        "background": palette["field_bg"], "foreground": palette["fg"], "fieldbackground": palette["field_bg"],
                    },
                    "map": {
                        "background": [("selected", palette["select_bg"])],
                        "foreground": [("selected", "#ffffff")],
                    },
                },
                "Treeview.Heading": {"configure": {"background": palette["button_bg"], "foreground": palette["fg"]}},
                "TLabelframe": {"configure": {"background": palette["bg"], "foreground": palette["fg"]}},
                "TLabelframe.Label": {"configure": {"background": palette["bg"], "foreground": palette["fg"]}},
                "TPanedwindow": {"configure": {"background": palette["bg"]}},
                "TScrollbar": {"configure": {
                    "background": palette["button_bg"], "troughcolor": palette["bg"], "arrowcolor": palette["fg"],
                }},
                # Named styles shared by both themes, sourced from this palette.
                "Accent.TButton": {
                    "configure": {"background": palette["accent"], "foreground": palette["accent_fg"]},
                    "map": {"background": [("active", palette["accent_active"])]},
                },
                "CardTitle.TLabel": {"configure": {
                    "background": palette["bg"], "foreground": palette["accent"], "font": ("Segoe UI", 10, "bold"),
                }},
                "Muted.TLabel": {"configure": {"background": palette["bg"], "foreground": palette["muted_fg"]}},
                "Warning.TLabel": {"configure": {"background": palette["bg"], "foreground": palette["warning"]}},
                "Danger.TLabel": {"configure": {"background": palette["bg"], "foreground": palette["danger"]}},
                "Link.TLabel": {"configure": {"background": palette["bg"], "foreground": palette["link"]}},
                "SurfaceBorder.TFrame": {"configure": {"background": palette["surface_border"]}},
            })
        except tk.TclError:
            pass  # already registered (re-instantiating ProjectileViewerApp in the same process, e.g. tests)

    def _apply_theme(self, dark: bool):
        palette = PALETTES["dark"] if dark else PALETTES["light"]
        self._current_palette = palette

        style = ttk.Style(self.root)
        style.theme_use(DARK_THEME_NAME if dark else LIGHT_THEME_NAME)
        self.root.configure(bg=palette["bg"])

        self.hardpoint_tree.tag_configure(PROJECTILE_LINK_TAG, foreground=palette["link"])
        self._style_tk_menu(self.recent_menu)
        self._update_dark_mode_button_style()

        for refresh in self._theme_refresh_callbacks:
            refresh()

    def _style_tk_menu(self, menu: tk.Menu):
        """Plain tk.Menu widgets (the Recent-projects menu, right-click
        context menus) aren't ttk and don't follow ttk.Style, so they need
        their colors set directly from the active palette.
        """
        palette = self._current_palette
        menu.configure(
            bg=palette["field_bg"], fg=palette["fg"],
            activebackground=palette["select_bg"], activeforeground="#ffffff",
            disabledforeground=palette["muted_fg"],
        )

    def _update_dark_mode_button_style(self):
        dark = self.dark_mode_var.get()
        self.dark_mode_button.config(
            text=icon_text("light_mode", "Light Mode") if dark else icon_text("dark_mode", "Dark Mode"),
            style="Accent.TButton" if dark else "TButton",
        )

    def _on_dark_mode_button_clicked(self):
        """A plain ttk.Button (unlike the Checkbutton this replaced) has no
        variable of its own to auto-flip before its command runs, so this
        flips `dark_mode_var` explicitly and defers to `_on_toggle_dark_mode`
        for the actual apply+persist - which still assumes (as before) that
        the var already holds the desired new state when it's called.
        """
        self.dark_mode_var.set(not self.dark_mode_var.get())
        self._on_toggle_dark_mode()

    def _on_toggle_dark_mode(self):
        dark = self.dark_mode_var.get()
        self._apply_theme(dark)
        app_settings.save_dark_mode(dark)

    def _make_card(self, parent: ttk.Frame, title: str | None = None, icon_key: str | None = None, place=None) -> ttk.Frame:
        """Returns an inner ttk.Frame to build content into, inset a few
        pixels inside a rounded rectangle drawn on a Canvas (ttk has no
        rounded-corner primitive) with an optional icon+title header.
        Replaces every spot that used to be a plain ttk.LabelFrame
        "pseudo-card". The small inset margin lets the rounded rect's
        surface tint show through as a colored ring around ordinary
        page-background content, rather than trying to recolor every
        nested widget to match a fully-filled card - ttk widgets don't
        inherit a parent's paint color at draw time, only whatever style
        they're individually given, so filling the card would otherwise
        require re-styling every Label/Entry/Button built inside it.
        `place`, if given, is called with the card's outer frame to place
        it (grid/pack/PanedWindow.add) instead of the default
        `pack(fill=X, pady=(0, 8))` - needed for the few cards that live in
        a grid-based parent.
        """
        inset = 4
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, bg=self._current_palette["bg"])
        canvas.pack(fill=tk.X)

        inner = ttk.Frame(canvas, padding=(12 - inset, 8))
        if title:
            header = ttk.Frame(inner)
            header.pack(fill=tk.X, pady=(0, 8))
            ttk.Label(
                header, text=icon_text(icon_key, title) if icon_key else title, style="CardTitle.TLabel",
            ).pack(side=tk.LEFT)
        content = ttk.Frame(inner)
        content.pack(fill=tk.BOTH, expand=True)

        rect_id = draw_rounded_rect(
            canvas, 0, 0, 10, 10, radius=10,
            fill=self._current_palette["surface"], outline=self._current_palette["surface_border"],
        )
        window_id = canvas.create_window(inset, inset, window=inner, anchor=tk.NW)

        def redraw_from_content(_event=None):
            # No update_idletasks() here - this already runs inside a
            # <Configure> callback (Tk has just finished sizing `inner`),
            # and forcing another nested idle-task pass from inside one
            # geometry callback corrupts/truncates the measurements once
            # several cards are cascading resizes at once (confirmed: with
            # it, a scrollable panel holding several cards froze its
            # scrollregion at roughly the visible viewport size instead of
            # the true, much taller content height).
            width = canvas.winfo_width() or (inner.winfo_reqwidth() + 2 * inset)
            height = inner.winfo_reqheight() + 2 * inset
            canvas.configure(height=height)
            canvas.itemconfigure(window_id, width=max(width - 2 * inset, 1))
            update_rounded_rect(canvas, rect_id, 0, 0, width, height, radius=10)

        def on_canvas_configure(event):
            canvas.itemconfigure(window_id, width=max(event.width - 2 * inset, 1))
            update_rounded_rect(canvas, rect_id, 0, 0, event.width, canvas.winfo_height(), radius=10)

        inner.bind("<Configure>", redraw_from_content)
        canvas.bind("<Configure>", on_canvas_configure)

        def refresh_theme():
            palette = self._current_palette
            canvas.configure(bg=palette["bg"])
            canvas.itemconfigure(rect_id, fill=palette["surface"], outline=palette["surface_border"])

        self._theme_refresh_callbacks.append(refresh_theme)

        if place is not None:
            place(outer)
        else:
            outer.pack(fill=tk.X, pady=(0, 8))
        return content

    def _surface_frame(self, parent: ttk.Frame, title: str | None = None, icon_key: str | None = None, padding=8, place=None) -> ttk.Frame:
        """A subtly-bordered panel (a surface-colored outer Frame showing
        through as a 1px border around an ordinary-background inner Frame)
        for the big stretchy list/tree panes that must fill available
        space and can't be content-height-sized like `_make_card`. Gives
        visual grouping without the rounded-rect canvas machinery, which
        isn't needed for panels already framed by their own Treeview
        scrollbar and a PanedWindow sash. `place`, if given, is called with
        the outer border frame to place it instead of the default
        `pack(fill=BOTH, expand=True)`.
        """
        border = ttk.Frame(parent, style="SurfaceBorder.TFrame")
        inner = ttk.Frame(border, padding=padding)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        if title:
            ttk.Label(
                inner, text=icon_text(icon_key, title) if icon_key else title, style="CardTitle.TLabel",
            ).pack(anchor=tk.W, pady=(0, 8))
        if place is not None:
            place(border)
        else:
            border.pack(fill=tk.BOTH, expand=True)
        return inner

    def _make_badge(self, parent: ttk.Frame, text: str) -> tk.Label:
        """A small chip-style status label for override-tracking badges
        ('seeded'/'custom'/'rule: X'). Plain tk.Label, not ttk.Label - only
        a plain tk.Label accepts an arbitrary literal background color per
        instance, and a badge's color is data (which of a few kinds it
        currently is), not a fixed theme role a named ttk style would fit.
        Starts neutral; `_set_badge_kind` recolors it once its real kind is
        known, and again on every theme toggle.
        """
        badge = tk.Label(parent, text=text, cursor="hand2", padx=6, pady=1, font=("Segoe UI", 8))
        self._set_badge_kind(badge, "neutral")
        return badge

    def _set_badge_kind(self, badge: tk.Label, kind: str):
        palette = self._current_palette
        fg, bg = {
            "neutral": (palette["muted_fg"], palette["bg"]),
            "warning": (palette["accent_fg"], palette["warning"]),
            "link": (palette["accent_fg"], palette["link"]),
        }.get(kind, (palette["muted_fg"], palette["bg"]))
        badge.configure(fg=fg, bg=bg)

    def _build_projectiles_tab(self, parent: ttk.Frame):
        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: search + projectile list
        left_frame = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        main_pane.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Category:").pack(anchor=tk.W)
        self.category_filter_var = tk.StringVar(value=CATEGORY_ALL)
        category_combo = ttk.Combobox(
            left_frame, textvariable=self.category_filter_var, state="readonly",
            values=[CATEGORY_ALL, *ALL_CATEGORIES],
        )
        category_combo.pack(fill=tk.X, pady=(0, 8))
        category_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_list())
        _autosize_combobox_popdown(category_combo)

        ttk.Label(left_frame, text="Filter:").pack(anchor=tk.W)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(left_frame, textvariable=self.search_var).pack(fill=tk.X, pady=(0, 4))

        self.group_by_folder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left_frame, text="Group by folder / XML file",
            variable=self.group_by_folder_var, command=self._refresh_list,
        ).pack(anchor=tk.W, pady=(0, 4))

        list_frame = self._surface_frame(left_frame, padding=4)
        self.name_tree = ttk.Treeview(list_frame, show="tree")
        self.name_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.name_tree.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.name_tree.config(yscrollcommand=list_scroll.set)
        self.name_tree.bind("<<TreeviewSelect>>", self._on_select_name)
        self.name_tree.bind("<Button-3>", lambda event: self._show_tree_context_menu(self.name_tree, event))

        # Right: breadcrumb + grouped field tree
        right_frame = ttk.Frame(main_pane, padding=(8, 0, 0, 0))
        main_pane.add(right_frame, weight=3)

        self.breadcrumb_frame = ttk.Frame(right_frame)
        self.breadcrumb_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        self._render_breadcrumb_placeholder()

        variants_row = ttk.Frame(right_frame)
        variants_row.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        ttk.Label(variants_row, text="Variants:").pack(side=tk.LEFT, padx=(0, 6))
        self.variants_var = tk.StringVar(value="(none)")
        self.variants_combo = ttk.Combobox(
            variants_row, textvariable=self.variants_var, state="disabled", width=50,
        )
        self.variants_combo.pack(side=tk.LEFT)
        self.variants_combo.bind("<<ComboboxSelected>>", self._on_variant_selected)

        self.hide_inherited_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            variants_row, text="Only show fields set on this variant",
            variable=self.hide_inherited_var, command=self._on_hide_inherited_toggled,
        ).pack(side=tk.LEFT, padx=(16, 0))

        columns = ("value", "source")
        self.tree = ttk.Treeview(right_frame, columns=columns, show="tree headings")
        self.tree.heading("#0", text="Field")
        self.tree.heading("value", text="Resolved Value")
        self.tree.heading("source", text="Source (set by)")
        self.tree.column("#0", width=280, anchor=tk.W)
        self.tree.column("value", width=320, anchor=tk.W)
        self.tree.column("source", width=220, anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.config(yscrollcommand=tree_scroll.set)

    def _build_units_tab(self, parent: ttk.Frame):
        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: theatre + unit type + search + unit list
        left_frame = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        main_pane.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Theatre:").pack(anchor=tk.W)
        self.theatre_var = tk.StringVar(value=THEATRE_SPACE)
        theatre_combo = ttk.Combobox(
            left_frame, textvariable=self.theatre_var, state="readonly",
            values=[THEATRE_SPACE, THEATRE_LAND],
        )
        theatre_combo.pack(fill=tk.X, pady=(0, 8))
        theatre_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_unit_filter_changed())
        _autosize_combobox_popdown(theatre_combo)

        ttk.Label(left_frame, text="Unit Type:").pack(anchor=tk.W)
        self.unit_kind_var = tk.StringVar(value=UNIT_KIND_UNITS)
        unit_kind_combo = ttk.Combobox(
            left_frame, textvariable=self.unit_kind_var, state="readonly",
            values=[UNIT_KIND_UNITS, UNIT_KIND_TEAMS, UNIT_KIND_COMPANIES],
        )
        unit_kind_combo.pack(fill=tk.X, pady=(0, 8))
        unit_kind_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_unit_filter_changed())
        _autosize_combobox_popdown(unit_kind_combo)

        ttk.Label(left_frame, text="Filter:").pack(anchor=tk.W)
        self.unit_search_var = tk.StringVar()
        self.unit_search_var.trace_add("write", lambda *_: self._refresh_unit_list())
        ttk.Entry(left_frame, textvariable=self.unit_search_var).pack(fill=tk.X, pady=(0, 4))

        self.unit_group_by_folder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left_frame, text="Group by folder / XML file",
            variable=self.unit_group_by_folder_var, command=self._refresh_unit_list,
        ).pack(anchor=tk.W, pady=(0, 4))

        list_frame = self._surface_frame(left_frame, padding=4)
        self.unit_name_tree = ttk.Treeview(list_frame, show="tree")
        self.unit_name_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.unit_name_tree.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.unit_name_tree.config(yscrollcommand=list_scroll.set)
        self.unit_name_tree.bind("<<TreeviewSelect>>", self._on_select_unit_name)
        self.unit_name_tree.bind(
            "<Button-3>", lambda event: self._show_tree_context_menu(self.unit_name_tree, event)
        )

        # Right: breadcrumb + grouped field tree
        right_frame = ttk.Frame(main_pane, padding=(8, 0, 0, 0))
        main_pane.add(right_frame, weight=3)

        self.unit_breadcrumb_frame = ttk.Frame(right_frame)
        self.unit_breadcrumb_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        self._render_unit_breadcrumb_placeholder()

        variants_row = ttk.Frame(right_frame)
        variants_row.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        ttk.Label(variants_row, text="Variants:").pack(side=tk.LEFT, padx=(0, 6))
        self.unit_variants_var = tk.StringVar(value="(none)")
        self.unit_variants_combo = ttk.Combobox(
            variants_row, textvariable=self.unit_variants_var, state="disabled", width=50,
        )
        self.unit_variants_combo.pack(side=tk.LEFT)
        self.unit_variants_combo.bind("<<ComboboxSelected>>", self._on_unit_variant_selected)

        self.unit_hide_inherited_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            variants_row, text="Only show fields set on this variant",
            variable=self.unit_hide_inherited_var, command=self._on_unit_hide_inherited_toggled,
        ).pack(side=tk.LEFT, padx=(16, 0))

        columns = ("value", "source")
        self.unit_tree = ttk.Treeview(right_frame, columns=columns, show="tree headings")
        self.unit_tree.heading("#0", text="Field")
        self.unit_tree.heading("value", text="Resolved Value")
        self.unit_tree.heading("source", text="Source (set by)")
        self.unit_tree.column("#0", width=280, anchor=tk.W)
        self.unit_tree.column("value", width=320, anchor=tk.W)
        self.unit_tree.column("source", width=220, anchor=tk.W)
        self.unit_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        unit_tree_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.unit_tree.yview)
        unit_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.unit_tree.config(yscrollcommand=unit_tree_scroll.set)

    def _build_hardpoints_tab(self, parent: ttk.Frame):
        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: search + hardpoint list
        left_frame = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        main_pane.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Filter:").pack(anchor=tk.W)
        self.hardpoint_search_var = tk.StringVar()
        self.hardpoint_search_var.trace_add("write", lambda *_: self._refresh_hardpoint_list())
        ttk.Entry(left_frame, textvariable=self.hardpoint_search_var).pack(fill=tk.X, pady=(0, 4))

        self.hardpoint_group_by_folder_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left_frame, text="Group by folder / XML file",
            variable=self.hardpoint_group_by_folder_var, command=self._refresh_hardpoint_list,
        ).pack(anchor=tk.W, pady=(0, 4))

        list_frame = self._surface_frame(left_frame, padding=4)
        self.hardpoint_name_tree = ttk.Treeview(list_frame, show="tree")
        self.hardpoint_name_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.hardpoint_name_tree.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.hardpoint_name_tree.config(yscrollcommand=list_scroll.set)
        self.hardpoint_name_tree.bind("<<TreeviewSelect>>", self._on_select_hardpoint_name)
        self.hardpoint_name_tree.bind(
            "<Button-3>", lambda event: self._show_tree_context_menu(self.hardpoint_name_tree, event)
        )

        # Right: grouped field tree - no breadcrumb/variants, HardPoint has no inheritance
        right_frame = ttk.Frame(main_pane, padding=(8, 0, 0, 0))
        main_pane.add(right_frame, weight=3)

        self.hardpoint_title_label = ttk.Label(
            right_frame, text="Select a hardpoint to view its data.",
            font=("Segoe UI", 10, "bold"),
        )
        self.hardpoint_title_label.pack(anchor=tk.W)

        ttk.Label(
            right_frame, text="Double-click a projectile reference (blue) to open it in the Projectiles tab.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))

        columns = ("value",)
        self.hardpoint_tree = ttk.Treeview(right_frame, columns=columns, show="tree headings")
        self.hardpoint_tree.heading("#0", text="Field")
        self.hardpoint_tree.heading("value", text="Value")
        self.hardpoint_tree.column("#0", width=280, anchor=tk.W)
        self.hardpoint_tree.column("value", width=460, anchor=tk.W)
        self.hardpoint_tree.tag_configure(PROJECTILE_LINK_TAG, foreground=self._current_palette["link"])
        self.hardpoint_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hardpoint_tree_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.hardpoint_tree.yview)
        hardpoint_tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.hardpoint_tree.config(yscrollcommand=hardpoint_tree_scroll.set)
        self.hardpoint_tree.bind("<Double-1>", self._on_hardpoint_double_click)

    def _build_category_masks_tab(self, parent: ttk.Frame):
        self.category_masks_source_label = ttk.Label(
            parent, text="No project loaded yet.", style="Muted.TLabel", padding=(0, 8, 0, 8),
        )
        self.category_masks_source_label.pack(anchor=tk.W)

        columns = ("bit", "hex", "description")
        self.category_masks_tree = ttk.Treeview(parent, columns=columns, show="tree headings")
        self.category_masks_tree.heading("#0", text="Tag")
        self.category_masks_tree.heading("bit", text="Bit #")
        self.category_masks_tree.heading("hex", text="Hex Value")
        self.category_masks_tree.heading("description", text="Description")
        self.category_masks_tree.column("#0", width=180, anchor=tk.W)
        self.category_masks_tree.column("bit", width=60, anchor=tk.CENTER)
        self.category_masks_tree.column("hex", width=180, anchor=tk.W)
        self.category_masks_tree.column("description", width=460, anchor=tk.W)
        self.category_masks_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        category_masks_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.category_masks_tree.yview)
        category_masks_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.category_masks_tree.config(yscrollcommand=category_masks_scroll.set)

    def _build_behaviors_tab(self, parent: ttk.Frame):
        self.behaviors_source_label = ttk.Label(
            parent, text="No project loaded yet.", style="Muted.TLabel", padding=(0, 8, 0, 4),
        )
        self.behaviors_source_label.pack(anchor=tk.W)

        filter_row = ttk.Frame(parent)
        filter_row.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
        ttk.Label(filter_row, text="Filter:").pack(side=tk.LEFT, padx=(0, 6))
        self.behaviors_search_var = tk.StringVar()
        self.behaviors_search_var.trace_add("write", lambda *_: self._render_behaviors())
        ttk.Entry(filter_row, textvariable=self.behaviors_search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        columns = ("context", "description")
        self.behaviors_tree = ttk.Treeview(parent, columns=columns, show="tree headings")
        self.behaviors_tree.heading("#0", text="Value")
        self.behaviors_tree.heading("context", text="Context")
        self.behaviors_tree.heading("description", text="Description (double-click to edit)")
        self.behaviors_tree.column("#0", width=260, anchor=tk.W)
        self.behaviors_tree.column("context", width=110, anchor=tk.CENTER)
        self.behaviors_tree.column("description", width=460, anchor=tk.W)
        self.behaviors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        behaviors_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.behaviors_tree.yview)
        behaviors_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.behaviors_tree.config(yscrollcommand=behaviors_scroll.set)
        self.behaviors_tree.bind("<Double-1>", self._on_behaviors_double_click)

    # -- project loading --------------------------------------------------------------

    def _on_open_project_dialog(self):
        ProjectDialog(self.root, on_load=self._on_project_loaded, on_recent_changed=self._refresh_recent_menu)

    def _refresh_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        recents = recent_projects.load_recent()
        if not recents:
            self.recent_menu.add_command(label="(no recent projects)", state=tk.DISABLED)
            return
        for project in recents:
            self.recent_menu.add_command(
                label=f"{project.name} ({len(project.mods)} mod(s))",
                command=lambda p=project: self._on_project_loaded(p),
            )

    def _on_reload(self):
        if self.current_project is not None:
            self._on_project_loaded(self.current_project)

    def _on_project_loaded(self, project: Project):
        resolved = resolve_project(project)
        load_result = load_files(resolved.all_files, PROJECTILE_TAG)
        classified = classify_duplicate_warnings(load_result, resolved)

        self.load_result = load_result
        self.resolved_project = resolved
        self.current_project = project
        self.all_names = sorted(load_result.entries.keys())
        self.children_map, self.name_categories = classify_all(load_result.entries)

        active_layers = sum(1 for layer in resolved.layers if layer.enabled)
        self.loaded_files_label.config(
            text=f"Project: {project.name} - {active_layers} layer(s), {len(resolved.all_files)} file(s), "
                 f"{len(self.all_names)} projectile(s)"
        )
        self.reload_button.config(state=tk.NORMAL)

        self._refresh_list()
        self._update_status(classified)
        self._load_category_masks(resolved.all_files)
        self._load_behaviors(resolved.all_files)
        self._load_units(resolved.all_files, resolved.preferred_files)
        self._load_hardpoints(resolved.all_files, resolved.preferred_files)
        self._load_battle_sim_data(resolved.all_files, resolved.preferred_files)
        self._refresh_wc_unit_combo()

        if resolved.missing_layers:
            messagebox.showwarning(
                "Some layers were not found",
                "These layer paths no longer exist on disk (they were skipped):\n\n"
                + "\n".join(resolved.missing_layers),
            )
        if load_result.parse_errors:
            shown = load_result.parse_errors[:MAX_SHOWN_PARSE_ERRORS]
            message = "\n".join(f"{p}: {e}" for p, e in shown)
            if len(load_result.parse_errors) > MAX_SHOWN_PARSE_ERRORS:
                message += f"\n\n...and {len(load_result.parse_errors) - MAX_SHOWN_PARSE_ERRORS} more."
            messagebox.showerror("Failed to parse some files", message)

        recent_projects.remember(project)
        self._refresh_recent_menu()

    def _update_status(self, classified: list[ClassifiedWarning] | None = None):
        if classified is None:
            # Manual multi-file load has no layer concept to classify against.
            if self.load_result.duplicate_warnings:
                self.status_label.config(
                    text=f"{len(self.load_result.duplicate_warnings)} duplicate name(s) - see console",
                    style="Warning.TLabel",
                )
                for warning in self.load_result.duplicate_warnings:
                    print(f"[warning] {warning}")
            else:
                self.status_label.config(text="")
            return

        conflicts = [c for c in classified if c.severity == "same_layer_conflict"]
        overrides = [c for c in classified if c.severity == "expected_override"]

        if conflicts:
            self.status_label.config(
                text=f"WARNING: {len(conflicts)} conflicting name(s) within the same layer (result depends on "
                     f"file order) - {len(overrides)} expected override(s) from later layers. See console.",
                style="Danger.TLabel",
            )
        elif overrides:
            self.status_label.config(
                text=f"{len(overrides)} name(s) overridden by later layers (expected).",
                style="Muted.TLabel",
            )
        else:
            self.status_label.config(text="")

        for c in conflicts:
            print(f"[conflict] {c.name!r}: {c.from_file!r} vs {c.to_file!r} (same layer)")
        for c in overrides:
            print(f"[override] {c.name!r}: {c.from_file!r} -> {c.to_file!r}")

    # -- manual (advanced) file loading --------------------------------------------------------------

    def _on_load_files(self):
        paths = filedialog.askopenfilenames(
            title="Select Projectile XML file(s)",
            filetypes=[("XML files", "*.xml *.XML"), ("All files", "*.*")],
        )
        if not paths:
            return

        self.load_result = load_files(list(paths), PROJECTILE_TAG)
        self.all_names = sorted(self.load_result.entries.keys())
        self.children_map, self.name_categories = classify_all(self.load_result.entries)
        self.current_project = None
        self.resolved_project = None
        self.reload_button.config(state=tk.DISABLED)

        self.loaded_files_label.config(
            text=f"{len(paths)} file(s) loaded - {len(self.all_names)} projectile(s) found"
        )
        self._refresh_list()
        self._update_status()
        self._load_category_masks(list(paths))
        self._load_behaviors(list(paths))
        self._load_units(list(paths), preferred_files=set())
        self._load_hardpoints(list(paths), preferred_files=set())
        self._load_battle_sim_data(list(paths), preferred_files=set())
        self._refresh_wc_unit_combo()

        if self.load_result.parse_errors:
            errors = "\n".join(f"{p}: {e}" for p, e in self.load_result.parse_errors)
            messagebox.showerror("Failed to parse some files", errors)

    # -- category masks --------------------------------------------------------------

    def _load_category_masks(self, file_paths: list[str]):
        """Find the GameObjectCategoryType enum file among the loaded files.
        If more than one layer defines it, the last one wins - same
        later-overrides-earlier convention as everything else in a Project.
        """
        matches = [p for p in file_paths if is_category_mask_file(p)]
        if not matches:
            self.category_mask_entries = []
            self.category_masks_source_label.config(
                text="No GameObjectCategoryType enum file found among the loaded files.", style="Muted.TLabel",
            )
            self.category_masks_tree.delete(*self.category_masks_tree.get_children())
            self._refresh_category_choices()
            return

        source_path = matches[-1]
        try:
            self.category_mask_entries = parse_category_masks(source_path)
        except OSError as exc:
            self.category_mask_entries = []
            self.category_masks_source_label.config(text=f"Failed to read {source_path}: {exc}", style="Danger.TLabel")
            self.category_masks_tree.delete(*self.category_masks_tree.get_children())
            self._refresh_category_choices()
            return

        self.category_masks_source_label.config(text=f"Loaded from: {source_path}", style="Muted.TLabel")
        self._render_category_masks()
        self._refresh_category_choices()

    def _render_category_masks(self):
        self.category_masks_tree.delete(*self.category_masks_tree.get_children())

        numbered = sorted(
            (e for e in self.category_mask_entries if e.bit_number is not None),
            key=lambda e: e.bit_number,
        )
        for entry in numbered:
            self.category_masks_tree.insert(
                "", tk.END, text=entry.name, values=(entry.bit_number, entry.hex_value, entry.description),
            )

        combos = [e for e in self.category_mask_entries if e.bit_number is None]
        if combos:
            combo_group = self.category_masks_tree.insert(
                "", tk.END, text="Special / Combined Values", open=True, values=("", "", ""),
            )
            for entry in combos:
                self.category_masks_tree.insert(
                    combo_group, tk.END, text=entry.name, values=("-", entry.hex_value, entry.description),
                )

    # -- behaviors --------------------------------------------------------------

    def _load_behaviors(self, file_paths: list[str]):
        combined = scan_files(file_paths)
        self.behavior_context = merge_with_context(combined)
        self.behaviors_source_label.config(
            text=f"Scanned {len(file_paths)} file(s) - {len(self.behavior_context)} distinct value(s) found.",
            style="Muted.TLabel",
        )
        self._render_behaviors()

    def _render_behaviors(self):
        query = self.behaviors_search_var.get().strip().lower()
        self.behaviors_tree.delete(*self.behaviors_tree.get_children())
        for value in sorted(self.behavior_context):
            if query and query not in value.lower():
                continue
            context = self.behavior_context[value]
            description = get_description(value, self.behavior_description_overrides)
            self.behaviors_tree.insert("", tk.END, iid=value, text=value, values=(context, description))

    def _on_behaviors_double_click(self, event):
        if self.behaviors_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.behaviors_tree.identify_column(event.x) != "#2":  # "#1"=context, "#2"=description
            return
        row_id = self.behaviors_tree.identify_row(event.y)
        if row_id:
            self._begin_edit_behavior_description(row_id)

    def _begin_edit_behavior_description(self, value: str):
        bbox = self.behaviors_tree.bbox(value, column="description")
        if not bbox:
            return
        x, y, width, height = bbox
        current = get_description(value, self.behavior_description_overrides)

        edit_var = tk.StringVar(value=current)
        entry = ttk.Entry(self.behaviors_tree, textvariable=edit_var)
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.select_range(0, tk.END)

        self._active_behavior_edit = {"value": value, "entry": entry, "var": edit_var, "original": current}
        entry.bind("<Return>", self._commit_behavior_edit)
        entry.bind("<FocusOut>", self._commit_behavior_edit)
        entry.bind("<Escape>", self._cancel_behavior_edit)

    def _commit_behavior_edit(self, _event=None):
        edit = self._active_behavior_edit
        if edit is None:
            return
        self._active_behavior_edit = None

        value, entry, edit_var, original = edit["value"], edit["entry"], edit["var"], edit["original"]
        new_text = edit_var.get().strip()
        entry.destroy()
        if new_text != original:
            self.behavior_description_overrides[value] = new_text
            save_overrides(self.behavior_description_overrides)
            self.behaviors_tree.set(value, column="description", value=new_text)

    def _cancel_behavior_edit(self, _event=None):
        edit = self._active_behavior_edit
        if edit is None:
            return
        self._active_behavior_edit = None
        edit["entry"].destroy()

    # -- shared name-tree context menu (folder/file grouping headings) ------------------------------

    def _show_tree_context_menu(self, tree: ttk.Treeview, event):
        row_id = tree.identify_row(event.y)
        if row_id:
            tree.selection_set(row_id)

        menu = tk.Menu(tree, tearoff=False)
        self._style_tk_menu(menu)
        menu.add_command(label="Expand All", command=lambda: _expand_all(tree))
        menu.add_command(label="Collapse All", command=lambda: _collapse_all(tree))
        menu.add_command(
            label="Collapse All Except Selected", command=lambda: _collapse_all_except(tree, row_id),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # -- projectile list & resolved view --------------------------------------------------------------

    def _refresh_list(self):
        category = self.category_filter_var.get()
        names = [
            n for n in self.all_names
            if category == CATEGORY_ALL or self.name_categories.get(n) == category
        ]
        render_name_tree(
            self.name_tree, names, self.load_result.entries,
            self.search_var.get(), self.group_by_folder_var.get(),
        )

    def _on_select_name(self, _event):
        selection = self.name_tree.selection()
        if not selection:
            return
        name = selection[0]
        if name not in self.load_result.entries:
            return  # a folder/file heading was clicked, not an actual entry
        self._display_resolved(name)

    def _select_and_display(self, name: str):
        """Jump to `name` from a breadcrumb click or the variants dropdown:
        make it visible in the (unfiltered) list, select it there, then
        display its resolved data.
        """
        self.search_var.set("")
        self.category_filter_var.set(CATEGORY_ALL)
        self._refresh_list()

        if self.name_tree.exists(name):
            self.name_tree.selection_set(name)
            self.name_tree.see(name)

        self._display_resolved(name)

    def _clear_breadcrumb(self):
        for child in self.breadcrumb_frame.winfo_children():
            child.destroy()

    def _render_breadcrumb_placeholder(self):
        self._clear_breadcrumb()
        ttk.Label(
            self.breadcrumb_frame, text="Select a projectile to view its resolved data.",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)

    def _render_breadcrumb(self, chain: list[str]):
        self._clear_breadcrumb()
        for index, link_name in enumerate(chain):
            if index > 0:
                ttk.Label(self.breadcrumb_frame, text=" -> ", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

            is_current = index == len(chain) - 1
            label_kwargs = {"font": ("Segoe UI", 10, "bold"), "cursor": "arrow"}
            if not is_current:
                label_kwargs["foreground"] = "#1a5fb4"
                label_kwargs["cursor"] = "hand2"

            label = ttk.Label(self.breadcrumb_frame, text=link_name, **label_kwargs)
            label.pack(side=tk.LEFT)
            if not is_current:
                label.bind("<Button-1>", lambda _event, n=link_name: self._select_and_display(n))

    def _on_variant_selected(self, _event):
        self._select_and_display(self.variants_var.get())

    def _update_variants_dropdown(self, name: str):
        children = sorted(self.children_map.get(name, []))
        if children:
            self.variants_combo.config(values=children, state="readonly")
            self.variants_var.set(f"{len(children)} variant(s) - select one")
        else:
            self.variants_combo.config(values=[], state="disabled")
            self.variants_var.set("(none)")
        _autosize_combobox_popdown(self.variants_combo)

    def _on_hide_inherited_toggled(self):
        if self._current_projectile_name is not None:
            self._display_resolved(self._current_projectile_name)

    def _display_resolved(self, name: str):
        try:
            chain = resolve_chain(self.load_result.entries, name)
        except InheritanceCycleError as exc:
            messagebox.showerror("Inheritance cycle", str(exc))
            return

        self._current_projectile_name = name
        resolved = merge_chain(self.load_result.entries, chain)
        if self.hide_inherited_var.get():
            resolved = {k: v for k, v in resolved.items() if v.source_name == name}

        self._render_breadcrumb(chain)
        self._update_variants_dropdown(name)

        self.tree.delete(*self.tree.get_children())
        grouped = field_groups.group_fields(resolved.keys())
        for group_name, field_names in grouped:
            group_id = self.tree.insert("", tk.END, text=group_name, open=True, values=("", ""))
            for field_name in field_names:
                resolved_field = resolved[field_name]
                display_value = resolved_field.value if resolved_field.value else "(empty)"
                self.tree.insert(
                    group_id, tk.END, text=field_name,
                    values=(display_value, resolved_field.source_name),
                )

    # -- unit list & resolved view --------------------------------------------------------------

    def _load_units(self, file_paths: list[str], preferred_files: set[str] | None = None):
        self._last_unit_file_paths = file_paths
        if preferred_files is not None:
            self._last_unit_preferred_files = preferred_files
        tags = THEATRE_UNIT_TAGS[(self.theatre_var.get(), self.unit_kind_var.get())]
        self.unit_load_result = load_files(file_paths, tags, preferred_files=self._last_unit_preferred_files)
        self.all_unit_names = sorted(self.unit_load_result.entries.keys())
        self.unit_children_map = build_children_map(self.unit_load_result.entries)
        self._refresh_unit_list()

    def _on_unit_filter_changed(self):
        # Changing Theatre or Unit Type invalidates whatever was on display
        # (that name likely doesn't exist in the new tag set's namespace),
        # unlike a normal reload of the same filters where leaving the last
        # view up is fine.
        self._current_unit_name = None
        self._load_units(self._last_unit_file_paths)
        self._render_unit_breadcrumb_placeholder()
        self.unit_tree.delete(*self.unit_tree.get_children())
        self.unit_variants_combo.config(values=[], state="disabled")
        self.unit_variants_var.set("(none)")

    def _refresh_unit_list(self):
        render_name_tree(
            self.unit_name_tree, self.all_unit_names, self.unit_load_result.entries,
            self.unit_search_var.get(), self.unit_group_by_folder_var.get(),
        )

    def _on_select_unit_name(self, _event):
        selection = self.unit_name_tree.selection()
        if not selection:
            return
        name = selection[0]
        if name not in self.unit_load_result.entries:
            return  # a folder/file heading was clicked, not an actual entry
        self._display_resolved_unit(name)

    def _select_and_display_unit(self, name: str):
        self.unit_search_var.set("")
        self._refresh_unit_list()

        if self.unit_name_tree.exists(name):
            self.unit_name_tree.selection_set(name)
            self.unit_name_tree.see(name)

        self._display_resolved_unit(name)

    def _clear_unit_breadcrumb(self):
        for child in self.unit_breadcrumb_frame.winfo_children():
            child.destroy()

    def _render_unit_breadcrumb_placeholder(self):
        self._clear_unit_breadcrumb()
        ttk.Label(
            self.unit_breadcrumb_frame, text="Select a unit to view its resolved data.",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT)

    def _render_unit_breadcrumb(self, chain: list[str]):
        self._clear_unit_breadcrumb()
        for index, link_name in enumerate(chain):
            if index > 0:
                ttk.Label(self.unit_breadcrumb_frame, text=" -> ", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

            is_current = index == len(chain) - 1
            label_kwargs = {"font": ("Segoe UI", 10, "bold"), "cursor": "arrow"}
            if not is_current:
                label_kwargs["foreground"] = "#1a5fb4"
                label_kwargs["cursor"] = "hand2"

            label = ttk.Label(self.unit_breadcrumb_frame, text=link_name, **label_kwargs)
            label.pack(side=tk.LEFT)
            if not is_current:
                label.bind("<Button-1>", lambda _event, n=link_name: self._select_and_display_unit(n))

    def _on_unit_variant_selected(self, _event):
        self._select_and_display_unit(self.unit_variants_var.get())

    def _update_unit_variants_dropdown(self, name: str):
        children = sorted(self.unit_children_map.get(name, []))
        if children:
            self.unit_variants_combo.config(values=children, state="readonly")
            self.unit_variants_var.set(f"{len(children)} variant(s) - select one")
        else:
            self.unit_variants_combo.config(values=[], state="disabled")
            self.unit_variants_var.set("(none)")
        _autosize_combobox_popdown(self.unit_variants_combo)

    def _on_unit_hide_inherited_toggled(self):
        if self._current_unit_name is not None:
            self._display_resolved_unit(self._current_unit_name)

    def _display_resolved_unit(self, name: str):
        try:
            chain = resolve_chain(self.unit_load_result.entries, name)
        except InheritanceCycleError as exc:
            messagebox.showerror("Inheritance cycle", str(exc))
            return

        self._current_unit_name = name
        resolved = merge_chain(self.unit_load_result.entries, chain)
        if self.unit_hide_inherited_var.get():
            resolved = {k: v for k, v in resolved.items() if v.source_name == name}

        self._render_unit_breadcrumb(chain)
        self._update_unit_variants_dropdown(name)

        self.unit_tree.delete(*self.unit_tree.get_children())
        flat_fields = {k: v for k, v in resolved.items() if k != UNIT_ABILITIES_TAG}
        grouped = unit_field_groups.group_fields(flat_fields.keys())
        for group_name, field_names in grouped:
            group_id = self.unit_tree.insert("", tk.END, text=group_name, open=True, values=("", ""))
            for field_name in field_names:
                resolved_field = flat_fields[field_name]
                display_value = resolved_field.value if resolved_field.value else "(empty)"
                self.unit_tree.insert(
                    group_id, tk.END, text=field_name,
                    values=(display_value, resolved_field.source_name),
                )

        self._render_unit_abilities(name)

    def _render_unit_abilities(self, name: str):
        """Shows Unit_Abilities_Data for the currently-VIEWED entry only, as
        directly authored - not resolved/merged across the inheritance chain,
        since the SubObjectList="Yes" attribute suggests the game may append
        ability lists across variants rather than replace them, and that
        semantic isn't confirmed. Mislabeling a merge here would be worse
        than just showing what this one entry actually declares.
        """
        entry = self.unit_load_result.entries.get(name)
        if entry is None:
            return
        abilities_el = entry.element.find(UNIT_ABILITIES_TAG)
        if abilities_el is None:
            return
        abilities = list(abilities_el.findall(UNIT_ABILITY_TAG))
        if not abilities:
            return

        group_id = self.unit_tree.insert(
            "", tk.END, text=f"Abilities defined directly on this unit ({len(abilities)})",
            open=True, values=("", ""),
        )
        for index, ability_el in enumerate(abilities, start=1):
            type_el = ability_el.find("Type")
            label = type_el.text.strip() if type_el is not None and type_el.text else f"Ability {index}"
            ability_id = self.unit_tree.insert(group_id, tk.END, text=label, open=False, values=("", ""))
            for child in ability_el:
                value = (child.text or "").strip()
                self.unit_tree.insert(
                    ability_id, tk.END, text=child.tag, values=(value if value else "(empty)", ""),
                )

    # -- hardpoint list & display --------------------------------------------------------------

    def _load_hardpoints(self, file_paths: list[str], preferred_files: set[str] | None = None):
        self.hardpoint_load_result = load_files(file_paths, HARDPOINT_TAG, preferred_files=preferred_files or set())
        self.all_hardpoint_names = sorted(self.hardpoint_load_result.entries.keys())
        self._refresh_hardpoint_list()

    def _refresh_hardpoint_list(self):
        render_name_tree(
            self.hardpoint_name_tree, self.all_hardpoint_names, self.hardpoint_load_result.entries,
            self.hardpoint_search_var.get(), self.hardpoint_group_by_folder_var.get(),
        )

    def _on_select_hardpoint_name(self, _event):
        selection = self.hardpoint_name_tree.selection()
        if not selection:
            return
        name = selection[0]
        if name not in self.hardpoint_load_result.entries:
            return  # a folder/file heading was clicked, not an actual entry
        self._display_hardpoint(name)

    def _select_and_display_hardpoint(self, name: str):
        self.hardpoint_search_var.set("")
        self._refresh_hardpoint_list()

        if self.hardpoint_name_tree.exists(name):
            self.hardpoint_name_tree.selection_set(name)
            self.hardpoint_name_tree.see(name)

        self._display_hardpoint(name)

    def _display_hardpoint(self, name: str):
        entry = self.hardpoint_load_result.entries.get(name)
        if entry is None:
            return
        self._current_hardpoint_name = name
        self.hardpoint_title_label.config(text=name)

        fields = extract_fields(entry.element)
        self.hardpoint_tree.delete(*self.hardpoint_tree.get_children())
        grouped = hardpoint_field_groups.group_fields(fields.keys())
        for group_name, field_names in grouped:
            group_id = self.hardpoint_tree.insert("", tk.END, text=group_name, open=True, values=("",))
            for field_name in field_names:
                is_link_field = field_name in PROJECTILE_REFERENCE_TAGS
                for value in fields[field_name]:
                    display_value = value if value else "(empty)"
                    tags = (PROJECTILE_LINK_TAG,) if is_link_field and value else ()
                    self.hardpoint_tree.insert(
                        group_id, tk.END, text=field_name, values=(display_value,), tags=tags,
                    )

    def _on_hardpoint_double_click(self, event):
        row_id = self.hardpoint_tree.identify_row(event.y)
        if not row_id:
            return
        if PROJECTILE_LINK_TAG not in self.hardpoint_tree.item(row_id, "tags"):
            return
        values = self.hardpoint_tree.item(row_id, "values")
        if not values:
            return
        self._open_projectile_from_hardpoint(values[0].strip())

    def _open_projectile_from_hardpoint(self, projectile_name: str):
        if projectile_name not in self.load_result.entries:
            messagebox.showinfo(
                "Projectile not loaded",
                f"{projectile_name!r} isn't among the currently loaded projectiles "
                "(its file may not be part of this project).",
            )
            return
        self.notebook.select(self.reader_tab_widget)
        self.reader_notebook.select(self.projectiles_tab_widget)
        self._select_and_display(projectile_name)

    # -- weapon rules (Config tab) --------------------------------------------------------------

    def _make_scrollable(self, parent: ttk.Frame) -> ttk.Frame:
        """Builds a vertically-scrolling Canvas+Scrollbar inside `parent` and
        returns a fresh inner ttk.Frame to pack/grid content into exactly as
        if it were `parent` itself. The inner frame's width is pinned to the
        canvas's own visible width on <Configure>, so only vertical scrolling
        ever happens - long content never grows a horizontal scrollbar.
        Mouse-wheel scrolling is bound only while the pointer is over this
        canvas (via <Enter>/<Leave>), not bind_all, so it doesn't compete with
        Treeviews elsewhere in the app that scroll via their own scrollbar.
        """
        canvas = tk.Canvas(parent, highlightthickness=0, borderwidth=0, bg=self._current_palette["bg"])
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        inner = ttk.Frame(canvas)
        inner_window = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        def on_inner_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfigure(inner_window, width=event.width)

        inner.bind("<Configure>", on_inner_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        self._theme_refresh_callbacks.append(lambda: canvas.configure(bg=self._current_palette["bg"]))

        def on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        def bind_wheel(_event=None):
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_wheel(_event=None):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)

        return inner

    def _build_weapon_rules_tab(self, parent: ttk.Frame):
        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        main_pane.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Weapon Categories:").pack(anchor=tk.W)
        list_frame = self._surface_frame(left_frame, padding=4, place=lambda w: w.pack(fill=tk.BOTH, expand=True, pady=(4, 0)))
        self.weapon_rule_tree = ttk.Treeview(list_frame, show="tree")
        self.weapon_rule_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.weapon_rule_tree.yview)
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.weapon_rule_tree.config(yscrollcommand=list_scroll.set)
        self.weapon_rule_tree.bind("<<TreeviewSelect>>", self._on_select_weapon_rule)

        button_row = ttk.Frame(left_frame)
        button_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(button_row, text=icon_text("new", "New"), command=self._on_new_weapon_rule).pack(side=tk.LEFT)
        ttk.Button(
            button_row, text=icon_text("delete", "Delete"), command=self._on_delete_weapon_rule,
        ).pack(side=tk.LEFT, padx=(4, 0))

        right_frame = self._surface_frame(
            main_pane, title="Template defaults", icon_key="weapon_rules",
            place=lambda w: main_pane.add(w, weight=2),
        )
        right_scroll = self._make_scrollable(right_frame)
        # Column 2 is never occupied by the plain Category/rate-of-fire
        # rows below (they only use columns 0-1) - giving it the weight
        # lets it silently absorb all leftover width once right_scroll is
        # forced wide by _make_scrollable, so the columnspan=3 cards
        # further down stretch to the panel's full width instead of being
        # squeezed to the label+entry rows' bare natural width.
        right_scroll.columnconfigure(2, weight=1)

        ttk.Label(right_scroll, text="Category:").grid(row=0, column=0, sticky=tk.W)
        self.weapon_rule_category_var = tk.StringVar()
        ttk.Entry(right_scroll, textvariable=self.weapon_rule_category_var, width=35).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 0)
        )

        rule_field_labels = [
            ("Min Recharge (s):", "weapon_rule_min_recharge_var"),
            ("Max Recharge (s):", "weapon_rule_max_recharge_var"),
            ("Pulse Count:", "weapon_rule_pulse_count_var"),
            ("Pulse Delay (s):", "weapon_rule_pulse_delay_var"),
            ("Fire SFX Event:", "weapon_rule_sfx_event_var"),
        ]
        row = 1
        for label, attr in rule_field_labels:
            ttk.Label(right_scroll, text=label).grid(row=row, column=0, sticky=tk.W, pady=(6, 0))
            var = tk.StringVar()
            setattr(self, attr, var)
            ttk.Entry(right_scroll, textvariable=var, width=25).grid(
                row=row, column=1, sticky=tk.W, padx=(6, 0), pady=(6, 0)
            )
            row += 1

        ttk.Button(
            right_scroll, text=icon_text("save", "Save Template"), style="Accent.TButton", command=self._on_save_weapon_rule,
        ).grid(row=row, column=0, sticky=tk.W, pady=(10, 0))
        row += 1

        accuracy_frame = self._make_card(
            right_scroll, title="Accuracy by Category",
            place=lambda w: w.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0)),
        )
        self._weapon_rule_accuracy: dict[str, float] = {}
        self._refresh_weapon_rule_accuracy_tree = self._build_accuracy_table(
            accuracy_frame,
            tree_attr="weapon_rule_accuracy_tree",
            category_var_attr="weapon_rule_accuracy_category_var",
            category_combo_attr="weapon_rule_accuracy_category_combo",
            value_var_attr="weapon_rule_accuracy_value_var",
            get_dict=lambda: self._weapon_rule_accuracy,
            on_change=lambda: None,
        )
        row += 1

        modifiers_frame = self._make_card(
            right_scroll, title="Modifiers",
            place=lambda w: w.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0)),
        )
        self._weapon_rule_modifiers: dict[str, str] = {}
        self._refresh_weapon_rule_modifiers_tree, _ = self._build_modifiers_table(
            modifiers_frame,
            tree_attr="weapon_rule_modifiers_tree",
            get_dict=lambda: self._weapon_rule_modifiers,
            on_change=lambda: None,
            get_specs=lambda: list(MODIFIER_CATALOG),
        )
        row += 1

        category_restrictions_frame = self._make_card(
            right_scroll, title="Category Restrictions",
            place=lambda w: w.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0)),
        )
        self._weapon_rule_category_restrictions: list[str] = []
        self._refresh_weapon_rule_category_restrictions_tree = self._build_category_list_table(
            category_restrictions_frame,
            combo_attr="weapon_rule_category_restriction_var",
            tree_attr="weapon_rule_category_restrictions_tree",
            get_list=lambda: self._weapon_rule_category_restrictions,
            on_change=lambda: None,
        )

        self._refresh_weapon_rules_list()
        self._show_weapon_rule_placeholder()

    def _build_accuracy_table(
        self, parent: ttk.Frame, tree_attr: str, category_var_attr: str, category_combo_attr: str,
        value_var_attr: str, get_dict, on_change,
    ):
        """Builds a Category/Value table + add-row controls inside `parent`,
        backed by whatever dict `get_dict()` currently returns - shared by
        the Weapon Configs tab (backed by the selected slot's
        accuracy_by_category, with override tracking via `on_change`) and
        the Weapon Rules tab (backed by the rule's own dict directly, no
        override tracking needed - a rule has no "base" to diverge from).
        The category combobox is readonly - values come from the real
        GameObjectCategoryType enum (self.category_mask_entries), refreshed
        by _refresh_category_choices whenever a project loads.
        """
        tree = ttk.Treeview(parent, columns=("value",), show="tree headings", height=4)
        tree.heading("#0", text="Category")
        tree.heading("value", text="Value")
        tree.column("#0", width=150, anchor=tk.W)
        tree.column("value", width=100, anchor=tk.E)
        tree.pack(fill=tk.X)
        setattr(self, tree_attr, tree)

        add_row = ttk.Frame(parent)
        add_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(add_row, text="Category:").pack(side=tk.LEFT)
        category_var = tk.StringVar()
        category_combo = ttk.Combobox(add_row, textvariable=category_var, state="readonly", width=20)
        category_combo.pack(side=tk.LEFT, padx=(4, 10))
        setattr(self, category_var_attr, category_var)
        setattr(self, category_combo_attr, category_combo)
        self._category_name_combos.append(category_combo)

        ttk.Label(add_row, text="Value:").pack(side=tk.LEFT)
        value_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=value_var, width=10).pack(side=tk.LEFT, padx=(4, 10))
        setattr(self, value_var_attr, value_var)

        def refresh():
            tree.delete(*tree.get_children())
            for category, value in sorted(get_dict().items()):
                tree.insert("", tk.END, iid=category, text=category, values=(value,))

        def on_add():
            category = category_var.get().strip()
            if not category:
                messagebox.showinfo("Category required", "Select a category from the dropdown first.")
                return
            get_dict()[category] = weapon_config_to_float(value_var.get())
            refresh()
            on_change()

        def on_remove():
            selection = tree.selection()
            if not selection:
                return
            for category in selection:
                get_dict().pop(category, None)
            refresh()
            on_change()

        ttk.Button(add_row, text=icon_text("add", "Add / Update"), command=on_add).pack(side=tk.LEFT)
        ttk.Button(
            add_row, text=icon_text("remove", "Remove Selected"), command=on_remove,
        ).pack(side=tk.LEFT, padx=(4, 0))

        refresh()
        return refresh

    def _build_category_list_table(self, parent: ttk.Frame, combo_attr: str, tree_attr: str, get_list, on_change):
        """Builds a plain Category list (no value) + add-row controls -
        Fire_Category_Restrictions is a single tag holding a bare
        comma-separated list of category names, unlike accuracy's
        "Category, value" pairs, so this is a simpler one-column sibling to
        _build_accuracy_table sharing the same category dropdown source.
        """
        tree = ttk.Treeview(parent, show="tree", height=4)
        tree.pack(fill=tk.X)
        setattr(self, tree_attr, tree)

        add_row = ttk.Frame(parent)
        add_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(add_row, text="Category:").pack(side=tk.LEFT)
        combo_var = tk.StringVar()
        combo = ttk.Combobox(add_row, textvariable=combo_var, state="readonly", width=20)
        combo.pack(side=tk.LEFT, padx=(4, 10))
        setattr(self, combo_attr, combo_var)
        self._category_name_combos.append(combo)

        def refresh():
            tree.delete(*tree.get_children())
            for category in get_list():
                tree.insert("", tk.END, iid=category, text=category)

        def on_add():
            category = combo_var.get().strip()
            if not category:
                messagebox.showinfo("Category required", "Select a category from the dropdown first.")
                return
            values = get_list()
            if category not in values:
                values.append(category)
            refresh()
            on_change()

        def on_remove():
            selection = tree.selection()
            if not selection:
                return
            values = get_list()
            for category in selection:
                if category in values:
                    values.remove(category)
            refresh()
            on_change()

        ttk.Button(add_row, text=icon_text("add", "Add"), command=on_add).pack(side=tk.LEFT)
        ttk.Button(
            add_row, text=icon_text("remove", "Remove Selected"), command=on_remove,
        ).pack(side=tk.LEFT, padx=(4, 0))

        refresh()
        return refresh

    def _refresh_category_choices(self):
        """Repopulates every category-name dropdown (accuracy, category
        restrictions) from the real GameObjectCategoryType enum, parsed
        per-project into self.category_mask_entries (Category Masks tab).
        """
        names = sorted(e.name for e in self.category_mask_entries)
        for combo in self._category_name_combos:
            combo.config(values=names)
            _autosize_combobox_popdown(combo)

    def _refresh_weapon_rules_list(self):
        self.weapon_rule_tree.delete(*self.weapon_rule_tree.get_children())
        for category in sorted(self.weapon_rules):
            self.weapon_rule_tree.insert("", tk.END, iid=category, text=category)

        # Keep the Weapon Configs tab's Category picker in sync too.
        if hasattr(self, "weapon_config_category_combo"):
            self._filter_search_combo(
                self.weapon_config_category_combo, sorted(self.weapon_rules), self.weapon_config_category_var,
            )

    def _on_select_weapon_rule(self, _event):
        selection = self.weapon_rule_tree.selection()
        if not selection:
            return
        self._display_weapon_rule(selection[0])

    def _show_weapon_rule_placeholder(self):
        self._current_rule_category = None
        self._set_weapon_rule_field_vars(WeaponRule(category=""))

    def _set_weapon_rule_field_vars(self, rule: WeaponRule):
        self.weapon_rule_category_var.set(rule.category)
        self._weapon_rule_accuracy = dict(rule.accuracy_by_category)
        self._refresh_weapon_rule_accuracy_tree()
        self.weapon_rule_min_recharge_var.set(str(rule.fire_min_recharge))
        self.weapon_rule_max_recharge_var.set(str(rule.fire_max_recharge))
        self.weapon_rule_pulse_count_var.set(str(rule.fire_pulse_count))
        self.weapon_rule_pulse_delay_var.set(str(rule.fire_pulse_delay))
        self.weapon_rule_sfx_event_var.set(rule.sfx_event)
        self._weapon_rule_modifiers = dict(rule.modifiers)
        self._refresh_weapon_rule_modifiers_tree()
        self._weapon_rule_category_restrictions = list(rule.category_restrictions)
        self._refresh_weapon_rule_category_restrictions_tree()

    def _display_weapon_rule(self, category: str):
        rule = self.weapon_rules.get(category)
        if rule is None:
            return
        self._current_rule_category = category
        self._set_weapon_rule_field_vars(rule)

    def _read_weapon_rule_from_fields(self) -> WeaponRule:
        return WeaponRule(
            category=self.weapon_rule_category_var.get().strip(),
            accuracy_by_category=dict(self._weapon_rule_accuracy),
            fire_min_recharge=weapon_config_to_float(self.weapon_rule_min_recharge_var.get()),
            fire_max_recharge=weapon_config_to_float(self.weapon_rule_max_recharge_var.get()),
            fire_pulse_count=weapon_config_to_int(self.weapon_rule_pulse_count_var.get()),
            fire_pulse_delay=weapon_config_to_float(self.weapon_rule_pulse_delay_var.get()),
            sfx_event=self.weapon_rule_sfx_event_var.get().strip(),
            modifiers=dict(self._weapon_rule_modifiers),
            category_restrictions=list(self._weapon_rule_category_restrictions),
        )

    def _on_new_weapon_rule(self):
        self.weapon_rule_tree.selection_remove(*self.weapon_rule_tree.selection())
        self._show_weapon_rule_placeholder()

    def _on_save_weapon_rule(self):
        rule = self._read_weapon_rule_from_fields()
        if not rule.category:
            messagebox.showwarning("Category required", "Give this rule a category name before saving.")
            return

        previous_category = self._current_rule_category
        if previous_category is not None and previous_category != rule.category:
            del self.weapon_rules[previous_category]

        self.weapon_rules[rule.category] = rule
        save_weapon_rules(list(self.weapon_rules.values()))
        self._current_rule_category = rule.category

        self._refresh_weapon_rules_list()
        self.weapon_rule_tree.selection_set(rule.category)
        self.weapon_rule_tree.see(rule.category)

    def _on_delete_weapon_rule(self):
        category = self._current_rule_category
        if category is None or category not in self.weapon_rules:
            return
        if not messagebox.askyesno("Delete Weapon Template", f"Delete the saved template for {category!r}?"):
            return
        del self.weapon_rules[category]
        save_weapon_rules(list(self.weapon_rules.values()))
        self._refresh_weapon_rules_list()
        self._show_weapon_rule_placeholder()

    # -- weapon configs (Config tab) --------------------------------------------------------------

    def _build_weapon_configs_tab(self, parent: ttk.Frame):
        picker_row = ttk.Frame(parent, padding=8)
        picker_row.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(picker_row, text="Theatre:").grid(row=0, column=0, sticky=tk.W)
        self.wc_theatre_var = tk.StringVar(value=THEATRE_SPACE)
        theatre_combo = ttk.Combobox(
            picker_row, textvariable=self.wc_theatre_var, state="readonly",
            values=[THEATRE_SPACE, THEATRE_LAND], width=10,
        )
        theatre_combo.grid(row=0, column=1, sticky=tk.W, padx=(6, 20))
        theatre_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_wc_theatre_changed())
        _autosize_combobox_popdown(theatre_combo)

        ttk.Label(picker_row, text="Unit:").grid(row=0, column=2, sticky=tk.W)
        self.wc_unit_var = tk.StringVar()
        self.wc_unit_combo = ttk.Combobox(picker_row, textvariable=self.wc_unit_var, width=40)
        self.wc_unit_combo.grid(row=0, column=3, sticky=tk.W, padx=(6, 6))
        self.wc_unit_var.trace_add(
            "write", lambda *_: self._filter_search_combo(
                self.wc_unit_combo, self._wc_unit_names_for_theatre(), self.wc_unit_var,
            )
        )
        self.wc_unit_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_wc_unit_selected())
        self.wc_unit_combo.bind("<Return>", lambda _e: self._on_wc_unit_selected())

        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Left: every weapon/hardpoint slot the selected unit has
        left_frame = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        main_pane.add(left_frame, weight=1)

        ttk.Label(left_frame, text=icon_text("weapon_configs", "Weapons / Hardpoints:"), style="CardTitle.TLabel").pack(anchor=tk.W)
        slot_columns = ("count", "type", "rule")
        self.weapon_config_slot_tree = ttk.Treeview(left_frame, columns=slot_columns, show="tree headings")
        self.weapon_config_slot_tree.heading("#0", text="Slot")
        self.weapon_config_slot_tree.heading("count", text="Count")
        self.weapon_config_slot_tree.heading("type", text="Type")
        self.weapon_config_slot_tree.heading("rule", text="Rule")
        self.weapon_config_slot_tree.column("#0", width=170, anchor=tk.W)
        self.weapon_config_slot_tree.column("count", width=45, anchor=tk.CENTER)
        self.weapon_config_slot_tree.column("type", width=90, anchor=tk.W)
        self.weapon_config_slot_tree.column("rule", width=110, anchor=tk.W)
        self.weapon_config_slot_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(4, 0))
        self.weapon_config_slot_tree.bind("<<TreeviewSelect>>", self._on_select_slot)

        button_row = ttk.Frame(left_frame)
        button_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            button_row, text=icon_text("save", "Save All Slots"), style="Accent.TButton", command=self._on_save_all_slots,
        ).pack(side=tk.LEFT)
        ttk.Button(button_row, text=icon_text("export", "Export Unit XML..."), command=self._on_export_unit_xml).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        # Right: source info, rule/override editor, live analysis
        right_frame = ttk.Frame(main_pane, padding=(8, 0, 0, 0))
        main_pane.add(right_frame, weight=3)
        right_scroll = self._make_scrollable(right_frame)

        source_frame = self._make_card(right_scroll, title="Slot source")

        ttk.Label(source_frame, text="Source Projectile:").grid(row=0, column=0, sticky=tk.W)
        self.weapon_config_source_projectile_label = ttk.Label(source_frame, text="(none)")
        self.weapon_config_source_projectile_label.grid(row=0, column=1, sticky=tk.W, padx=(6, 6))
        ttk.Button(source_frame, text=icon_text("view", "View"), command=self._on_view_source_projectile).grid(row=0, column=2)

        ttk.Label(source_frame, text="Source Hardpoint:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.weapon_config_source_hardpoint_label = ttk.Label(source_frame, text="(none)")
        self.weapon_config_source_hardpoint_label.grid(row=1, column=1, sticky=tk.W, padx=(6, 6), pady=(6, 0))
        ttk.Button(
            source_frame, text=icon_text("view", "View"), command=self._on_view_source_hardpoint,
        ).grid(row=1, column=2, pady=(6, 0))

        ttk.Label(source_frame, text="Category (template):").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        self.weapon_config_category_var = tk.StringVar()
        self.weapon_config_category_combo = ttk.Combobox(
            source_frame, textvariable=self.weapon_config_category_var, width=30,
        )
        self.weapon_config_category_combo.grid(row=2, column=1, sticky=tk.W, padx=(6, 6), pady=(6, 0))
        self.weapon_config_category_var.trace_add(
            "write", lambda *_: self._filter_search_combo(
                self.weapon_config_category_combo, sorted(self.weapon_rules), self.weapon_config_category_var,
            )
        )
        ttk.Button(
            source_frame, text=icon_text("apply", "Apply Template"), command=self._on_apply_weapon_rule,
        ).grid(row=2, column=2, pady=(6, 0))
        ttk.Button(
            source_frame, text=icon_text("new", "Create Template from Slot"), command=self._on_create_rule_from_slot,
        ).grid(row=2, column=3, padx=(8, 0), pady=(6, 0))

        fields_frame = self._make_card(right_scroll, title="Basic weapon settings")

        ttk.Label(fields_frame, text="Name:").grid(row=0, column=0, sticky=tk.W)
        self.weapon_config_name_var = tk.StringVar()
        ttk.Entry(fields_frame, textvariable=self.weapon_config_name_var, width=40).grid(
            row=0, column=1, columnspan=3, sticky=tk.W, padx=(6, 0)
        )

        row = 1

        # Range and Damage/damage_type are all seeded from a real source
        # (Range: the connected HardPoint's Fire_Range_Distance, or - for a
        # unit-weapon slot - the unit's own Targeting_Max_Attack_Distance;
        # Damage/damage_type: the connected Projectile) but can be
        # overridden per-mount (real, confirmed pattern - e.g.
        # HP_Victory_Weapon_02 sets its own Projectile_Damage/Damage_Type
        # alongside Fire_Projectile_Type) - so they get the same
        # override-tracked treatment (badge + Reset) as the rule-governed
        # fields below, even though no WeaponRule actually governs them
        # (_update_weapon_config_badges only shows a "rule:" badge for
        # fields in weapon_rules.RULE_FIELDS) - a saved template describes a
        # category of weapon, not one unit's engagement distance or a
        # specific mount's damage.
        # Accuracy/reload/burst/SFX are rule-governed (weapon_rules.RULE_FIELDS).
        # A unit-weapon slot has no Min/Max range (a single scalar recharge)
        # - _update_weapon_config_schema_visibility relabels/hides that row
        # per slot.
        rule_field_specs = [
            ("Range:", "fire_range", "weapon_config_range_var"),
            ("Damage:", "damage", "weapon_config_damage_var"),
            ("Damage Type:", "damage_type", "weapon_config_damage_type_var"),
            ("Min Recharge (s):", "fire_min_recharge", "weapon_config_min_recharge_var"),
            ("Max Recharge (s):", "fire_max_recharge", "weapon_config_max_recharge_var"),
            ("Pulse Count:", "fire_pulse_count", "weapon_config_pulse_count_var"),
            ("Pulse Delay (s):", "fire_pulse_delay", "weapon_config_pulse_delay_var"),
            ("Fire SFX Event:", "sfx_event", "weapon_config_sfx_event_var"),
        ]
        for label, field_name, attr in rule_field_specs:
            label_widget = ttk.Label(fields_frame, text=label)
            label_widget.grid(row=row, column=0, sticky=tk.W, pady=(6, 0))
            var = tk.StringVar()
            var.trace_add(
                "write", lambda *_, fn=field_name: self._on_weapon_config_rule_field_changed(fn)
            )
            setattr(self, attr, var)
            entry = ttk.Entry(fields_frame, textvariable=var, width=20)
            entry.grid(row=row, column=1, sticky=tk.W, padx=(6, 0), pady=(6, 0))
            badge = self._make_badge(fields_frame, "")
            badge.grid(row=row, column=2, sticky=tk.W, padx=(8, 0), pady=(6, 0))
            self._weapon_config_field_badges[field_name] = badge
            _Tooltip(badge, lambda fn=field_name: self._weapon_config_override_notes.get(fn, ""))
            badge.bind("<Double-Button-1>", lambda _e, fn=field_name: self._on_edit_override_note(fn))
            reset_button = ttk.Button(
                fields_frame, text=icon_text("reset", "Reset"), width=9,
                command=lambda fn=field_name: self._on_reset_weapon_config_field(fn),
            )
            reset_button.grid(row=row, column=3, sticky=tk.W, padx=(4, 0), pady=(6, 0))
            self._weapon_config_field_rows[field_name] = {"label": label_widget, "widgets": [entry, badge, reset_button]}
            row += 1

        accuracy_frame = self._make_card(right_scroll, title="Accuracy by Category")

        accuracy_header = ttk.Frame(accuracy_frame)
        accuracy_header.pack(fill=tk.X)
        accuracy_badge = self._make_badge(accuracy_header, "")
        accuracy_badge.pack(side=tk.LEFT)
        self._weapon_config_field_badges["accuracy"] = accuracy_badge
        _Tooltip(accuracy_badge, lambda: self._weapon_config_override_notes.get("accuracy", ""))
        accuracy_badge.bind("<Double-Button-1>", lambda _e: self._on_edit_override_note("accuracy"))
        ttk.Button(
            accuracy_header, text=icon_text("reset", "Reset"), width=9,
            command=lambda: self._on_reset_weapon_config_field("accuracy"),
        ).pack(side=tk.LEFT, padx=(8, 0))

        self._refresh_weapon_config_accuracy_tree = self._build_accuracy_table(
            accuracy_frame,
            tree_attr="weapon_config_accuracy_tree",
            category_var_attr="weapon_config_accuracy_category_var",
            category_combo_attr="weapon_config_accuracy_category_combo",
            value_var_attr="weapon_config_accuracy_value_var",
            get_dict=lambda: self._weapon_config_accuracy,
            on_change=lambda: self._on_weapon_config_rule_field_changed("accuracy"),
        )

        self.weapon_config_modifiers_frame = self._make_card(right_scroll, title="Modifiers")
        self._refresh_modifiers_tree, self._refresh_weapon_config_modifier_specs = self._build_modifiers_table(
            self.weapon_config_modifiers_frame,
            tree_attr="weapon_config_modifiers_tree",
            get_dict=lambda: self._weapon_config_modifiers,
            on_change=lambda: None,
            get_specs=lambda: modifiers_for_context(self._weapon_config_modifier_context),
        )

        category_restrictions_frame = self._make_card(right_scroll, title="Category Restrictions")
        self._refresh_weapon_config_category_restrictions_tree = self._build_category_list_table(
            category_restrictions_frame,
            combo_attr="weapon_config_category_restriction_var",
            tree_attr="weapon_config_category_restrictions_tree",
            get_list=lambda: self._weapon_config_category_restrictions,
            on_change=lambda: None,
        )

        self.weapon_config_analysis_frame = self._make_card(right_scroll, title="Analysis")

        target_row = ttk.Frame(self.weapon_config_analysis_frame)
        target_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(target_row, text="Target Armor:").pack(side=tk.LEFT)
        self.weapon_config_target_armor_var = tk.StringVar(value=TARGET_TYPE_NONE)
        self.weapon_config_target_armor_combo = ttk.Combobox(
            target_row, textvariable=self.weapon_config_target_armor_var, state="readonly", width=22,
        )
        self.weapon_config_target_armor_combo.pack(side=tk.LEFT, padx=(4, 16))
        self.weapon_config_target_armor_var.trace_add("write", lambda *_: self._update_weapon_config_analysis())

        ttk.Label(target_row, text="Target Shield:").pack(side=tk.LEFT)
        self.weapon_config_target_shield_var = tk.StringVar(value=TARGET_TYPE_NONE)
        self.weapon_config_target_shield_combo = ttk.Combobox(
            target_row, textvariable=self.weapon_config_target_shield_var, state="readonly", width=22,
        )
        self.weapon_config_target_shield_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.weapon_config_target_shield_var.trace_add("write", lambda *_: self._update_weapon_config_analysis())

        self.weapon_config_analysis_label = ttk.Label(
            self.weapon_config_analysis_frame, text="(no slot selected)", justify=tk.LEFT,
        )
        self.weapon_config_analysis_label.pack(anchor=tk.W)
        self._refresh_target_type_combos()

        def refresh_badge_colors():
            for name, badge in self._weapon_config_field_badges.items():
                self._set_badge_kind(badge, self._weapon_config_field_badge_kind.get(name, "neutral"))

        self._theme_refresh_callbacks.append(refresh_badge_colors)

        self._refresh_wc_unit_combo()
        self._show_weapon_config_placeholder()

    def _build_modifiers_table(self, parent: ttk.Frame, tree_attr: str, get_dict, on_change, get_specs):
        """Builds a dropdown-driven modifier list + add-row controls inside
        `parent`, backed by whatever dict `get_dict()` currently returns -
        shared by the Weapon Configs tab (backed by the selected slot's
        modifiers, schema-filtered live via `get_specs`) and the Weapon
        Templates tab (backed by the template's own dict directly, always
        offered the full catalog since a template isn't tied to one
        schema). Value input swaps between a Yes/No combobox and a plain
        Entry depending on the selected modifier's kind - unlike the
        fixed-shape accuracy table, so this is a separate, purpose-built
        widget. Rows are keyed by each spec's schema-agnostic `key` (not the
        raw XML tag, which can differ per schema for the same concept).
        Returns `(refresh_tree, refresh_specs)` - the caller invokes
        `refresh_specs()` again whenever the set of selectable modifiers
        should change (e.g. the Weapon Configs tab calls it whenever the
        displayed slot's schema changes).
        """
        label_to_spec: dict[str, object] = {}

        tree = ttk.Treeview(parent, columns=("value",), show="tree headings", height=5)
        tree.heading("#0", text="Modifier")
        tree.heading("value", text="Value")
        tree.column("#0", width=300, anchor=tk.W)
        tree.column("value", width=80, anchor=tk.E)
        tree.pack(fill=tk.X)
        setattr(self, tree_attr, tree)

        desc_label = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=460, justify=tk.LEFT)
        desc_label.pack(fill=tk.X, pady=(4, 0))

        add_row = ttk.Frame(parent)
        add_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(add_row, text="Modifier:").pack(side=tk.LEFT)
        name_var = tk.StringVar()
        name_combo = ttk.Combobox(add_row, textvariable=name_var, state="readonly", width=42)
        name_combo.pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(add_row, text="Value:").pack(side=tk.LEFT)
        bool_var = tk.StringVar(value="Yes")
        bool_combo = ttk.Combobox(
            add_row, textvariable=bool_var, state="readonly", values=["Yes", "No"], width=8,
        )
        _autosize_combobox_popdown(bool_combo)
        float_var = tk.StringVar()
        float_entry = ttk.Entry(add_row, textvariable=float_var, width=10)
        bool_combo.pack(side=tk.LEFT, padx=(4, 0))

        def refresh_tree():
            tree.delete(*tree.get_children())
            for key, value in sorted(get_dict().items()):
                spec = MODIFIERS_BY_KEY.get(key)
                label = spec.label if spec is not None else key
                tree.insert("", tk.END, iid=key, text=label, values=(value,))

        def refresh_specs():
            specs = get_specs()
            label_to_spec.clear()
            label_to_spec.update({m.label: m for m in specs})
            name_combo.config(values=sorted(label_to_spec))
            _autosize_combobox_popdown(name_combo)
            if name_var.get() not in label_to_spec:
                name_var.set("")
                desc_label.config(text="")

        def on_name_selected():
            spec = label_to_spec.get(name_var.get())
            if spec is None:
                desc_label.config(text="")
                return
            desc_label.config(text=spec.description)
            if spec.kind == KIND_BOOL:
                float_entry.pack_forget()
                bool_combo.pack(side=tk.LEFT, padx=(4, 0))
            else:
                bool_combo.pack_forget()
                float_entry.pack(side=tk.LEFT, padx=(4, 0))

        name_combo.bind("<<ComboboxSelected>>", lambda _e: on_name_selected())

        def on_add():
            spec = label_to_spec.get(name_var.get())
            if spec is None:
                messagebox.showinfo("Modifier required", "Select a modifier from the dropdown first.")
                return
            if spec.kind == KIND_BOOL:
                ui_value = bool_var.get().strip().lower() == "yes"
            else:
                ui_value = weapon_config_to_float(float_var.get())
            # A dict keyed by the spec's stable key allows at most one value
            # per modifier - this Add/Update simply overwrites rather than
            # duplicating a row.
            get_dict()[spec.key] = format_modifier_value(spec, ui_value)
            refresh_tree()
            on_change()

        def on_remove():
            selection = tree.selection()
            if not selection:
                return
            for key in selection:
                get_dict().pop(key, None)
            refresh_tree()
            on_change()

        def on_select_row(_event):
            selection = tree.selection()
            if not selection:
                return
            key = selection[0]
            spec = MODIFIERS_BY_KEY.get(key)
            if spec is None or spec.label not in label_to_spec:
                return
            name_var.set(spec.label)
            on_name_selected()
            raw = get_dict().get(key, "")
            if spec.kind == KIND_BOOL:
                bool_var.set("Yes" if parse_bool(raw) else "No")
            else:
                float_var.set(raw)

        tree.bind("<<TreeviewSelect>>", on_select_row)

        ttk.Button(add_row, text=icon_text("add", "Add / Update"), command=on_add).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(
            add_row, text=icon_text("remove", "Remove Selected"), command=on_remove,
        ).pack(side=tk.LEFT, padx=(4, 0))

        refresh_specs()
        refresh_tree()
        return refresh_tree, refresh_specs

    def _refresh_modifier_catalog_choices(self, context: str):
        """Re-populates the Weapon Configs tab's modifier dropdown with only
        the concepts that apply to `context` (hardpoint vs unit-weapon),
        since the two schemas don't support the same set (e.g.
        Power-to-Weapons mode is ship/hardpoint-only; the deployed-state
        movement fields are direct-unit-weapon-only).
        """
        self._weapon_config_modifier_context = context
        self._refresh_weapon_config_modifier_specs()

    def _theatre_tags(self, theatre: str) -> tuple[str, ...]:
        return (SPACEUNIT_TAG,) if theatre == THEATRE_SPACE else (GROUNDVEHICLE_TAG, GROUNDINFANTRY_TAG)

    def _wc_unit_names_for_theatre(self) -> list[str]:
        tags = self._theatre_tags(self.wc_theatre_var.get())
        entries = self.combat_unit_load_result.entries
        return sorted(n for n in self.all_combat_unit_names if entries[n].element.tag in tags)

    def _refresh_wc_unit_combo(self):
        self._filter_search_combo(self.wc_unit_combo, self._wc_unit_names_for_theatre(), self.wc_unit_var)
        self._filter_search_combo(
            self.weapon_config_category_combo, sorted(self.weapon_rules), self.weapon_config_category_var,
        )

    def _on_wc_theatre_changed(self):
        self.wc_unit_var.set("")
        self._refresh_wc_unit_combo()
        self._load_wc_unit(None)

    def _on_wc_unit_selected(self, _event=None):
        name = self.wc_unit_var.get().strip()
        entries = self.combat_unit_load_result.entries
        if name not in entries or entries[name].element.tag not in self._theatre_tags(self.wc_theatre_var.get()):
            messagebox.showinfo("Unit not found", f"{name!r} isn't a loaded {self.wc_theatre_var.get()} unit.")
            return
        self._load_wc_unit(name)

    def _load_wc_unit(self, unit_name: str | None):
        if self._current_slot_index is not None:
            self._write_back_current_slot()
        self._current_slot_index = None
        self._current_wc_unit_name = unit_name

        if unit_name is None:
            self._current_unit_slots = []
            self._refresh_slot_tree()
            self._show_weapon_config_placeholder()
            return

        self._current_unit_slots = self._build_unit_slots(unit_name)
        self._refresh_slot_tree()
        if self._current_unit_slots:
            self.weapon_config_slot_tree.selection_set("0")
            self.weapon_config_slot_tree.see("0")
            self._current_slot_index = 0
            self._display_slot(self._current_unit_slots[0])
        else:
            self._show_weapon_config_placeholder()
            messagebox.showinfo(
                "No weapons found", f"{unit_name!r} has no weapon hardpoints or direct weapon fields.",
            )

    def _build_unit_slots(self, unit_name: str) -> list[HardpointGroup]:
        """Every weapon/hardpoint slot the unit actually has, from both real
        schemas at once (a unit can have both - see SPMAT_Walker). A slot
        whose auto-generated name matches a previously-saved config reuses
        that saved config (with its rule/overrides/notes intact) instead of
        a fresh reseed, so returning to a unit never loses prior work.
        """
        entries = self.combat_unit_load_result.entries
        loadout = build_loadout(unit_name, entries, self.hardpoint_load_result.entries, self.load_result.entries)
        slots = list(loadout.weapon_groups)

        try:
            direct = build_unit_weapon_group(unit_name, entries, self.load_result.entries)
            if direct is not None:
                slots.append(direct)
        except InheritanceCycleError as exc:
            messagebox.showerror("Inheritance cycle", str(exc))

        for slot in slots:
            auto_name = f"{unit_name} - {slot.label}"
            saved = self.weapon_configs.get(auto_name)
            if saved is not None:
                slot.weapon_config = saved
            else:
                slot.weapon_config.name = auto_name
                slot.weapon_config.unit_name = unit_name
            slot.stats = analyze_weapon_config(slot.weapon_config)

        return slots

    def _refresh_slot_tree(self):
        self.weapon_config_slot_tree.delete(*self.weapon_config_slot_tree.get_children())
        for index, slot in enumerate(self._current_unit_slots):
            self.weapon_config_slot_tree.insert("", tk.END, iid=str(index), text=slot.label, values=self._slot_row_values(slot))

    def _slot_row_values(self, slot: HardpointGroup) -> tuple:
        type_label = "Direct Weapon" if slot.weapon_config.context == CONTEXT_UNIT_WEAPON else "HardPoint"
        return (slot.count, type_label, slot.weapon_config.category or "-")

    def _refresh_slot_tree_row(self, index: int | None):
        if index is None or not self.weapon_config_slot_tree.exists(str(index)):
            return
        self.weapon_config_slot_tree.item(str(index), values=self._slot_row_values(self._current_unit_slots[index]))

    def _on_select_slot(self, _event):
        selection = self.weapon_config_slot_tree.selection()
        if not selection:
            return
        new_index = int(selection[0])
        if self._current_slot_index is not None and self._current_slot_index != new_index:
            self._write_back_current_slot()
        self._current_slot_index = new_index
        self._display_slot(self._current_unit_slots[new_index])

    def _write_back_current_slot(self):
        """Writes the form back into the current slot's in-memory
        WeaponConfig AND into self.weapon_configs (the same dict "Save All
        Slots" persists to disk) - not just the local `_current_unit_slots`
        list, which gets replaced wholesale by `_build_unit_slots` the
        moment the user switches to a different unit. Without also updating
        `self.weapon_configs` here, switching units before an explicit Save
        would silently discard whatever was just edited.
        """
        if self._current_slot_index is None:
            return
        slot = self._current_unit_slots[self._current_slot_index]
        slot.weapon_config = self._read_weapon_config_from_fields()
        slot.stats = analyze_weapon_config(slot.weapon_config)
        self.weapon_configs[slot.weapon_config.name] = slot.weapon_config
        self._refresh_slot_tree_row(self._current_slot_index)

    def _display_slot(self, slot: HardpointGroup):
        self._set_slot_form(slot.weapon_config)

    def _set_slot_form(self, config: WeaponConfig):
        self.weapon_config_name_var.set(config.name)
        self.weapon_config_category_var.set(config.category)
        self.weapon_config_source_projectile_label.config(text=config.source_projectile_name or "(none)")
        is_hardpoint = config.context == CONTEXT_HARDPOINT
        self.weapon_config_source_hardpoint_label.config(
            text=config.source_hardpoint_name if is_hardpoint and config.source_hardpoint_name
            else "(direct unit weapon)"
        )
        self._set_weapon_config_field_vars(config)
        self._update_weapon_config_schema_visibility(config.context)
        self._update_weapon_config_analysis()

    def _show_weapon_config_placeholder(self):
        self.weapon_config_name_var.set("")
        self.weapon_config_category_var.set("")
        self.weapon_config_source_projectile_label.config(text="(none)")
        self.weapon_config_source_hardpoint_label.config(text="(none)")
        self._set_weapon_config_field_vars(WeaponConfig(name=""))
        self._update_weapon_config_schema_visibility(CONTEXT_HARDPOINT)
        self.weapon_config_analysis_label.config(text="(no slot selected)")

    def _update_weapon_config_schema_visibility(self, context: str):
        """A unit-weapon slot has a single scalar recharge (no Min/Max
        range) - relabel/hide that row so the form matches whichever real
        schema this slot uses. Fire SFX Event stays visible for both
        schemas: a HardPoint slot reads its own Fire_SFXEvent, a unit-weapon
        slot reads the unit's own SFXEvent_Fire (a different tag, but still
        real firing-sound data - seed_from_unit_weapon/weapon_config_export
        handle the per-schema tag-name difference).
        """
        is_unit_weapon = context == CONTEXT_UNIT_WEAPON
        self._weapon_config_field_rows["fire_min_recharge"]["label"].config(
            text="Recharge (s):" if is_unit_weapon else "Min Recharge (s):"
        )
        for widget in self._weapon_config_field_rows["fire_max_recharge"]["widgets"]:
            widget.grid_remove() if is_unit_weapon else widget.grid()

        # Modifiers apply to both schemas, but which concepts are valid
        # differs (e.g. Power-to-Weapons mode is hardpoint/ship-only; the
        # deployed-state movement fields are direct-unit-weapon-only) - the
        # section stays visible for both, only its dropdown's choices change.
        self._refresh_modifier_catalog_choices(context)

    def _set_weapon_config_field_vars(self, config: WeaponConfig):
        self._weapon_config_overridden_fields = set(config.overridden_fields)
        self._weapon_config_override_notes = dict(config.override_notes)
        self._weapon_config_accuracy = dict(config.accuracy_by_category)
        self._refresh_weapon_config_accuracy_tree()
        self._weapon_config_modifiers = dict(config.modifiers)
        self._refresh_modifiers_tree()
        self._weapon_config_category_restrictions = list(config.category_restrictions)
        self._refresh_weapon_config_category_restrictions_tree()
        self._weapon_config_field_traces_suspended = True
        try:
            self.weapon_config_damage_var.set(str(config.damage))
            self.weapon_config_damage_type_var.set(config.damage_type)
            self.weapon_config_min_recharge_var.set(str(config.fire_min_recharge))
            self.weapon_config_max_recharge_var.set(str(config.fire_max_recharge))
            self.weapon_config_pulse_count_var.set(str(config.fire_pulse_count))
            self.weapon_config_pulse_delay_var.set(str(config.fire_pulse_delay))
            self.weapon_config_range_var.set(str(config.fire_range))
            self.weapon_config_sfx_event_var.set(config.sfx_event)
        finally:
            self._weapon_config_field_traces_suspended = False
        self._update_weapon_config_badges()

    def _update_weapon_config_badges(self):
        category = self.weapon_config_category_var.get().strip()
        for field_name, badge in self._weapon_config_field_badges.items():
            if field_name in self._weapon_config_overridden_fields:
                self._set_field_badge(field_name, badge, "custom", "warning")
            elif category and field_name in RULE_FIELDS:
                # damage/damage_type get the same badge/Reset UI but aren't
                # rule-governed (weapon_rules.RULE_FIELDS) - they only ever
                # come from the connected Projectile, never a category rule.
                self._set_field_badge(field_name, badge, f"rule: {category}", "link")
            else:
                self._set_field_badge(field_name, badge, "seeded", "neutral")

    def _set_field_badge(self, field_name: str, badge: tk.Label, text: str, kind: str):
        badge.config(text=text)
        self._weapon_config_field_badge_kind[field_name] = kind
        self._set_badge_kind(badge, kind)

    def _read_weapon_config_from_fields(self) -> WeaponConfig:
        """Builds a WeaponConfig from the current form state, preserving the
        currently-selected slot's identity fields (unit_name/context/source
        names/notes aren't user-editable form widgets - they come from the
        slot itself) so live analysis and Save/Export never drift apart.
        """
        base = (
            self._current_unit_slots[self._current_slot_index].weapon_config
            if self._current_slot_index is not None else WeaponConfig(name="")
        )
        return WeaponConfig(
            name=self.weapon_config_name_var.get().strip(),
            unit_name=base.unit_name,
            source_projectile_name=base.source_projectile_name,
            source_hardpoint_name=base.source_hardpoint_name,
            context=base.context,
            category=self.weapon_config_category_var.get().strip(),
            damage=weapon_config_to_float(self.weapon_config_damage_var.get()),
            damage_type=self.weapon_config_damage_type_var.get().strip(),
            fire_min_recharge=weapon_config_to_float(self.weapon_config_min_recharge_var.get()),
            fire_max_recharge=weapon_config_to_float(self.weapon_config_max_recharge_var.get()),
            fire_pulse_count=weapon_config_to_int(self.weapon_config_pulse_count_var.get()),
            fire_pulse_delay=weapon_config_to_float(self.weapon_config_pulse_delay_var.get()),
            fire_range=weapon_config_to_float(self.weapon_config_range_var.get()),
            accuracy_by_category=dict(self._weapon_config_accuracy),
            sfx_event=self.weapon_config_sfx_event_var.get().strip(),
            modifiers=dict(self._weapon_config_modifiers),
            category_restrictions=list(self._weapon_config_category_restrictions),
            notes=base.notes,
            overridden_fields=set(self._weapon_config_overridden_fields),
            override_notes=dict(self._weapon_config_override_notes),
        )

    def _on_weapon_config_field_changed(self):
        if self._weapon_config_field_traces_suspended:
            return
        self._update_weapon_config_analysis()

    def _on_weapon_config_rule_field_changed(self, field_name: str):
        if not self._weapon_config_field_traces_suspended:
            self._weapon_config_overridden_fields.add(field_name)
            self._update_weapon_config_badges()
        self._on_weapon_config_field_changed()

    def _on_edit_override_note(self, field_name: str):
        if field_name not in self._weapon_config_overridden_fields:
            messagebox.showinfo("Not overridden", "Only an overridden (custom) field can have a note.")
            return
        current = self._weapon_config_override_notes.get(field_name, "")
        note = simpledialog.askstring(
            "Override note", f"Why was {field_name!r} overridden?", initialvalue=current, parent=self.root,
        )
        if note is None:
            return
        if note.strip():
            self._weapon_config_override_notes[field_name] = note.strip()
        else:
            self._weapon_config_override_notes.pop(field_name, None)

    def _on_reset_weapon_config_field(self, field_name: str):
        """Clears the field's override (and any note) so the next seed/rule
        application can fill it again, then immediately re-derives it: from
        the active rule if a category is set, otherwise by re-seeding from
        this slot's real source (a HardPoint, or the unit's own direct
        weapon fields - whichever schema this slot uses).
        """
        self._weapon_config_overridden_fields.discard(field_name)
        self._weapon_config_override_notes.pop(field_name, None)
        config = self._read_weapon_config_from_fields()

        if field_name in ("damage", "damage_type"):
            # damage/damage_type only ever come from the connected
            # Projectile, never from the hardpoint/unit-weapon itself or a
            # category rule - re-seed from there specifically.
            if config.source_projectile_name and config.source_projectile_name in self.load_result.entries:
                try:
                    proj_chain = resolve_chain(self.load_result.entries, config.source_projectile_name)
                    proj_resolved = merge_chain(self.load_result.entries, proj_chain)
                    seed_from_projectile(config, proj_resolved)
                except InheritanceCycleError as exc:
                    messagebox.showerror("Inheritance cycle", str(exc))
            self._apply_slot_config(config)
            return

        if field_name == "fire_range":
            # Not rule-governed either (a saved template describes a
            # category of weapon, not one unit's engagement distance) - a
            # WeaponRule.apply_rule() call would silently no-op on it since
            # it's deliberately excluded from RULE_FIELDS, so bypass that
            # branch entirely and re-seed straight from the real source,
            # same as damage/damage_type above.
            if config.context == CONTEXT_HARDPOINT:
                entry = self.hardpoint_load_result.entries.get(config.source_hardpoint_name)
                if entry is not None:
                    seed_from_hardpoint(config, extract_fields(entry.element))
            elif config.context == CONTEXT_UNIT_WEAPON:
                entries = self.combat_unit_load_result.entries
                if config.unit_name in entries:
                    try:
                        chain = resolve_chain(entries, config.unit_name)
                        resolved_fields = merge_chain(entries, chain)
                        seed_from_unit_weapon(config, resolved_fields, entries, chain)
                    except InheritanceCycleError as exc:
                        messagebox.showerror("Inheritance cycle", str(exc))
            self._apply_slot_config(config)
            return

        rule = self.weapon_rules.get(config.category)
        if rule is not None:
            apply_rule(config, rule)
        elif config.context == CONTEXT_HARDPOINT:
            entry = self.hardpoint_load_result.entries.get(config.source_hardpoint_name)
            if entry is not None:
                seed_from_hardpoint(config, extract_fields(entry.element))
        elif config.context == CONTEXT_UNIT_WEAPON:
            entries = self.combat_unit_load_result.entries
            if config.unit_name in entries:
                try:
                    chain = resolve_chain(entries, config.unit_name)
                    resolved_fields = merge_chain(entries, chain)
                    seed_from_unit_weapon(config, resolved_fields, entries, chain)
                except InheritanceCycleError as exc:
                    messagebox.showerror("Inheritance cycle", str(exc))

        self._apply_slot_config(config)

    def _on_apply_weapon_rule(self):
        category = self.weapon_config_category_var.get().strip()
        rule = self.weapon_rules.get(category)
        if rule is None:
            messagebox.showinfo("Template not found", f"No saved Weapon Template for category {category!r}.")
            return

        config = self._read_weapon_config_from_fields()
        config.category = category
        apply_rule(config, rule)
        self._apply_slot_config(config)

    def _on_create_rule_from_slot(self):
        """The reverse of Apply Template: captures the currently-displayed
        slot's rate-of-fire/accuracy/SFX/modifiers/category-restriction
        fields into a new (or overwritten) saved Weapon Template, so a
        hand-tuned slot can be reused as a preset for other weapons without
        re-typing every field on the Weapon Templates tab by hand.
        """
        if self._current_slot_index is None:
            messagebox.showinfo("No slot loaded", "Select a weapon/hardpoint slot first.")
            return

        config = self._read_weapon_config_from_fields()
        category = simpledialog.askstring(
            "New Weapon Template", "Category name for this template:", initialvalue=config.category, parent=self.root,
        )
        if category is None:
            return
        category = category.strip()
        if not category:
            messagebox.showwarning("Category required", "Give this template a category name before saving.")
            return

        if category in self.weapon_rules:
            if not messagebox.askyesno(
                "Template exists",
                f"A Weapon Template for {category!r} already exists. Overwrite it with this slot's settings?",
            ):
                return

        rule = WeaponRule(
            category=category,
            accuracy_by_category=dict(config.accuracy_by_category),
            fire_min_recharge=config.fire_min_recharge,
            fire_max_recharge=config.fire_max_recharge,
            fire_pulse_count=config.fire_pulse_count,
            fire_pulse_delay=config.fire_pulse_delay,
            sfx_event=config.sfx_event,
            modifiers=dict(config.modifiers),
            category_restrictions=list(config.category_restrictions),
        )
        self.weapon_rules[category] = rule
        save_weapon_rules(list(self.weapon_rules.values()))
        self._refresh_weapon_rules_list()

        self.weapon_config_category_var.set(category)
        messagebox.showinfo("Template created", f"Saved this slot's settings as the {category!r} Weapon Template.")

    def _apply_slot_config(self, config: WeaponConfig):
        if self._current_slot_index is not None:
            slot = self._current_unit_slots[self._current_slot_index]
            slot.weapon_config = config
            slot.stats = analyze_weapon_config(config)
        self._set_slot_form(config)
        self._refresh_slot_tree_row(self._current_slot_index)

    def _update_weapon_config_analysis(self):
        config = self._read_weapon_config_from_fields()
        stats = analyze_weapon_config(config)

        armor_type = self.weapon_config_target_armor_var.get().strip()
        armor_type = "" if armor_type == TARGET_TYPE_NONE else armor_type
        shield_type = self.weapon_config_target_shield_var.get().strip()
        shield_type = "" if shield_type == TARGET_TYPE_NONE else shield_type
        # Same formula combat_sim.py uses per-weapon (stats.dps_avg *
        # matrix.multiplier(...)), minus the group-count multiplication -
        # this analyzes one weapon slot in isolation, not a counted group.
        dps_vs_shield = stats.dps_avg * self.damage_matrix.multiplier(config.damage_type, shield_type)
        dps_vs_armor = stats.dps_avg * self.damage_matrix.multiplier(config.damage_type, armor_type)

        self.weapon_config_analysis_label.config(
            text=(
                f"Shots per cycle: {stats.shots_per_cycle}\n"
                f"Damage per shot: {stats.damage_per_shot:g}    Damage per cycle: {stats.damage_per_cycle:g}\n"
                f"Cycle time - min: {stats.cycle_time_min:g}s  avg: {stats.cycle_time_avg:g}s  "
                f"max: {stats.cycle_time_max:g}s\n"
                f"DPS - min: {stats.dps_min:g}  avg: {stats.dps_avg:g}  max: {stats.dps_max:g}\n"
                f"DPS vs Shield ({shield_type or 'none'}): {dps_vs_shield:g}\n"
                f"DPS vs Armor ({armor_type or 'none'}): {dps_vs_armor:g}"
            )
        )

    def _on_view_source_projectile(self):
        if self._current_slot_index is None:
            return
        name = self._current_unit_slots[self._current_slot_index].weapon_config.source_projectile_name
        if not name or name not in self.load_result.entries:
            messagebox.showinfo("Projectile not found", f"{name!r} isn't among the currently loaded projectiles.")
            return
        self._open_projectile_from_hardpoint(name)

    def _on_view_source_hardpoint(self):
        if self._current_slot_index is None:
            return
        name = self._current_unit_slots[self._current_slot_index].weapon_config.source_hardpoint_name
        if not name or name not in self.hardpoint_load_result.entries:
            messagebox.showinfo("Hardpoint not found", f"{name!r} isn't among the currently loaded hardpoints.")
            return
        self.notebook.select(self.reader_tab_widget)
        self.reader_notebook.select(self.hardpoints_tab_widget)
        self._select_and_display_hardpoint(name)

    def _on_save_all_slots(self):
        if self._current_slot_index is not None:
            self._write_back_current_slot()
        if not self._current_unit_slots:
            messagebox.showinfo("Nothing to save", "Select a unit with at least one weapon/hardpoint first.")
            return

        for slot in self._current_unit_slots:
            self.weapon_configs[slot.weapon_config.name] = slot.weapon_config
        save_weapon_configs(list(self.weapon_configs.values()))
        messagebox.showinfo(
            "Saved", f"Saved {len(self._current_unit_slots)} slot(s) for {self._current_wc_unit_name!r}.",
        )

    def _confirm_damage_override(self, overridden_slots: list[HardpointGroup]) -> str:
        """Shown before export when one or more slots override the damage/
        damage_type of a connected Projectile (a real, deliberate pattern -
        see HP_Victory_Weapon_02 - but worth a second look, since it's easy
        to mean to edit the Projectile itself instead). Returns "export",
        "cancel", or "view:<projectile_name>".
        """
        result = {"action": "cancel"}
        dialog = tk.Toplevel(self.root)
        dialog.title("Damage override detected")
        dialog.transient(self.root)
        dialog.grab_set()

        lines = [
            f"- {s.weapon_config.name}  (fires {s.weapon_config.source_projectile_name})"
            for s in overridden_slots
        ]
        message = (
            "The following weapon(s) override the connected projectile's own damage/damage type:\n\n"
            + "\n".join(lines)
            + "\n\nExport with these per-weapon overrides, or edit the projectile itself instead?"
        )
        ttk.Label(dialog, text=message, justify=tk.LEFT, padding=12, wraplength=440).pack()

        button_row = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        button_row.pack(fill=tk.X)

        def choose(action: str):
            result["action"] = action
            dialog.destroy()

        ttk.Button(button_row, text="Export Anyway", command=lambda: choose("export")).pack(side=tk.LEFT)

        distinct_projectiles = sorted({s.weapon_config.source_projectile_name for s in overridden_slots})
        for name in distinct_projectiles:
            ttk.Button(
                button_row, text=f"View {name}", command=lambda n=name: choose(f"view:{n}"),
            ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(button_row, text="Cancel", command=lambda: choose("cancel")).pack(side=tk.RIGHT)

        dialog.wait_window()
        return result["action"]

    def _on_export_unit_xml(self):
        if self._current_slot_index is not None:
            self._write_back_current_slot()
        if not self._current_unit_slots:
            messagebox.showinfo("Nothing to export", "Select a unit with at least one weapon/hardpoint first.")
            return

        overridden_slots = [
            s for s in self._current_unit_slots
            if s.weapon_config.source_projectile_name
            and ({"damage", "damage_type"} & s.weapon_config.overridden_fields)
        ]
        if overridden_slots:
            action = self._confirm_damage_override(overridden_slots)
            if action == "cancel":
                return
            if action.startswith("view:"):
                self._open_projectile_from_hardpoint(action[len("view:"):])
                return
            # action == "export" - fall through and continue exporting

        hardpoint_configs = [
            s.weapon_config for s in self._current_unit_slots if s.weapon_config.context == CONTEXT_HARDPOINT
        ]
        unit_weapon_configs = [
            s.weapon_config for s in self._current_unit_slots if s.weapon_config.context == CONTEXT_UNIT_WEAPON
        ]
        safe_unit = "".join(c for c in self._current_wc_unit_name if c.isalnum() or c in " _-")

        if hardpoint_configs:
            path = filedialog.asksaveasfilename(
                title="Export Hardpoints XML", defaultextension=".xml",
                initialfile=f"HardPoints_{safe_unit}.xml", filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(build_hardpoints_file_xml(hardpoint_configs))

        if unit_weapon_configs:
            base_unit_tag = self.combat_unit_load_result.entries[self._current_wc_unit_name].element.tag
            path = filedialog.asksaveasfilename(
                title="Export Unit Weapons XML", defaultextension=".xml",
                initialfile=f"Weapons_{safe_unit}.xml", filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(build_unit_weapons_file_xml(base_unit_tag, unit_weapon_configs))

        messagebox.showinfo("Exported", "Export complete.")

    def _filter_search_combo(self, combo: ttk.Combobox, master_list: list[str], var: tk.StringVar):
        """Live search filter for a combobox's dropdown: narrows `combo`'s
        values to case-insensitive substring matches of whatever is
        currently typed in `var`, always re-filtering from the full
        `master_list` so backspacing widens the list again.
        """
        query = var.get().strip().lower()
        values = master_list if not query else [n for n in master_list if query in n.lower()]
        combo.config(values=values)
        _autosize_combobox_popdown(combo)

    # -- battle sim --------------------------------------------------------------

    def _load_battle_sim_data(self, file_paths: list[str], preferred_files: set[str] | None = None):
        """Loads the combined "any fightable unit" list (Space/Ground units,
        excluding Containers/Companies/Squadrons - those are rosters, not a
        single unit to simulate) and the damage/armor multiplier matrix from
        GAMECONSTANTS.XML, independent of whatever Theatre/Unit-Type filter
        the Reader tab's Units sub-tab currently has selected.
        """
        tags = [SPACEUNIT_TAG, GROUNDVEHICLE_TAG, GROUNDINFANTRY_TAG]
        self.combat_unit_load_result = load_files(file_paths, tags, preferred_files=preferred_files or set())
        self.all_combat_unit_names = sorted(self.combat_unit_load_result.entries.keys())

        gc_path = find_game_constants_file(file_paths)
        if gc_path is not None:
            self.damage_matrix = parse_damage_matrix(gc_path)
            self.shield_recharge_interval_secs = parse_shield_recharge_interval(gc_path)
        else:
            self.damage_matrix = DamageMatrix()
            self.shield_recharge_interval_secs = 1.0

        self._refresh_battle_sim_combos()
        self._refresh_target_type_combos()

    def _refresh_battle_sim_combos(self):
        self._filter_search_combo(self.battle_ally_combo, self.all_combat_unit_names, self.battle_ally_var)
        self._filter_search_combo(self.battle_enemy_combo, self.all_combat_unit_names, self.battle_enemy_var)

    def _refresh_target_type_combos(self):
        """Repopulates the Weapon Configs tab's Target Armor/Target Shield
        pickers from the real damage-multiplier matrix (GAMECONSTANTS.XML)
        whenever it (re)loads - the same one place `self.damage_matrix`
        itself is ever assigned, on project load or manual multi-file load.
        """
        values = [TARGET_TYPE_NONE, *all_target_types(self.damage_matrix)]
        for combo in (self.weapon_config_target_armor_combo, self.weapon_config_target_shield_combo):
            combo.config(values=values)
            _autosize_combobox_popdown(combo)

    def _build_battle_sim_tab(self, parent: ttk.Frame):
        picker_row = ttk.Frame(parent, padding=8)
        picker_row.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(picker_row, text="Ally Unit:").grid(row=0, column=0, sticky=tk.W)
        self.battle_ally_var = tk.StringVar()
        self.battle_ally_combo = ttk.Combobox(picker_row, textvariable=self.battle_ally_var, width=40)
        self.battle_ally_combo.grid(row=0, column=1, sticky=tk.W, padx=(6, 20))
        self.battle_ally_var.trace_add(
            "write", lambda *_: self._filter_search_combo(
                self.battle_ally_combo, self.all_combat_unit_names, self.battle_ally_var,
            )
        )
        self.battle_ally_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_battle_sim_changed())
        self.battle_ally_combo.bind("<Return>", lambda _e: self._on_battle_sim_changed())

        ttk.Label(picker_row, text="Enemy Unit:").grid(row=0, column=2, sticky=tk.W)
        self.battle_enemy_var = tk.StringVar()
        self.battle_enemy_combo = ttk.Combobox(picker_row, textvariable=self.battle_enemy_var, width=40)
        self.battle_enemy_combo.grid(row=0, column=3, sticky=tk.W, padx=(6, 20))
        self.battle_enemy_var.trace_add(
            "write", lambda *_: self._filter_search_combo(
                self.battle_enemy_combo, self.all_combat_unit_names, self.battle_enemy_var,
            )
        )
        self.battle_enemy_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_battle_sim_changed())
        self.battle_enemy_combo.bind("<Return>", lambda _e: self._on_battle_sim_changed())

        ttk.Button(
            picker_row, text=icon_text("simulate", "Simulate"), style="Accent.TButton", command=self._on_battle_sim_changed,
        ).grid(row=0, column=4)

        loadout_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        loadout_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.battle_ally_frame, self.battle_ally_summary, self.battle_ally_tree = (
            self._build_battle_loadout_panel(loadout_pane, "Ally")
        )
        self.battle_enemy_frame, self.battle_enemy_summary, self.battle_enemy_tree = (
            self._build_battle_loadout_panel(loadout_pane, "Enemy")
        )

        prediction_frame = self._surface_frame(
            parent, title="Battle Prediction (Ally attacking Enemy)", icon_key="battle_sim",
            place=lambda w: w.pack(side=tk.TOP, fill=tk.BOTH, padx=8, pady=(0, 8)),
        )

        columns = ("count", "dps_shield", "dps_hull")
        self.battle_result_tree = ttk.Treeview(prediction_frame, columns=columns, show="tree headings", height=6)
        self.battle_result_tree.heading("#0", text="Weapon")
        self.battle_result_tree.heading("count", text="Count")
        self.battle_result_tree.heading("dps_shield", text="DPS vs Shield")
        self.battle_result_tree.heading("dps_hull", text="DPS vs Hull")
        self.battle_result_tree.column("#0", width=260, anchor=tk.W)
        self.battle_result_tree.column("count", width=60, anchor=tk.CENTER)
        self.battle_result_tree.column("dps_shield", width=120, anchor=tk.E)
        self.battle_result_tree.column("dps_hull", width=120, anchor=tk.E)
        self.battle_result_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        summary_row = ttk.Frame(prediction_frame)
        summary_row.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

        self.battle_model_regen_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            summary_row, text="Model shield regen", variable=self.battle_model_regen_var,
            command=self._render_battle_summary,
        ).pack(side=tk.LEFT)

        self.battle_summary_label = ttk.Label(prediction_frame, text="Select an Ally and Enemy unit to simulate.", justify=tk.LEFT)
        self.battle_summary_label.pack(side=tk.TOP, anchor=tk.W, pady=(8, 0))

    def _build_battle_loadout_panel(self, parent: ttk.PanedWindow, title: str):
        frame = self._surface_frame(parent, title=title, place=lambda w: parent.add(w, weight=1))

        summary_label = ttk.Label(frame, text="(no unit selected)", justify=tk.LEFT)
        summary_label.pack(side=tk.TOP, anchor=tk.W, pady=(0, 8))

        columns = ("count", "detail")
        tree = ttk.Treeview(frame, columns=columns, show="tree headings")
        tree.heading("#0", text="Hardpoint")
        tree.heading("count", text="Count")
        tree.heading("detail", text="Detail")
        tree.column("#0", width=220, anchor=tk.W)
        tree.column("count", width=50, anchor=tk.CENTER)
        tree.column("detail", width=260, anchor=tk.W)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree.config(yscrollcommand=scroll.set)

        return frame, summary_label, tree

    def _render_unit_loadout(self, loadout: UnitLoadout | None, summary_label: ttk.Label, tree: ttk.Treeview):
        tree.delete(*tree.get_children())
        if loadout is None:
            summary_label.config(text="(no unit selected)")
            return

        summary_label.config(text=(
            f"{loadout.unit_name}\n"
            f"Tactical Health: {loadout.tactical_health:g}    Armor Type: {loadout.armor_type or '(none)'}\n"
            f"Shield Points: {loadout.shield_points:g}    Shield Armor Type: {loadout.shield_armor_type or '(none)'}\n"
            f"Shield Refresh Rate: {loadout.shield_refresh_rate:g}\n"
            f"Combined Hardpoint Health (targetable only): {loadout.combined_hardpoint_health:g}"
        ))

        for group in loadout.groups:
            if group.is_weapon and group.stats is not None:
                detail = f"{group.weapon_config.damage_type or '(none)'}, DPS avg {group.stats.dps_avg:g}"
            else:
                detail = f"Health {group.total_health:g} each"
            if not group.is_targetable:
                detail += " (not targetable)"
            tree.insert("", tk.END, text=group.label, values=(group.count, detail))

    def _on_battle_sim_changed(self):
        ally_name = self.battle_ally_var.get().strip()
        enemy_name = self.battle_enemy_var.get().strip()
        entries = self.combat_unit_load_result.entries

        self._battle_sim_ally_loadout = None
        self._battle_sim_enemy_loadout = None

        if ally_name in entries:
            try:
                self._battle_sim_ally_loadout = build_loadout(
                    ally_name, entries, self.hardpoint_load_result.entries, self.load_result.entries,
                )
            except InheritanceCycleError as exc:
                messagebox.showerror("Inheritance cycle", str(exc))
        elif ally_name:
            messagebox.showinfo("Ally not found", f"{ally_name!r} isn't among the currently loaded units.")

        if enemy_name in entries:
            try:
                self._battle_sim_enemy_loadout = build_loadout(
                    enemy_name, entries, self.hardpoint_load_result.entries, self.load_result.entries,
                )
            except InheritanceCycleError as exc:
                messagebox.showerror("Inheritance cycle", str(exc))
        elif enemy_name:
            messagebox.showinfo("Enemy not found", f"{enemy_name!r} isn't among the currently loaded units.")

        self._render_unit_loadout(self._battle_sim_ally_loadout, self.battle_ally_summary, self.battle_ally_tree)
        self._render_unit_loadout(self._battle_sim_enemy_loadout, self.battle_enemy_summary, self.battle_enemy_tree)
        self._render_battle_summary()

    def _render_battle_summary(self):
        self.battle_result_tree.delete(*self.battle_result_tree.get_children())
        ally = self._battle_sim_ally_loadout
        enemy = self._battle_sim_enemy_loadout

        if ally is None or enemy is None:
            self.battle_summary_label.config(text="Select an Ally and Enemy unit to simulate.")
            return

        result = simulate_battle(ally, enemy, self.damage_matrix, self.shield_recharge_interval_secs)

        for weapon in result.per_weapon:
            self.battle_result_tree.insert(
                "", tk.END, text=weapon.group.label,
                values=(weapon.group.count, f"{weapon.dps_vs_shield:g}", f"{weapon.dps_vs_hull:g}"),
            )

        model_regen = self.battle_model_regen_var.get()
        shield_strip = (
            result.shield_strip_seconds_with_regen if model_regen else result.shield_strip_seconds_no_regen
        )
        total_ttk = result.total_ttk_seconds_with_regen if model_regen else result.total_ttk_seconds_no_regen

        shield_strip_text = f"{shield_strip:g}s" if shield_strip is not None else "never strips (regen outpaces damage)"
        hull_text = f"{result.hull_kill_seconds:g}s" if result.hull_kill_seconds is not None else "never (no DPS vs hull)"
        ttk_text = f"{total_ttk:g}s" if total_ttk is not None else "never - shields never strip"

        self.battle_summary_label.config(text=(
            f"Total DPS vs Shield: {result.total_dps_vs_shield:g}    Total DPS vs Hull: {result.total_dps_vs_hull:g}\n"
            f"Enemy shield regen: {result.shield_regen_per_sec:g}/sec\n"
            f"Shield strip time: {shield_strip_text}    Hull kill time: {hull_text}\n"
            f"Predicted time to kill: {ttk_text}"
        ))


def main():
    root = tk.Tk()
    ProjectileViewerApp(root)
    root.mainloop()
