"""A reusable Theatre / Faction / CategoryMask / Unit picker row.

Filters cascade exactly like the Weapon Configs tab's picker (Faction
options come from the theatre's units, CategoryMask options from units
matching the chosen Faction, the Unit list from both) and read the same
data - Affiliation and the first non-"Anti*" CategoryMask, resolved through
each unit's Variant_Of_Existing_Type chain - via the app's cached
`_wc_unit_faction_categories`. The Weapon Configs tab keeps its own
hand-wired copy; this one exists for tabs that need an independent picker.
"""

import tkinter as tk
from tkinter import ttk

ALL = "(All)"
NO_FACTION = "(No Faction)"
NO_CATEGORY = "(No CategoryMask)"
THEATRES = ("Space", "Land")


class UnitPicker:
    def __init__(self, app, parent: ttk.Frame, on_unit_selected, autosize=None):
        self.app = app
        self.on_unit_selected = on_unit_selected
        self._autosize = autosize or (lambda _combo: None)

        row = ttk.Frame(parent, padding=8)
        row.pack(side=tk.TOP, fill=tk.X)
        self.frame = row

        ttk.Label(row, text="Theatre:").grid(row=0, column=0, sticky=tk.W)
        self.theatre_var = tk.StringVar(value=THEATRES[0])
        theatre_combo = ttk.Combobox(
            row, textvariable=self.theatre_var, state="readonly", values=list(THEATRES), width=10,
        )
        theatre_combo.grid(row=0, column=1, sticky=tk.W, padx=(6, 20))
        theatre_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_theatre_changed())

        ttk.Label(row, text="Faction:").grid(row=0, column=2, sticky=tk.W)
        self.faction_var = tk.StringVar(value=ALL)
        self.faction_combo = ttk.Combobox(
            row, textvariable=self.faction_var, state="readonly", values=[ALL], width=16,
        )
        self.faction_combo.grid(row=0, column=3, sticky=tk.W, padx=(6, 20))
        self.faction_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_faction_changed())

        ttk.Label(row, text="CategoryMask:").grid(row=0, column=4, sticky=tk.W)
        self.category_var = tk.StringVar(value=ALL)
        self.category_combo = ttk.Combobox(
            row, textvariable=self.category_var, state="readonly", values=[ALL], width=18,
        )
        self.category_combo.grid(row=0, column=5, sticky=tk.W, padx=(6, 20))
        self.category_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_category_changed())

        ttk.Label(row, text="Unit:").grid(row=0, column=6, sticky=tk.W)
        self.unit_var = tk.StringVar()
        self.unit_combo = ttk.Combobox(row, textvariable=self.unit_var, width=40)
        self.unit_combo.grid(row=0, column=7, sticky=tk.W, padx=(6, 6))
        self.unit_var.trace_add("write", lambda *_: self._filter_units())
        self.unit_combo.bind("<<ComboboxSelected>>", lambda _e: self._select_unit())
        self.unit_combo.bind("<Return>", lambda _e: self._select_unit())

    # -- data -------------------------------------------------------------------------------------

    @property
    def theatre(self) -> str:
        return self.theatre_var.get()

    def _theatre_units(self) -> list[str]:
        tags = self.app._theatre_tags(self.theatre)
        entries = self.app.combat_unit_load_result.entries
        return sorted(n for n in self.app.all_combat_unit_names if entries[n].element.tag in tags)

    def _filtered(self, faction: str | None = None, category: str | None = None) -> list[str]:
        faction = self.faction_var.get() if faction is None else faction
        category = self.category_var.get() if category is None else category
        names = []
        for name in self._theatre_units():
            factions, categories = self.app._wc_unit_faction_categories(name)
            if faction != ALL:
                if faction == NO_FACTION:
                    if factions:
                        continue
                elif faction not in factions:
                    continue
            if category != ALL:
                if category == NO_CATEGORY:
                    if categories:
                        continue
                elif category not in categories:
                    continue
            names.append(name)
        return names

    # -- refresh ----------------------------------------------------------------------------------

    def refresh(self):
        """Rebuilds the Faction/CategoryMask options and the unit list from
        the app's currently loaded units; stale selections fall back to (All)."""
        factions: set[str] = set()
        has_no_faction = False
        for name in self._theatre_units():
            f, _c = self.app._wc_unit_faction_categories(name)
            factions |= f
            has_no_faction = has_no_faction or not f
        faction_values = [ALL, *sorted(factions, key=str.lower)] + ([NO_FACTION] if has_no_faction else [])
        self.faction_combo.config(values=faction_values)
        if self.faction_var.get() not in faction_values:
            self.faction_var.set(ALL)
        self._autosize(self.faction_combo)

        categories: set[str] = set()
        has_no_category = False
        for name in self._filtered(category=ALL):
            _f, c = self.app._wc_unit_faction_categories(name)
            categories |= c
            has_no_category = has_no_category or not c
        category_values = [ALL, *sorted(categories, key=str.lower)] + ([NO_CATEGORY] if has_no_category else [])
        self.category_combo.config(values=category_values)
        if self.category_var.get() not in category_values:
            self.category_var.set(ALL)
        self._autosize(self.category_combo)

        self._filter_units()

    def _filter_units(self):
        query = self.unit_var.get().strip().lower()
        names = self._filtered()
        values = names if not query else [n for n in names if query in n.lower()]
        self.unit_combo.config(values=values)
        self._autosize(self.unit_combo)

    # -- events -----------------------------------------------------------------------------------

    def _on_theatre_changed(self):
        self.faction_var.set(ALL)
        self.category_var.set(ALL)
        self.unit_var.set("")
        self.refresh()

    def _on_faction_changed(self):
        self.category_var.set(ALL)
        self.unit_var.set("")
        self.refresh()

    def _on_category_changed(self):
        self.unit_var.set("")
        self.refresh()

    def _select_unit(self):
        name = self.unit_var.get().strip()
        entries = self.app.combat_unit_load_result.entries
        if name in entries:
            self.on_unit_selected(name)
