"""The "Hardpoint Configs" sub-tab of the Config tab: list, create, edit and
persist reusable HardpointConfigs (see hardpoint_config.py).

Kept out of ui.py (already very large) as a small class that borrows the
app's widget helpers - cards, scrollable panels, badges, and the shared
accuracy/modifier/category table builders - rather than re-implementing
them. The weapon block follows the same override model as the per-slot
Weapon Configs tab: a field the user edits is added to the embedded
WeaponConfig's `overridden_fields` (a "custom" badge) so re-applying the
linked Weapon Template never clobbers it; Reset returns a field - or, with
Reset All, every field - to the template's defaults.
"""

import copy
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .hardpoint_config import (
    HARDPOINT_TYPES, KIND_NON_WEAPON, KIND_WEAPON, HardpointConfig, order_projectile_choices,
    reset_weapon_to_template,
)
from .hardpoint_config_store import load_configs, save_configs
from .inheritance import InheritanceCycleError, merge_chain, resolve_chain
from .projectile_classification import build_children_map
from .ui_theme import icon_text
from .weapon_config import (
    CONTEXT_HARDPOINT, WeaponConfig, seed_from_projectile, to_float as weapon_config_to_float,
    to_int as weapon_config_to_int,
)
from .weapon_modifiers import modifiers_for_context
from .weapon_rules import RULE_FIELDS, apply_rule, rule_from_config, save_rules

FILTER_ALL = "(All)"
THEATRE_ANY = "Any"
THEATRES = ("Space", "Land")
NO_TEMPLATE = "(None)"

# (logical field name, label, weapon attribute, kind) for the override-tracked
# scalar rows of the weapon block. kind: "float" | "int" | "str".
WEAPON_SCALAR_FIELDS = (
    ("fire_range", "Weapon Range:", "fire_range", "float"),
    ("fire_cone_width", "Fire Cone Width:", "fire_cone_width", "float"),
    ("fire_cone_height", "Fire Cone Height:", "fire_cone_height", "float"),
    ("turret_rotate_speed", "Turret Rotate Speed:", "turret_rotate_speed", "float"),
    ("fire_min_recharge", "Min Recharge (s):", "fire_min_recharge", "float"),
    ("fire_max_recharge", "Max Recharge (s):", "fire_max_recharge", "float"),
    ("fire_pulse_count", "Pulse Count:", "fire_pulse_count", "int"),
    ("fire_pulse_delay", "Pulse Delay (s):", "fire_pulse_delay", "float"),
    ("sfx_event", "Fire SFX Event:", "sfx_event", "str"),
    ("damage", "Damage:", "damage", "float"),
    ("damage_type", "Damage Type:", "damage_type", "str"),
)
# Logical names of the non-scalar override-tracked parts of the weapon block,
# mapped to the WeaponConfig attribute holding them.
WEAPON_BLOCK_ATTRS = {
    "accuracy": "accuracy_by_category",
    "modifiers": "modifiers",
    "category_restrictions": "category_restrictions",
    "projectile": "source_projectile_name",
}


