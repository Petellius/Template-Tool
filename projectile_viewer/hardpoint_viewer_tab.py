"""The "Hardpoint Viewer" sub-tab of the Config tab: pick a unit, see every
hardpoint it uses grouped by assigned Hardpoint Config (else by similarity),
turn a group into a Hardpoint Config and/or Weapon Template, assign existing
configs, and see where the unit's real hardpoint XML has drifted from the
config it's assigned to.

The grouping/comparison logic lives in hardpoint_view.py; this module is the
widget layer. Every action persists immediately (configs, templates and
per-unit assignments), so there is no separate save step to forget.
"""

import tkinter as tk
from dataclasses import replace
from tkinter import messagebox, simpledialog, ttk

from .hardpoint_assignments import load_assignments, save_assignments
from .hardpoint_config import KIND_NON_WEAPON, KIND_WEAPON
from .hardpoint_overrides import load_overrides, save_overrides
from .hardpoint_field_groups import group_fields
from .hardpoint_view import (
    UnitHardpoint, ViewGroup, _norm, apply_overrides, compare_with_overrides, config_from_hardpoint,
    group_hardpoints, read_unit_hardpoints, summarize_fields,
)
from .unit_picker import UnitPicker
from .ui_theme import icon_text
from .weapon_rules import rule_from_config, save_rules

KIND_LABELS = {KIND_WEAPON: "Weapon", KIND_NON_WEAPON: "Non-weapon"}
STATUS_OK = "OK"
NL = chr(10)
# Orange warning marker for hardpoints that differ from their assigned config.
WARN_ICON = "⚠"
WARN_TAG = "differs"
WARN_COLOR = "#f08c00"
# Fields the user has overridden on top of the template/XML data.
CUSTOM_TAG = "custom"
CUSTOM_COLOR = "#3b8fe0"


