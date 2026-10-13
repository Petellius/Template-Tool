"""The "Project..." dialog: pick a base game folder + ordered mod stack,
or reopen a recent project.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import recent_projects
from .mod_discovery import discover_mods, find_xml_roots
from .project import ModLayer, Project


def _describe_mod_status(mod: ModLayer) -> str:
    if not os.path.isdir(mod.path):
        return "NOT FOUND"
    roots = find_xml_roots(mod.path)
    if roots:
        return f"{len(roots)} XML root(s)"
    return "no Data/XML found - will scan whole folder"


def _row_label(index: int, mod: ModLayer) -> str:
    state = "x" if mod.enabled else " "
    name = os.path.basename(os.path.normpath(mod.path)) or mod.path
    return f"{index + 1}. [{state}] {name}  --  {_describe_mod_status(mod)}"


class ProjectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, on_load, on_recent_changed=None):
        super().__init__(parent)
        self.title("Project")
        self.geometry("640x560")
        self.transient(parent)
        self.grab_set()

        self.on_load = on_load
        self.on_recent_changed = on_recent_changed
        self.mods: list[ModLayer] = []

        self._build_widgets()
        self._refresh_recent_list()

    # -- widget construction -------------------------------------------------

    def _build_widgets(self):
        pad = dict(padx=10, pady=6)

        recent_frame = ttk.LabelFrame(self, text="Recent Projects (double-click to load)")
        recent_frame.pack(fill=tk.X, **pad)
        recent_row = ttk.Frame(recent_frame)
        recent_row.pack(fill=tk.X, padx=6, pady=6)
        self.recent_listbox = tk.Listbox(recent_row, height=4)
        self.recent_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.recent_listbox.bind("<Double-Button-1>", self._on_recent_double_click)
        self.recent_listbox.bind("<<ListboxSelect>>", self._on_recent_select)
        ttk.Button(recent_row, text="Delete", command=self._on_delete_recent).pack(side=tk.LEFT, padx=(6, 0))

        name_frame = ttk.Frame(self)
        name_frame.pack(fill=tk.X, **pad)
        ttk.Label(name_frame, text="Project Name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value="Untitled Project")
        ttk.Entry(name_frame, textvariable=self.name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        base_frame = ttk.LabelFrame(self, text="Base Folder (vanilla game install)")
        base_frame.pack(fill=tk.X, **pad)
        base_row = ttk.Frame(base_frame)
        base_row.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.base_path_var = tk.StringVar(value="")
        ttk.Entry(base_row, textvariable=self.base_path_var, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(base_row, text="Browse...", command=self._on_browse_base).pack(side=tk.LEFT, padx=(6, 0))
        self.base_status_label = ttk.Label(base_frame, text="No base folder selected.", foreground="#666")
        self.base_status_label.pack(anchor=tk.W, padx=6, pady=(2, 6))

        mods_frame = ttk.LabelFrame(self, text="Mods (load order - later overrides earlier)")
        mods_frame.pack(fill=tk.BOTH, expand=True, **pad)

        list_row = ttk.Frame(mods_frame)
        list_row.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.mods_listbox = tk.Listbox(list_row, exportselection=False)
        self.mods_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        mods_scroll = ttk.Scrollbar(list_row, orient=tk.VERTICAL, command=self.mods_listbox.yview)
        mods_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.mods_listbox.config(yscrollcommand=mods_scroll.set)

        button_col = ttk.Frame(mods_frame)
        button_col.pack(fill=tk.X, padx=6, pady=(0, 6))
        self.add_from_base_button = ttk.Menubutton(button_col, text="Add from corruption\\Mods")
        self.add_from_base_button.pack(side=tk.LEFT)
        self.add_from_base_menu = tk.Menu(self.add_from_base_button, tearoff=False)
        self.add_from_base_button.config(menu=self.add_from_base_menu)
        ttk.Button(button_col, text="Add Folder...", command=self._on_add_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_col, text="Remove", command=self._on_remove_mod).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_col, text="Move Up", command=lambda: self._move_mod(-1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_col, text="Move Down", command=lambda: self._move_mod(1)).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_col, text="Toggle Enabled", command=self._on_toggle_enabled).pack(side=tk.LEFT, padx=4)

        bottom_row = ttk.Frame(self)
        bottom_row.pack(fill=tk.X, **pad)
        ttk.Button(bottom_row, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(bottom_row, text="Load Project", command=self._on_load_project).pack(side=tk.RIGHT, padx=(0, 6))

    # -- recent projects -------------------------------------------------------

    def _refresh_recent_list(self):
        self._recent_projects = recent_projects.load_recent()
        self.recent_listbox.delete(0, tk.END)
        for project in self._recent_projects:
            mod_count = len(project.mods)
            self.recent_listbox.insert(
                tk.END, f"{project.name}  --  {os.path.basename(project.base_path)}  --  {mod_count} mod(s)"
            )

    def _on_recent_select(self, _event):
        selection = self.recent_listbox.curselection()
        if not selection:
            return
        self._load_project_into_form(self._recent_projects[selection[0]])

    def _on_recent_double_click(self, _event):
        selection = self.recent_listbox.curselection()
        if not selection:
            return
        self._load_project_into_form(self._recent_projects[selection[0]])
        self._on_load_project()

    def _on_delete_recent(self):
        selection = self.recent_listbox.curselection()
        if not selection:
            return
        project = self._recent_projects[selection[0]]
        if not messagebox.askyesno("Delete recent project", f"Remove {project.name!r} from Recent Projects?"):
            return

        recent_projects.forget(project.name)
        self._refresh_recent_list()
        if self.on_recent_changed:
            self.on_recent_changed()

    def _load_project_into_form(self, project: Project):
        self.name_var.set(project.name)
        self.base_path_var.set(project.base_path)
        self.mods = list(project.mods)
        self._update_base_status()
        self._refresh_mods_list()
        self._refresh_add_from_base_menu()

    # -- base folder -------------------------------------------------------

    def _on_browse_base(self):
        path = filedialog.askdirectory(title="Select the base game folder (e.g. .../corruption)")
        if not path:
            return
        self.base_path_var.set(path)
        self._update_base_status()
        self._refresh_add_from_base_menu()

    def _update_base_status(self):
        path = self.base_path_var.get()
        if not path:
            self.base_status_label.config(text="No base folder selected.", foreground="#666")
            return
        if not os.path.isdir(path):
            self.base_status_label.config(text="Folder not found.", foreground="#b00000")
            return
        roots = find_xml_roots(path)
        if roots:
            self.base_status_label.config(text=f"Found {len(roots)} XML root(s).", foreground="#207020")
        else:
            self.base_status_label.config(
                text=(
                    "No Data/XML folder detected - vanilla data is packed in .meg files, "
                    "which this tool can't read yet. Inheritance chains bottoming out at a "
                    "vanilla-only Name will show as unresolved."
                ),
                foreground="#a06000",
            )

    # -- mods list -------------------------------------------------------

    def _refresh_mods_list(self):
        self.mods_listbox.delete(0, tk.END)
        for index, mod in enumerate(self.mods):
            self.mods_listbox.insert(tk.END, _row_label(index, mod))

    def _refresh_add_from_base_menu(self):
        self.add_from_base_menu.delete(0, tk.END)
        base_path = self.base_path_var.get()
        if not base_path or not os.path.isdir(base_path):
            self.add_from_base_menu.add_command(label="(select a base folder first)", state=tk.DISABLED)
            return

        mods_root = os.path.join(base_path, "Mods")
        candidates = discover_mods(mods_root)
        existing_paths = {os.path.normcase(os.path.abspath(m.path)) for m in self.mods}

        added_any = False
        for candidate in candidates:
            if os.path.normcase(os.path.abspath(candidate.path)) in existing_paths:
                continue
            added_any = True
            label = candidate.name if candidate.usable else f"{candidate.name} (no XML data)"
            self.add_from_base_menu.add_command(
                label=label, command=lambda c=candidate: self._add_mod(c.path)
            )
        if not added_any:
            self.add_from_base_menu.add_command(label="(no more mods found)", state=tk.DISABLED)

    def _add_mod(self, path: str):
        normalized = os.path.normcase(os.path.abspath(path))
        if any(os.path.normcase(os.path.abspath(m.path)) == normalized for m in self.mods):
            messagebox.showinfo("Already added", f"{path!r} is already in this project.")
            return
        self.mods.append(ModLayer(path=path))
        self._refresh_mods_list()
        self._refresh_add_from_base_menu()

    def _on_add_folder(self):
        path = filedialog.askdirectory(title="Select a mod folder to add")
        if not path:
            return
        self._add_mod(path)

    def _selected_mod_index(self):
        selection = self.mods_listbox.curselection()
        return selection[0] if selection else None

    def _on_remove_mod(self):
        index = self._selected_mod_index()
        if index is None:
            return
        del self.mods[index]
        self._refresh_mods_list()
        self._refresh_add_from_base_menu()

    def _move_mod(self, offset: int):
        index = self._selected_mod_index()
        if index is None:
            return
        new_index = index + offset
        if not (0 <= new_index < len(self.mods)):
            return
        self.mods[index], self.mods[new_index] = self.mods[new_index], self.mods[index]
        self._refresh_mods_list()
        self.mods_listbox.selection_set(new_index)

    def _on_toggle_enabled(self):
        index = self._selected_mod_index()
        if index is None:
            return
        self.mods[index].enabled = not self.mods[index].enabled
        self._refresh_mods_list()
        self.mods_listbox.selection_set(index)

    # -- load -------------------------------------------------------

    def _on_load_project(self):
        base_path = self.base_path_var.get()
        if not base_path:
            messagebox.showerror("No base folder", "Please select a base folder first.")
            return

        project = Project(name=self.name_var.get().strip() or "Untitled Project", base_path=base_path, mods=list(self.mods))
        self.destroy()
        self.on_load(project)