class HardpointConfigTab:
    def __init__(self, app, parent: ttk.Frame):
        self.app = app
        self.configs: dict[str, HardpointConfig] = {c.name: c for c in load_configs()}
        self.current_name: str | None = None
        self._suspend = False

        # Working copy of the weapon block's non-scalar parts + override state.
        self._accuracy: dict[str, float] = {}
        self._modifiers: dict[str, str] = {}
        self._restrictions: list[str] = []
        self._overridden: set[str] = set()
        self._override_notes: dict[str, str] = {}
        self._base_weapon = WeaponConfig(name="", context=CONTEXT_HARDPOINT)

        self._badges: dict[str, tk.Label] = {}
        self._category_combos: list[ttk.Combobox] = []

        self._build(parent)
        self.refresh_list()
        self._show_placeholder()

    # -- construction -----------------------------------------------------------------------------

    def _build(self, parent: ttk.Frame):
        app = self.app
        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Left: theatre filter + list + buttons
        left = ttk.Frame(main_pane, padding=(0, 0, 8, 0))
        main_pane.add(left, weight=1)

        filter_row = ttk.Frame(left)
        filter_row.pack(fill=tk.X)
        ttk.Label(filter_row, text="Theatre:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value=FILTER_ALL)
        filter_combo = ttk.Combobox(
            filter_row, textvariable=self.filter_var, state="readonly", width=8,
            values=[FILTER_ALL, *THEATRES],
        )
        filter_combo.pack(side=tk.LEFT, padx=(6, 0))
        filter_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_list())

        ttk.Label(left, text="Hardpoint Configs:").pack(anchor=tk.W, pady=(6, 0))
        list_frame = app._surface_frame(
            left, padding=4, place=lambda w: w.pack(fill=tk.BOTH, expand=True, pady=(4, 0)),
        )
        self.list_tree = ttk.Treeview(list_frame, show="tree")
        self.list_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.list_tree.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.list_tree.config(yscrollcommand=scroll.set)
        self.list_tree.bind("<<TreeviewSelect>>", self._on_select)

        button_row = ttk.Frame(left)
        button_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(button_row, text=icon_text("new", "New"), command=self._on_new).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Duplicate", command=self._on_duplicate).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(button_row, text=icon_text("delete", "Delete"), command=self._on_delete).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        # Right: scrollable editor
        right = app._surface_frame(
            main_pane, title="Hardpoint config", place=lambda w: main_pane.add(w, weight=3),
        )
        scroll_area = app._make_scrollable(right)

        self._build_identity_card(scroll_area)
        self._build_survivability_card(scroll_area)
        self._build_model_card(scroll_area)
        self._build_turret_card(scroll_area)
        self._build_weapon_card(scroll_area)

        ttk.Button(
            scroll_area, text=icon_text("save", "Save Hardpoint Config"), style="Accent.TButton",
            command=self._on_save,
        ).pack(anchor=tk.W, pady=(4, 8))

        self._update_visibility()

    def _entry_row(self, parent, row: int, label: str, var: tk.StringVar, width: int = 30, values=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=(4, 0))
        if values is None:
            widget = ttk.Entry(parent, textvariable=var, width=width)
        else:
            widget = ttk.Combobox(parent, textvariable=var, values=list(values), width=width)
        widget.grid(row=row, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0))
        return widget

    def _build_identity_card(self, parent):
        card = self.app._make_card(parent, title="Identity")
        self.name_var = tk.StringVar()
        self.kind_var = tk.StringVar(value="Weapon")
        self.type_var = tk.StringVar()
        self.tooltip_var = tk.StringVar()
        self.theatre_var = tk.StringVar(value=THEATRE_ANY)
        self.notes_var = tk.StringVar()

        self._entry_row(card, 0, "Name:", self.name_var, width=40)

        ttk.Label(card, text="Kind:").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
        kind_combo = ttk.Combobox(
            card, textvariable=self.kind_var, state="readonly", values=["Weapon", "Non-weapon"], width=14,
        )
        kind_combo.grid(row=1, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0))
        kind_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_visibility())

        self.type_combo = self._entry_row(card, 2, "Type:", self.type_var, width=38, values=HARDPOINT_TYPES)
        self._entry_row(card, 3, "Tooltip_Text:", self.tooltip_var, width=40)

        ttk.Label(card, text="Theatre:").grid(row=4, column=0, sticky=tk.W, pady=(4, 0))
        theatre_combo = ttk.Combobox(
            card, textvariable=self.theatre_var, state="readonly", values=[THEATRE_ANY, *THEATRES], width=10,
        )
        theatre_combo.grid(row=4, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0))
        theatre_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_choices())

        self._entry_row(card, 5, "Notes:", self.notes_var, width=60)

    def _build_survivability_card(self, parent):
        card = self.app._make_card(parent, title="Survivability")
        self.targetable_var = tk.BooleanVar()
        self.destroyable_var = tk.BooleanVar()
        self.health_var = tk.StringVar(value="1.0")
        self.death_particles_var = tk.StringVar()
        self.death_sfx_var = tk.StringVar()
        self.decal_var = tk.StringVar()
        self.damage_particles_var = tk.StringVar()

        flags = ttk.Frame(card)
        flags.grid(row=0, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(flags, text="Is_Targetable", variable=self.targetable_var).pack(side=tk.LEFT)
        ttk.Checkbutton(flags, text="Is_Destroyable", variable=self.destroyable_var).pack(side=tk.LEFT, padx=(12, 0))

        self._entry_row(card, 1, "Health:", self.health_var, width=12)
        self._entry_row(card, 2, "Death_Explosion_Particles:", self.death_particles_var, width=36)
        self._entry_row(card, 3, "Death_Explosion_SFXEvent:", self.death_sfx_var, width=36)
        self._entry_row(card, 4, "Damage_Decal:", self.decal_var, width=36)
        self._entry_row(card, 5, "Damage_Particles:", self.damage_particles_var, width=36)

    def _build_model_card(self, parent):
        card = self.app._make_card(parent, title="Model & Bones")
        self.model_var = tk.StringVar()
        self.fire_bone_a_var = tk.StringVar()
        self.fire_bone_b_var = tk.StringVar()
        self.attachment_bone_var = tk.StringVar()
        self.collision_mesh_var = tk.StringVar()

        self._entry_row(card, 0, "Model_To_Attach:", self.model_var, width=36)
        self._entry_row(card, 1, "Fire_Bone_A:", self.fire_bone_a_var, width=24)
        self._entry_row(card, 2, "Fire_Bone_B:", self.fire_bone_b_var, width=24)
        self._entry_row(card, 3, "Attachment_Bone:", self.attachment_bone_var, width=24)
        self._entry_row(card, 4, "Collision_Mesh:", self.collision_mesh_var, width=24)
        ttk.Label(
            card, style="Muted.TLabel", wraplength=460, justify=tk.LEFT,
            text=(
                "Model_To_Attach and the fire bones are fixed by the attached model. Attachment_Bone and "
                "Collision_Mesh are placement defaults - a unit sets its own when the config is placed."
            ),
        ).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

    def _build_turret_card(self, parent):
        self.turret_card_outer = ttk.Frame(parent)
        self.turret_card_outer.pack(fill=tk.X)
        card = self.app._make_card(
            self.turret_card_outer, title="Turret",
        )
        self.is_turret_var = tk.BooleanVar()
        self.turret_bone_var = tk.StringVar()
        self.barrel_bone_var = tk.StringVar()
        self.rest_angle_var = tk.StringVar()
        self.rotation_offset_var = tk.StringVar()
        self.rotate_extent_var = tk.StringVar(value="0.0")
        self.elevate_extent_var = tk.StringVar(value="0.0")

        ttk.Checkbutton(
            card, text="Is_Turret", variable=self.is_turret_var, command=self._update_visibility,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        self.turret_rows: list[tk.Widget] = []
        specs = (
            ("Turret_Bone_Name:", self.turret_bone_var), ("Barrel_Bone_Name:", self.barrel_bone_var),
            ("Turret_Rest_Angle:", self.rest_angle_var), ("Turret_Rotation_Offset:", self.rotation_offset_var),
            ("Turret_Rotate_Extent_Degrees:", self.rotate_extent_var),
            ("Turret_Elevate_Extent_Degrees:", self.elevate_extent_var),
        )
        for index, (label, var) in enumerate(specs, start=1):
            lbl = ttk.Label(card, text=label)
            lbl.grid(row=index, column=0, sticky=tk.W, pady=(4, 0))
            ent = ttk.Entry(card, textvariable=var, width=24)
            ent.grid(row=index, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0))
            self.turret_rows.extend([lbl, ent])
        ttk.Label(
            card, style="Muted.TLabel", wraplength=460, justify=tk.LEFT,
            text="Turret_Rotate_Speed is part of the weapon block below (it is a weapon-template field).",
        ).grid(row=len(specs) + 1, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

    def _build_weapon_card(self, parent):
        app = self.app
        # A permanent slot keeps the weapon block's position in the panel
        # when it's hidden/re-shown (re-packing would drop it below Save).
        self.weapon_slot = ttk.Frame(parent)
        self.weapon_slot.pack(fill=tk.X)
        self.weapon_outer = ttk.Frame(self.weapon_slot)
        self.weapon_outer.pack(fill=tk.X)
        card = app._make_card(self.weapon_outer, title="Weapon")

        # Template link
        link_row = ttk.Frame(card)
        link_row.grid(row=0, column=0, columnspan=4, sticky=tk.W)
        ttk.Label(link_row, text="Weapon Template:").pack(side=tk.LEFT)
        self.template_var = tk.StringVar(value=NO_TEMPLATE)
        self.template_combo = ttk.Combobox(
            link_row, textvariable=self.template_var, state="readonly", width=34, values=[NO_TEMPLATE],
        )
        self.template_combo.pack(side=tk.LEFT, padx=(6, 6))
        self.template_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_template_selected())
        ttk.Button(link_row, text="Apply", command=self._on_apply_template).pack(side=tk.LEFT)
        ttk.Button(
            link_row, text="Override Weapon Template", command=self._on_override_template,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            link_row, text=icon_text("reset", "Reset All to Template Defaults"), command=self._on_reset_all,
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Projectile (override-tracked as "projectile")
        row = 1
        ttk.Label(card, text="Projectile:").grid(row=row, column=0, sticky=tk.W, pady=(8, 0))
        self.projectile_var = tk.StringVar()
        self.projectile_combo = ttk.Combobox(card, textvariable=self.projectile_var, width=40)
        self.projectile_combo.grid(row=row, column=1, sticky=tk.W, padx=(6, 0), pady=(8, 0))
        self.projectile_var.trace_add("write", lambda *_: self._on_projectile_var_written())
        self._add_badge_and_reset(card, row, "projectile", pady=(8, 0))
        row += 1

        self.scalar_vars: dict[str, tk.StringVar] = {}
        for logical, label, _attr, _kind in WEAPON_SCALAR_FIELDS:
            ttk.Label(card, text=label).grid(row=row, column=0, sticky=tk.W, pady=(4, 0))
            var = tk.StringVar()
            self.scalar_vars[logical] = var
            var.trace_add("write", lambda *_, fn=logical: self._on_scalar_written(fn))
            ttk.Entry(card, textvariable=var, width=24).grid(
                row=row, column=1, sticky=tk.W, padx=(6, 0), pady=(4, 0)
            )
            self._add_badge_and_reset(card, row, logical, pady=(4, 0))
            row += 1

        # Accuracy / Modifiers / Restrictions share the app's table builders.
        start = len(app._category_name_combos)

        acc_card = app._make_card(self.weapon_outer, title="Accuracy by Category")
        self._add_block_header(acc_card, "accuracy")
        self._refresh_accuracy = app._build_accuracy_table(
            acc_card, tree_attr="hpc_accuracy_tree", category_var_attr="hpc_accuracy_category_var",
            category_combo_attr="hpc_accuracy_category_combo", value_var_attr="hpc_accuracy_value_var",
            get_dict=lambda: self._accuracy, on_change=lambda: self._mark_overridden("accuracy"),
        )

        mod_card = app._make_card(self.weapon_outer, title="Modifiers")
        self._add_block_header(mod_card, "modifiers")
        self._refresh_modifiers, _ = app._build_modifiers_table(
            mod_card, tree_attr="hpc_modifiers_tree", get_dict=lambda: self._modifiers,
            on_change=lambda: self._mark_overridden("modifiers"),
            get_specs=lambda: list(modifiers_for_context(CONTEXT_HARDPOINT)),
        )

        res_card = app._make_card(self.weapon_outer, title="Category Restrictions")
        self._add_block_header(res_card, "category_restrictions")
        self._refresh_restrictions = app._build_category_list_table(
            res_card, combo_attr="hpc_restriction_var", tree_attr="hpc_restrictions_tree",
            get_list=lambda: self._restrictions, on_change=lambda: self._mark_overridden("category_restrictions"),
        )

        # These combos are filtered by this config's theatre (see
        # refresh_choices), so keep the app's global refresh from resetting them.
        self._category_combos = app._category_name_combos[start:]
        del app._category_name_combos[start:]

    def _add_badge_and_reset(self, parent, row: int, logical: str, pady=(4, 0)):
        badge = self.app._make_badge(parent, "")
        badge.grid(row=row, column=2, sticky=tk.W, padx=(8, 0), pady=pady)
        badge.bind("<Double-Button-1>", lambda _e, fn=logical: self._on_edit_note(fn))
        self._badges[logical] = badge
        ttk.Button(
            parent, text=icon_text("reset", "Reset"), width=9, command=lambda fn=logical: self._on_reset_field(fn),
        ).grid(row=row, column=3, sticky=tk.W, padx=(4, 0), pady=pady)

    def _add_block_header(self, card, logical: str):
        header = ttk.Frame(card)
        header.pack(fill=tk.X, pady=(0, 4))
        badge = self.app._make_badge(header, "")
        badge.pack(side=tk.LEFT)
        badge.bind("<Double-Button-1>", lambda _e, fn=logical: self._on_edit_note(fn))
        self._badges[logical] = badge
        ttk.Button(
            header, text=icon_text("reset", "Reset"), command=lambda fn=logical: self._on_reset_field(fn),
        ).pack(side=tk.LEFT, padx=(6, 0))

    # -- list -------------------------------------------------------------------------------------

    def add_config(self, config: HardpointConfig):
        """Adds (or replaces) a config created elsewhere - e.g. from the
        Hardpoint Viewer - and persists it."""
        self.configs[config.name] = config
        save_configs(list(self.configs.values()))
        self.refresh_list()
        self._notify_changed()

    def _notify_changed(self):
        """Lets the Hardpoint Viewer re-group/re-compare after config edits."""
        viewer = getattr(self.app, "hardpoint_viewer_tab", None)
        if viewer is not None:
            viewer.refresh()

    def refresh_list(self):
        chosen = self.filter_var.get()
        self.list_tree.delete(*self.list_tree.get_children())
        for name in sorted(self.configs, key=str.lower):
            theatre = self.configs[name].theatre
            if chosen != FILTER_ALL and theatre not in ("", chosen):
                continue
            self.list_tree.insert("", tk.END, iid=name, text=name)

    def _on_select(self, _event):
        selection = self.list_tree.selection()
        if selection:
            self._display(selection[0])

    def _on_new(self):
        self.list_tree.selection_remove(*self.list_tree.selection())
        self._show_placeholder()

    def _show_placeholder(self):
        self.current_name = None
        chosen = self.filter_var.get() if hasattr(self, "filter_var") else FILTER_ALL
        config = HardpointConfig(name="", theatre=chosen if chosen in THEATRES else "")
        self._load(config)

    def _display(self, name: str):
        config = self.configs.get(name)
        if config is None:
            return
        self.current_name = name
        self._load(config)

    def _on_duplicate(self):
        if self.current_name is None or self.current_name not in self.configs:
            messagebox.showinfo("Nothing selected", "Select a hardpoint config to duplicate first.")
            return
        base = self.current_name
        new_name = f"{base} Copy"
        counter = 2
        while new_name in self.configs:
            new_name = f"{base} Copy {counter}"
            counter += 1
        clone = copy.deepcopy(self.configs[base])
        clone.name = new_name
        clone.weapon.name = new_name
        self.configs[new_name] = clone
        save_configs(list(self.configs.values()))
        self.refresh_list()
        self._notify_changed()
        if self.list_tree.exists(new_name):
            self.list_tree.selection_set(new_name)

    def _on_delete(self):
        name = self.current_name
        if name is None or name not in self.configs:
            return
        if not messagebox.askyesno("Delete Hardpoint Config", f"Delete the saved hardpoint config {name!r}?"):
            return
        del self.configs[name]
        save_configs(list(self.configs.values()))
        self.refresh_list()
        self._show_placeholder()
        self._notify_changed()

    def _on_save(self):
        config = self._read_form()
        if not config.name:
            messagebox.showwarning("Name required", "Give this hardpoint config a name before saving.")
            return
        previous = self.current_name
        if config.name != previous and config.name in self.configs:
            if not messagebox.askyesno(
                "Config exists", f"A hardpoint config named {config.name!r} already exists. Overwrite it?",
            ):
                return
        if previous is not None and previous != config.name:
            self.configs.pop(previous, None)

        self.configs[config.name] = config
        save_configs(list(self.configs.values()))
        self.current_name = config.name
        self.refresh_list()
        if self.list_tree.exists(config.name):
            self.list_tree.selection_set(config.name)
            self.list_tree.see(config.name)
        self._notify_changed()

    # -- form <-> model ---------------------------------------------------------------------------

    def _load(self, config: HardpointConfig):
        self._suspend = True
        try:
            self.name_var.set(config.name)
            self.kind_var.set("Weapon" if config.kind == KIND_WEAPON else "Non-weapon")
            self.type_var.set(config.hp_type)
            self.tooltip_var.set(config.tooltip_text)
            self.theatre_var.set(config.theatre or THEATRE_ANY)
            self.notes_var.set(config.notes)

            self.targetable_var.set(config.is_targetable)
            self.destroyable_var.set(config.is_destroyable)
            self.health_var.set(str(config.health))
            self.death_particles_var.set(config.death_explosion_particles)
            self.death_sfx_var.set(config.death_explosion_sfx)
            self.decal_var.set(config.damage_decal)
            self.damage_particles_var.set(config.damage_particles)

            self.model_var.set(config.model_to_attach)
            self.fire_bone_a_var.set(config.fire_bone_a)
            self.fire_bone_b_var.set(config.fire_bone_b)
            self.attachment_bone_var.set(config.attachment_bone)
            self.collision_mesh_var.set(config.collision_mesh)

            self.is_turret_var.set(config.is_turret)
            self.turret_bone_var.set(config.turret_bone_name)
            self.barrel_bone_var.set(config.barrel_bone_name)
            self.rest_angle_var.set(config.turret_rest_angle)
            self.rotation_offset_var.set(config.turret_rotation_offset)
            self.rotate_extent_var.set(str(config.turret_rotate_extent_degrees))
            self.elevate_extent_var.set(str(config.turret_elevate_extent_degrees))

            weapon = config.weapon
            self._base_weapon = copy.deepcopy(weapon)
            self._accuracy = dict(weapon.accuracy_by_category)
            self._modifiers = dict(weapon.modifiers)
            self._restrictions = list(weapon.category_restrictions)
            self._overridden = set(weapon.overridden_fields)
            self._override_notes = dict(weapon.override_notes)

            self.template_var.set(config.weapon_template or NO_TEMPLATE)
            self.refresh_choices()
            self.projectile_var.set(weapon.source_projectile_name)
            for logical, _label, attr, kind in WEAPON_SCALAR_FIELDS:
                value = getattr(weapon, attr)
                self.scalar_vars[logical].set("" if value is None else str(value))
        finally:
            self._suspend = False

        self._refresh_accuracy()
        self._refresh_modifiers()
        self._refresh_restrictions()
        self._update_visibility()
        self._update_badges()

    def _read_form(self) -> HardpointConfig:
        kind = KIND_WEAPON if self.kind_var.get() == "Weapon" else KIND_NON_WEAPON
        theatre = self.theatre_var.get()
        template = self.template_var.get()
        name = self.name_var.get().strip()

        weapon = copy.deepcopy(self._base_weapon)
        weapon.name = name
        weapon.context = CONTEXT_HARDPOINT
        weapon.category = "" if template == NO_TEMPLATE else template
        weapon.source_projectile_name = self.projectile_var.get().strip()
        for logical, _label, attr, kind_name in WEAPON_SCALAR_FIELDS:
            text = self.scalar_vars[logical].get()
            if kind_name == "float":
                value = weapon_config_to_float(text)
            elif kind_name == "int":
                value = weapon_config_to_int(text)
            else:
                value = text.strip()
            setattr(weapon, attr, value)
        weapon.accuracy_by_category = dict(self._accuracy)
        weapon.modifiers = dict(self._modifiers)
        weapon.category_restrictions = list(self._restrictions)
        weapon.overridden_fields = set(self._overridden)
        weapon.override_notes = dict(self._override_notes)

        return HardpointConfig(
            name=name, kind=kind, hp_type=self.type_var.get().strip(),
            tooltip_text=self.tooltip_var.get().strip(),
            notes=self.notes_var.get().strip(),
            theatre=theatre if theatre in THEATRES else "",
            is_targetable=bool(self.targetable_var.get()),
            is_destroyable=bool(self.destroyable_var.get()),
            health=weapon_config_to_float(self.health_var.get(), 1.0),
            death_explosion_particles=self.death_particles_var.get().strip(),
            death_explosion_sfx=self.death_sfx_var.get().strip(),
            damage_decal=self.decal_var.get().strip(),
            damage_particles=self.damage_particles_var.get().strip(),
            model_to_attach=self.model_var.get().strip(),
            fire_bone_a=self.fire_bone_a_var.get().strip(),
            fire_bone_b=self.fire_bone_b_var.get().strip(),
            is_turret=bool(self.is_turret_var.get()),
            turret_bone_name=self.turret_bone_var.get().strip(),
            barrel_bone_name=self.barrel_bone_var.get().strip(),
            turret_rest_angle=self.rest_angle_var.get().strip(),
            turret_rotation_offset=self.rotation_offset_var.get().strip(),
            turret_rotate_extent_degrees=weapon_config_to_float(self.rotate_extent_var.get()),
            turret_elevate_extent_degrees=weapon_config_to_float(self.elevate_extent_var.get()),
            attachment_bone=self.attachment_bone_var.get().strip(),
            collision_mesh=self.collision_mesh_var.get().strip(),
            weapon_template="" if template == NO_TEMPLATE else template,
            weapon=weapon,
        )

    def _update_visibility(self):
        is_weapon = self.kind_var.get() == "Weapon"
        if is_weapon:
            self.weapon_outer.pack(fill=tk.X)
        else:
            self.weapon_outer.pack_forget()

        state = tk.NORMAL if self.is_turret_var.get() else tk.DISABLED
        for widget in self.turret_rows:
            if isinstance(widget, ttk.Entry):
                widget.config(state=state)

    # -- choices ----------------------------------------------------------------------------------

    def _rule(self):
        name = self.template_var.get()
        return None if name == NO_TEMPLATE else self.app.weapon_rules.get(name)

    def refresh_choices(self):
        """Repopulates the template, projectile and category dropdowns -
        called on load, after a template/project/mask change, and when this
        config's theatre changes."""
        app = self.app
        theatre = self.theatre_var.get()
        theatre = theatre if theatre in THEATRES else ""

        templates = [
            name for name, rule in sorted(app.weapon_rules.items(), key=lambda kv: kv[0].lower())
            if theatre == "" or rule.theatre in ("", theatre)
        ]
        current = self.template_var.get()
        if current != NO_TEMPLATE and current not in templates:
            templates.append(current)  # keep a link to a template that's been filtered/removed visible
        self.template_combo.config(values=[NO_TEMPLATE, *templates])

        rule = self._rule()
        default_projectile = rule.default_projectile if rule is not None else ""
        names = list(app.load_result.entries)
        ordered = order_projectile_choices(
            names, build_children_map(app.load_result.entries) if names else {}, default_projectile,
        )
        self._ordered_projectiles = ordered
        longest = max((len(n) for n in ordered), default=0)
        self.projectile_combo.config(width=max(longest + 2, 25))
        app._filter_search_combo(self.projectile_combo, ordered, self.projectile_var)

        category_names = app._category_names_for_theatre(theatre or None)
        for combo in self._category_combos:
            combo.config(values=category_names)

    def _on_projectile_var_written(self):
        if hasattr(self, "_ordered_projectiles"):
            self.app._filter_search_combo(self.projectile_combo, self._ordered_projectiles, self.projectile_var)
        if self._suspend:
            return
        self._mark_overridden("projectile")
        self._reseed_damage()

    def _on_template_selected(self):
        # Selecting only links the template; Apply (or Reset All) pulls its values.
        self.refresh_choices()
        self._update_badges()

    # -- weapon-block behaviour ---------------------------------------------------------------------

    def _projectile_fields(self, name: str):
        entries = self.app.load_result.entries
        if not name or name not in entries:
            return None
        try:
            return merge_chain(entries, resolve_chain(entries, name))
        except InheritanceCycleError:
            return None

    def _on_scalar_written(self, logical: str):
        if self._suspend:
            return
        self._mark_overridden(logical)

    def _mark_overridden(self, logical: str):
        if self._suspend:
            return
        self._overridden.add(logical)
        self._update_badges()

    def _reseed_damage(self):
        """After the projectile changes, re-read damage/damage_type from it
        unless the user has overridden those."""
        fields = self._projectile_fields(self.projectile_var.get().strip())
        if fields is None:
            return
        temp = WeaponConfig(name="", overridden_fields={f for f in ("damage", "damage_type") if f in self._overridden})
        temp.damage = weapon_config_to_float(self.scalar_vars["damage"].get())
        temp.damage_type = self.scalar_vars["damage_type"].get().strip()
        seed_from_projectile(temp, fields)
        self._suspend = True
        try:
            self.scalar_vars["damage"].set(str(temp.damage))
            self.scalar_vars["damage_type"].set(temp.damage_type)
        finally:
            self._suspend = False

    def _on_apply_template(self):
        rule = self._rule()
        if rule is None:
            messagebox.showinfo("No template", "Choose a Weapon Template to apply first.")
            return
        config = self._read_form()
        apply_rule(config.weapon, rule)
        self._base_weapon = config.weapon
        # Re-seed damage from the (possibly changed) projectile, honouring overrides.
        fields = self._projectile_fields(config.weapon.source_projectile_name)
        if fields is not None:
            seed_from_projectile(config.weapon, fields)
        self._load(config)

    def _on_override_template(self):
        """Writes this config's current weapon values back into the linked
        Weapon Template (the reverse of Apply). The template's category and
        theatre are kept; its default projectile only changes when this
        config's projectile is overridden. Afterwards the config's overrides
        are cleared - its values now *are* the template's."""
        app = self.app
        rule = self._rule()
        if rule is None:
            messagebox.showinfo("No template", "Choose a Weapon Template to override first.")
            return

        config = self._read_form()
        weapon = config.weapon
        new_rule = rule_from_config(weapon, rule.category, theatre=rule.theatre)
        new_rule.default_projectile = (
            weapon.source_projectile_name if "projectile" in weapon.overridden_fields else rule.default_projectile
        )

        labels = {
            "accuracy_by_category": "accuracy", "fire_min_recharge": "min recharge", "fire_max_recharge": "max recharge",
            "fire_pulse_count": "pulse count", "fire_pulse_delay": "pulse delay", "sfx_event": "fire SFX",
            "modifiers": "modifiers", "category_restrictions": "category restrictions", "fire_range": "range",
            "fire_cone_width": "cone width", "fire_cone_height": "cone height",
            "turret_rotate_speed": "turret rotate speed", "default_projectile": "default projectile",
        }
        changed = [text for attr, text in labels.items() if getattr(new_rule, attr) != getattr(rule, attr)]
        if not changed:
            messagebox.showinfo("Nothing to override", f"This config already matches {rule.category!r}.")
            return

        if not messagebox.askyesno(
            "Override Weapon Template",
            f"Overwrite the Weapon Template {rule.category!r} with this config's values?\n\n"
            f"Changes: {', '.join(changed)}.\n\n"
            "Every config that re-applies this template will pick these up.",
        ):
            return

        app.weapon_rules[rule.category] = new_rule
        save_rules(list(app.weapon_rules.values()))
        app._refresh_weapon_rules_list()

        # The config now matches its template exactly, so its overrides are moot.
        weapon.overridden_fields.clear()
        weapon.override_notes.clear()
        self._base_weapon = weapon
        self._load(config)

    def _on_reset_all(self):
        config = self._read_form()
        rule = self._rule()
        if rule is None and config.weapon_template:
            messagebox.showinfo("Template not found", f"No saved Weapon Template named {config.weapon_template!r}.")
            return
        reset_weapon_to_template(config, rule, self._projectile_fields)
        self._load(config)

    def _on_reset_field(self, logical: str):
        config = self._read_form()
        weapon = config.weapon
        weapon.overridden_fields.discard(logical)
        weapon.override_notes.pop(logical, None)

        rule = self._rule()
        fresh = WeaponConfig(name="", context=CONTEXT_HARDPOINT)
        if rule is not None:
            apply_rule(fresh, rule)

        attr = WEAPON_BLOCK_ATTRS.get(logical, logical)
        if logical in ("damage", "damage_type"):
            fields = self._projectile_fields(weapon.source_projectile_name)
            temp = WeaponConfig(name="")
            if fields is not None:
                seed_from_projectile(temp, fields)
            setattr(weapon, attr, getattr(temp, attr))
        else:
            setattr(weapon, attr, copy.copy(getattr(fresh, attr)))
            if logical == "projectile":
                fields = self._projectile_fields(weapon.source_projectile_name)
                if fields is not None:
                    seed_from_projectile(weapon, fields)

        self._base_weapon = weapon
        self._load(config)

    def _on_edit_note(self, logical: str):
        if logical not in self._overridden:
            messagebox.showinfo("Not overridden", "Only an overridden (custom) field can have a note.")
            return
        current = self._override_notes.get(logical, "")
        note = simpledialog.askstring(
            "Override note", f"Why was {logical!r} overridden?", initialvalue=current, parent=self.app.root,
        )
        if note is None:
            return
        if note.strip():
            self._override_notes[logical] = note.strip()
        else:
            self._override_notes.pop(logical, None)

    def _update_badges(self):
        template = self.template_var.get()
        for logical, badge in self._badges.items():
            if logical in self._overridden:
                text, kind = "custom", "warning"
            elif template != NO_TEMPLATE and (
                logical in RULE_FIELDS or logical in ("accuracy", "modifiers", "category_restrictions", "projectile")
            ):
                text, kind = f"rule: {template}", "link"
            else:
                text, kind = "default", "neutral"
            badge.config(text=text)
            self.app._set_badge_kind(badge, kind)