class HardpointViewerTab:
    def __init__(self, app, parent: ttk.Frame):
        self.app = app
        self.assignments = load_assignments()
        self.overrides = load_overrides()
        self._data_rows: dict[str, tuple] = {}
        self._cell_editor: ttk.Entry | None = None
        self.unit_name: str | None = None
        self.hardpoints: list[UnitHardpoint] = []
        self.missing: list[str] = []
        self.groups: list[ViewGroup] = []
        self._by_iid: dict[str, tuple[str, object]] = {}

        self.picker = UnitPicker(app, parent, self.show_unit, autosize=self._autosize)
        self._build(parent)

    def _autosize(self, combo):
        from .ui import _autosize_combobox_popdown  # local: ui imports this module at import time
        _autosize_combobox_popdown(combo)

    # -- construction -----------------------------------------------------------------------------

    def _build(self, parent: ttk.Frame):
        self.banner = ttk.Label(parent, text="Pick a unit to see its hardpoints.", style="Muted.TLabel")
        self.banner.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))

        pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(pane, padding=(0, 0, 8, 0))
        pane.add(left, weight=3)
        columns = ("type", "kind", "config", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="Hardpoint / group")
        self.tree.heading("type", text="Type")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("config", text="Hardpoint Config")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=300, anchor=tk.W)
        self.tree.column("type", width=210, anchor=tk.W)
        self.tree.column("kind", width=90, anchor=tk.W)
        self.tree.column("config", width=170, anchor=tk.W)
        self.tree.column("status", width=90, anchor=tk.W)
        vsb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure(WARN_TAG, foreground=WARN_COLOR)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        right = ttk.Frame(pane, padding=(8, 0, 0, 0))
        pane.add(right, weight=2)

        self.detail_label = ttk.Label(right, text="Select a group or hardpoint.", style="CardTitle.TLabel",
                                      wraplength=420, justify=tk.LEFT)
        self.detail_label.pack(anchor=tk.W)

        actions = ttk.Frame(right)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            actions, text=icon_text("new", "Create Hardpoint Config..."), command=self._on_create_config,
        ).grid(row=0, column=0, sticky=tk.EW, pady=2)
        ttk.Button(
            actions, text=icon_text("weapon_rules", "Create Weapon Template..."), command=self._on_create_template,
        ).grid(row=1, column=0, sticky=tk.EW, pady=2)
        ttk.Button(
            actions, text="Create Both...", command=self._on_create_both,
        ).grid(row=2, column=0, sticky=tk.EW, pady=2)
        ttk.Button(
            actions, text="Assign Existing Config...", command=self._on_assign_existing,
        ).grid(row=0, column=1, sticky=tk.EW, padx=(6, 0), pady=2)
        ttk.Button(
            actions, text="Unassign", command=self._on_unassign,
        ).grid(row=1, column=1, sticky=tk.EW, padx=(6, 0), pady=2)
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        self.status_label = ttk.Label(right, text="", style="Muted.TLabel", wraplength=420, justify=tk.LEFT)
        self.status_label.pack(anchor=tk.W, pady=(6, 0))

        self.data_label = ttk.Label(right, text="Hardpoint data:", style="CardTitle.TLabel")
        self.data_label.pack(anchor=tk.W, pady=(10, 0))
        data_frame = ttk.Frame(right)
        data_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self.data_tree = ttk.Treeview(
            data_frame, columns=("value", "state"), show="tree headings", selectmode="extended",
        )
        self.data_tree.heading("#0", text="Field")
        self.data_tree.heading("value", text="Value (double-click to edit)")
        self.data_tree.heading("state", text="State")
        self.data_tree.column("#0", width=210, anchor=tk.W)
        self.data_tree.column("value", width=240, anchor=tk.W)
        self.data_tree.column("state", width=80, anchor=tk.W)
        self.data_tree.bind("<Double-1>", self._on_data_double_click)
        data_vsb = ttk.Scrollbar(data_frame, orient=tk.VERTICAL, command=self.data_tree.yview)
        data_hsb = ttk.Scrollbar(data_frame, orient=tk.HORIZONTAL, command=self.data_tree.xview)
        self.data_tree.configure(yscrollcommand=data_vsb.set, xscrollcommand=data_hsb.set)
        self.data_tree.grid(row=0, column=0, sticky=tk.NSEW)
        data_vsb.grid(row=0, column=1, sticky=tk.NS)
        data_hsb.grid(row=1, column=0, sticky=tk.EW)
        data_frame.rowconfigure(0, weight=1)
        data_frame.columnconfigure(0, weight=1)
        self.data_tree.tag_configure("varies", foreground=WARN_COLOR)
        self.data_tree.tag_configure(CUSTOM_TAG, foreground=CUSTOM_COLOR)

        data_buttons = ttk.Frame(right)
        data_buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(data_buttons, text="Add Field...", command=self._on_add_field).pack(side=tk.LEFT)
        ttk.Button(
            data_buttons, text="Reset Override", command=self._on_reset_override,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            data_buttons, text="Reset All Overrides", command=self._on_reset_all_overrides,
        ).pack(side=tk.LEFT, padx=(6, 0))

    # -- public hooks -----------------------------------------------------------------------------

    def refresh(self):
        """Called when units/projectiles/configs change: refreshes the picker
        and re-reads the shown unit so groups and warnings stay current."""
        self.picker.refresh()
        if self.unit_name is not None:
            if self.unit_name in self.app.combat_unit_load_result.entries:
                self.show_unit(self.unit_name)
            else:
                self.unit_name = None
                self._clear()

    def show_unit(self, name: str):
        self.unit_name = name
        app = self.app
        unit_entries = app.wc_inheritance_entries or app.combat_unit_load_result.entries
        self.hardpoints, self.missing = read_unit_hardpoints(name, unit_entries, app.hardpoint_load_result.entries)
        self._regroup()

    # -- rendering --------------------------------------------------------------------------------

    def _clear(self):
        self.hardpoints, self.missing, self.groups = [], [], []
        self.tree.delete(*self.tree.get_children())
        self._render_data([])
        self._by_iid.clear()
        self.banner.config(text="Pick a unit to see its hardpoints.")
        self.detail_label.config(text="Select a group or hardpoint.")

    def _unit_assignments(self) -> dict[str, str]:
        return self.assignments.get(self.unit_name or "", {})

    def _regroup(self):
        configs = self.app.hardpoint_config_tab.configs
        self.groups = group_hardpoints(self.hardpoints, self._unit_assignments(), configs)

        self.tree.delete(*self.tree.get_children())
        self._by_iid.clear()
        total_warnings = 0
        for index, group in enumerate(self.groups):
            warnings = self._group_mismatches(group)
            total_warnings += len(warnings)
            iid = f"g{index}"
            self._by_iid[iid] = ("group", group)
            first = group.members[0]
            status = self._group_status(group, warnings)
            self.tree.insert(
                "", tk.END, iid=iid, open=group.count <= 1,
                text=f"{group.label}  x{group.count}" if group.count > 1 else group.label,
                values=(
                    first.fields.get("Type", [""])[0], KIND_LABELS[group.kind], group.config_name, status,
                ),
                tags=(WARN_TAG,) if warnings else (),
            )
            for member in group.members:
                member_iid = f"h:{member.name}"
                self._by_iid[member_iid] = ("hardpoint", member)
                member_warnings = self._hardpoint_mismatches(member, group.config_name)
                # Each child shows its own assignment and status, so a
                # group-level assign/unassign is visibly applied to every child.
                if group.config_name and self._config_for(group.config_name) is None:
                    member_status = "config missing"
                elif member_warnings:
                    member_status = WARN_ICON
                else:
                    member_status = STATUS_OK if group.config_name else "-"
                self.tree.insert(
                    iid, tk.END, iid=member_iid, text=member.name,
                    values=(
                        member.fields.get("Type", [""])[0], KIND_LABELS[member.kind], group.config_name,
                        member_status,
                    ),
                    tags=(WARN_TAG,) if member_warnings else (),
                )

        assigned = sum(1 for g in self.groups if g.config_name)
        text = f"{self.unit_name}: {len(self.hardpoints)} hardpoint(s) in {len(self.groups)} group(s)"
        if assigned:
            text += f", {assigned} assigned to a config"
        if total_warnings:
            text += f" - {total_warnings} difference(s) from assigned configs (marked with a warning)"
        if self.missing:
            text += f" - {len(self.missing)} referenced but not defined: {', '.join(self.missing[:6])}"
            if len(self.missing) > 6:
                text += ", ..."
        self.banner.config(text=text)
        self._on_select()

    def _config_for(self, name: str):
        return self.app.hardpoint_config_tab.configs.get(name) if name else None

    def _unit_overrides(self) -> dict[str, dict[str, list[str]]]:
        return self.overrides.get(self.unit_name or "", {})

    def _hardpoint_mismatches(self, hardpoint: UnitHardpoint, config_name: str):
        """Where this hardpoint's XML differs from its template data
        (assigned config + the user's overrides on top)."""
        config = self._config_for(config_name)
        return compare_with_overrides(hardpoint.fields, config, self._unit_overrides().get(hardpoint.name))

    def _group_mismatches(self, group: ViewGroup):
        return [m for member in group.members for m in self._hardpoint_mismatches(member, group.config_name)]

    def _group_status(self, group: ViewGroup, warnings) -> str:
        if group.config_name and self._config_for(group.config_name) is None:
            return "config missing"
        if warnings:
            return WARN_ICON
        return STATUS_OK if group.config_name else "-"

    # -- selection --------------------------------------------------------------------------------

    def _selected_members(self) -> tuple[list[UnitHardpoint], ViewGroup | None]:
        """Every hardpoint in the selection (groups contribute all their
        members; shift/ctrl-click can select several groups and/or single
        hardpoints), de-duplicated and in unit order. The returned group is
        only set when the selection is exactly one group or one hardpoint."""
        selection = self.tree.selection()
        members: dict[str, UnitHardpoint] = {}
        single_group: ViewGroup | None = None
        for iid in selection:
            kind, obj = self._by_iid.get(iid, (None, None))
            if kind == "group":
                for member in obj.members:
                    members[member.name] = member
                single_group = obj
            elif kind == "hardpoint":
                members[obj.name] = obj
                single_group = self._by_iid.get(self.tree.parent(iid), (None, None))[1]
        ordered = sorted(members.values(), key=lambda m: m.order)
        return ordered, (single_group if len(selection) == 1 else None)

    def _on_select(self):
        members, group = self._selected_members()
        self._render_data(members)
        if not members:
            self.detail_label.config(text="Select a group or hardpoint (shift/ctrl-click for several).")
            return

        assigned = self._unit_assignments()
        configs_used = {assigned.get(m.name, "") for m in members}

        if group is not None and len(self.tree.selection()) == 1 and self._by_iid.get(
            self.tree.selection()[0], (None, None)
        )[0] == "group":
            title = f"{group.label} - {len(members)} hardpoint(s)"
        elif len(members) == 1:
            title = members[0].name
        else:
            title = f"{len(members)} hardpoints selected"

        if len(configs_used) > 1:
            names = ", ".join(sorted(c or "none" for c in configs_used))
            title += NL + "Assigned to: (mixed - " + names + ")"
        else:
            config_name = next(iter(configs_used))
            if config_name:
                exists = self._config_for(config_name) is not None
                title += NL + "Assigned to: " + config_name + ("" if exists else " (config no longer exists)")
            else:
                title += NL + "Not assigned to a Hardpoint Config"

        scope = (
            f"Assign / Unassign applies to all {len(members)} selected hardpoints."
            if len(members) > 1 else "Assign / Unassign applies to this hardpoint only."
        )
        self.detail_label.config(text=title + NL + scope)

    def _effective_members(self, members: list[UnitHardpoint]) -> list[UnitHardpoint]:
        """The selected hardpoints with the user's overrides laid on top."""
        overrides = self._unit_overrides()
        return [replace(m, fields=apply_overrides(m.fields, overrides.get(m.name))) for m in members]

    def _override_state(self, members: list[UnitHardpoint], tag: str) -> str:
        overrides = self._unit_overrides()
        count = sum(1 for m in members if tag in overrides.get(m.name, {}))
        if count == 0:
            return ""
        return "custom" if count == len(members) else f"custom ({count}/{len(members)})"

    def _render_data(self, members: list[UnitHardpoint]):
        """Full, editable data view for the selection: every field of a
        single hardpoint, or - for a group / several hardpoints - the fields
        they share, plus a section listing where they differ. Values shown
        are the hardpoint's XML data with any user overrides applied; an
        overridden field is marked "custom"."""
        tree = self.data_tree
        self._end_cell_edit()
        tree.delete(*tree.get_children())
        self._data_rows.clear()
        if not members:
            self.data_label.config(text="Hardpoint data:")
            return

        data = summarize_fields(self._effective_members(members))
        if data.count == 1:
            self.data_label.config(text=f"Hardpoint data - {members[0].name}")
        else:
            self.data_label.config(text=f"Shared data - {data.count} hardpoints")

        def add_row(parent, text, value, state, info, extra_tags=()):
            tags = tuple(extra_tags) + ((CUSTOM_TAG,) if state else ())
            iid = tree.insert(parent, tk.END, text=text, values=(value, state), tags=tags)
            self._data_rows[iid] = info
            return iid

        for group_name, tags in group_fields(data.shared):
            parent = tree.insert("", tk.END, text=group_name, open=True)
            for tag in tags:
                values = data.shared[tag]
                state = self._override_state(members, tag)
                if len(values) <= 1:
                    add_row(parent, tag, values[0] if values else "", state, ("shared", tag, 0))
                else:
                    # A repeated tag (e.g. one Fire_Inaccuracy_Distance per category).
                    for index, value in enumerate(values):
                        add_row(parent, f"{tag} ({index + 1})", value, state, ("shared", tag, index))

        if data.varying:
            parent = tree.insert(
                "", tk.END, text=f"Differs between hardpoints ({len(data.varying)})", open=True, tags=("varies",),
            )
            for tag in sorted(data.varying):
                variations = data.varying[tag]
                state = self._override_state(members, tag)
                node = add_row(
                    parent, tag, f"{len(variations)} different values", state, ("varying", tag, 0), ("varies",),
                )
                for variation in variations:
                    shown = " | ".join(variation.values) if variation.values else "(not set)"
                    names = ", ".join(n.rsplit("_", 1)[-1] for n in variation.members[:6])
                    if len(variation.members) > 6:
                        names += f", +{len(variation.members) - 6} more"
                    child = tree.insert(node, tk.END, text=shown, values=(f"x{len(variation.members)}: {names}", ""))
                    self._data_rows[child] = ("varying-child", tag, 0)

    # -- editing the hardpoint data ---------------------------------------------------------------

    def _end_cell_edit(self):
        if self._cell_editor is not None:
            try:
                self._cell_editor.destroy()
            except tk.TclError:
                pass
            self._cell_editor = None

    def _on_data_double_click(self, event):
        tree = self.data_tree
        if tree.identify_region(event.x, event.y) != "cell" or tree.identify_column(event.x) != "#1":
            return
        row = tree.identify_row(event.y)
        info = self._data_rows.get(row)
        if info is None:
            return
        kind, tag, index = info
        if kind == "varying-child":
            return

        bbox = tree.bbox(row, "#1")
        if not bbox:
            return
        members, _group = self._selected_members()
        if not members:
            return
        self._end_cell_edit()

        current = tree.set(row, "value") if kind == "shared" else ""
        x, y, width, height = bbox
        editor = ttk.Entry(tree)
        editor.insert(0, current)
        editor.select_range(0, tk.END)
        editor.place(x=x, y=y, width=max(width, 220), height=height)
        editor.focus_set()
        self._cell_editor = editor

        def commit(_event=None):
            if self._cell_editor is not editor:
                return
            text = editor.get()
            self._end_cell_edit()
            self._commit_edit(info, text)

        def cancel(_event=None):
            if self._cell_editor is editor:
                self._end_cell_edit()

        editor.bind("<Return>", commit)
        editor.bind("<FocusOut>", commit)
        editor.bind("<Escape>", cancel)

    def _set_override(self, member: UnitHardpoint, tag: str, values: list[str] | None):
        """Sets (or, with None / values equal to the XML's own, removes) one
        override. An empty list is a real override that clears the tag."""
        per_unit = self.overrides.setdefault(self.unit_name, {})
        tags = per_unit.setdefault(member.name, {})
        if values is None or [_norm(v) for v in values] == [_norm(v) for v in member.fields.get(tag, [])]:
            tags.pop(tag, None)
        else:
            tags[tag] = list(values)
        if not tags:
            per_unit.pop(member.name, None)

    def _after_override_change(self):
        save_overrides(self.overrides)
        selected = list(self.tree.selection())
        self._regroup()
        existing = [iid for iid in selected if self.tree.exists(iid)]
        if existing:
            self.tree.selection_set(*existing)
        self._render_data(self._selected_members()[0])

    def _commit_edit(self, info: tuple, text: str):
        kind, tag, index = info
        members, _group = self._selected_members()
        if not members:
            return
        text = text.strip()

        if kind == "shared":
            effective = self._effective_members(members)[0].fields.get(tag, [])
            values = list(effective)
            if text == "" and len(values) <= 1:
                values = []
            elif index < len(values):
                values[index] = text
            else:
                values.append(text)
        else:  # "varying": one new value for every selected hardpoint
            values = [text] if text != "" else []

        for member in members:
            self._set_override(member, tag, values)
        self._after_override_change()
        self.status_label.config(text=f"Override on {tag} applied to {len(members)} hardpoint(s). Saved.")

    def _on_add_field(self):
        members = self._require_members()
        if members is None:
            return
        tag = simpledialog.askstring(
            "Add field", "XML tag to add (e.g. Fire_Cone_Width):", parent=self.app.root,
        )
        if not tag or not tag.strip():
            return
        tag = tag.strip()
        if not tag.replace("_", "").isalnum():
            messagebox.showinfo("Invalid tag", "Tag names may only contain letters, digits and underscores.")
            return
        value = simpledialog.askstring("Add field", f"Value for {tag}:", parent=self.app.root)
        if value is None:
            return
        for member in members:
            self._set_override(member, tag, [value.strip()])
        self._after_override_change()
        self.status_label.config(text=f"Added {tag} to {len(members)} hardpoint(s) as an override. Saved.")

    def _selected_data_tags(self) -> list[str]:
        tags = []
        for iid in self.data_tree.selection():
            info = self._data_rows.get(iid)
            if info is not None and info[1] not in tags:
                tags.append(info[1])
        return tags

    def _on_reset_override(self):
        members = self._require_members()
        if members is None:
            return
        tags = self._selected_data_tags()
        if not tags:
            messagebox.showinfo("Nothing selected", "Select one or more fields in the data panel first.")
            return
        for member in members:
            for tag in tags:
                self._set_override(member, tag, None)
        self._after_override_change()
        self.status_label.config(text=f"Reset {len(tags)} field(s) to their template/XML values.")

    def _on_reset_all_overrides(self):
        members = self._require_members()
        if members is None:
            return
        per_unit = self.overrides.get(self.unit_name, {})
        if not any(m.name in per_unit for m in members):
            messagebox.showinfo("No overrides", "The selected hardpoints have no overrides.")
            return
        if not messagebox.askyesno(
            "Reset overrides", f"Remove every override on the {len(members)} selected hardpoint(s)?",
        ):
            return
        for member in members:
            per_unit.pop(member.name, None)
        self._after_override_change()
        self.status_label.config(text="Removed all overrides on the selection.")

    # -- actions ----------------------------------------------------------------------------------

    def _require_members(self) -> list[UnitHardpoint] | None:
        members, _group = self._selected_members()
        if not members:
            messagebox.showinfo("Nothing selected", "Select a hardpoint group (or hardpoints) first.")
            return None
        return members

    def _require_same_kind(self, members: list[UnitHardpoint]) -> bool:
        """Creating a config/template from several hardpoints uses the first
        as the representative, so a weapon/non-weapon mix is ambiguous."""
        if len({m.kind for m in members}) > 1:
            messagebox.showinfo(
                "Mixed selection",
                "The selection mixes weapon and non-weapon hardpoints. Select hardpoints of one kind to create "
                "a config or template from them.",
            )
            return False
        return True

    def _default_label(self) -> str:
        members, group = self._selected_members()
        if group is not None and group.label and not group.config_name:
            return group.label
        return members[0].name if members else ""

    def _projectile_entries(self) -> dict:
        return self.app.load_result.entries

    def _persist_assignments(self, members: list[UnitHardpoint], config_name: str):
        mapping = self.assignments.setdefault(self.unit_name, {})
        for member in members:
            if config_name:
                mapping[member.name] = config_name
            else:
                mapping.pop(member.name, None)
        save_assignments(self.assignments)

    def _make_config(self, members: list[UnitHardpoint], name: str, template: str = ""):
        rep = members[0]
        config = config_from_hardpoint(
            rep.fields, name, hardpoint_name=rep.name, projectile_entries=self._projectile_entries(),
            theatre=self.picker.theatre,
        )
        config.weapon_template = template
        config.weapon.category = template
        return config

    def _save_config(self, config) -> bool:
        tab = self.app.hardpoint_config_tab
        if config.name in tab.configs and not messagebox.askyesno(
            "Config exists", f"A hardpoint config named {config.name!r} already exists. Overwrite it?",
        ):
            return False
        tab.add_config(config)
        return True

    def _save_template(self, members: list[UnitHardpoint], category: str) -> bool:
        app = self.app
        if category in app.weapon_rules and not messagebox.askyesno(
            "Template exists", f"A Weapon Template for {category!r} already exists. Overwrite it?",
        ):
            return False
        weapon = self._make_config(members, category).weapon
        app.weapon_rules[category] = rule_from_config(
            weapon, category, theatre=self.picker.theatre, include_projectile=True,
        )
        save_rules(list(app.weapon_rules.values()))
        app._refresh_weapon_rules_list()
        return True

    def _on_create_config(self):
        members = self._require_members()
        if members is None:
            return
        if not self._require_same_kind(members):
            return
        name = simpledialog.askstring(
            "New Hardpoint Config", "Name for this hardpoint config:", initialvalue=self._default_label(),
            parent=self.app.root,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        config = self._make_config(members, name)
        if not self._save_config(config):
            return
        self._persist_assignments(members, name)
        self._regroup()
        self.status_label.config(text=f"Saved hardpoint config {name!r} and assigned {len(members)} hardpoint(s).")

    def _on_create_template(self):
        members = self._require_members()
        if members is None:
            return
        if not self._require_same_kind(members):
            return
        if members[0].kind != KIND_WEAPON:
            messagebox.showinfo("Not a weapon", "Weapon Templates can only be created from weapon hardpoints.")
            return
        category = simpledialog.askstring(
            "New Weapon Template", "Category name for this template:", initialvalue=self._default_label(),
            parent=self.app.root,
        )
        if not category or not category.strip():
            return
        category = category.strip()
        if self._save_template(members, category):
            self.status_label.config(text=f"Saved Weapon Template {category!r}.")

    def _on_create_both(self):
        members = self._require_members()
        if members is None:
            return
        if not self._require_same_kind(members):
            return
        is_weapon = members[0].kind == KIND_WEAPON
        name = simpledialog.askstring(
            "New Hardpoint Config", "Name for the hardpoint config"
            + (" (also used as the Weapon Template category):" if is_weapon else ":"),
            initialvalue=self._default_label(), parent=self.app.root,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        template = ""
        if is_weapon:
            if not self._save_template(members, name):
                return
            template = name
        config = self._make_config(members, name, template=template)
        if not self._save_config(config):
            return
        self._persist_assignments(members, name)
        self._regroup()
        what = "hardpoint config + Weapon Template" if is_weapon else "hardpoint config"
        self.status_label.config(text=f"Saved {what} {name!r} and assigned {len(members)} hardpoint(s).")

    def _on_assign_existing(self):
        members = self._require_members()
        if members is None:
            return
        configs = self.app.hardpoint_config_tab.configs
        if not configs:
            messagebox.showinfo("No configs", "There are no saved Hardpoint Configs yet - create one first.")
            return
        chosen = self._ask_choice(
            "Assign Hardpoint Config", "Assign the selection to:", sorted(configs, key=str.lower),
        )
        if not chosen:
            return
        self._persist_assignments(members, chosen)
        self._regroup()
        self.status_label.config(text=f"Assigned {len(members)} hardpoint(s) to {chosen!r}.")

    def _on_unassign(self):
        members = self._require_members()
        if members is None:
            return
        self._persist_assignments(members, "")
        self._regroup()
        self.status_label.config(text=f"Unassigned {len(members)} hardpoint(s).")

    def _ask_choice(self, title: str, prompt: str, values: list[str]) -> str | None:
        dialog = tk.Toplevel(self.app.root)
        dialog.title(title)
        dialog.transient(self.app.root)
        dialog.resizable(False, False)
        ttk.Label(dialog, text=prompt, padding=(12, 12, 12, 4)).pack(anchor=tk.W)
        var = tk.StringVar(value=values[0])
        combo = ttk.Combobox(dialog, textvariable=var, values=values, state="readonly", width=46)
        combo.pack(padx=12, pady=(0, 8))
        result: dict[str, str | None] = {"value": None}

        def ok():
            result["value"] = var.get()
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="OK", command=ok).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 6))
        dialog.grab_set()
        dialog.wait_window()
        return result["value"]
