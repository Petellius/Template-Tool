# Template Tool

A desktop tool for *Star Wars: Empire at War - Forces of Corruption* modders. It reads a
project's XML (base game plus mod layers) and lets you browse projectiles, units,
hardpoints, category masks and behaviors, build weapon templates and per-slot weapon
configs, export them as game XML, and compare loadouts in a battle simulator.

## Running

Requires Python 3 with tkinter (included in the standard Windows installer). No other
dependencies.

```
python run.py
```

On first launch, choose your game `corruption` folder and any mod layers to open a project.

## Layout

- `projectile_viewer/` - the application package (`ui.py` is the main window).
- `user_data/weapon_rules.json` - shared weapon template presets.
- `user_data/behavior_descriptions.json` - behavior description text.
- Other `user_data/` files (recent projects, settings, saved weapon configs) are personal
  state, created on first run and not tracked in git.
