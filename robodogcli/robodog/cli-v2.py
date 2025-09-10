# Quick Solution: Add Exclude Folders to CLI

I'll add a new `/exclude` command to set comma-separated exclude folders globally. This updates the service's exclude dirs and logs the change. The exclude dirs are already used in `search_files` (used by various commands like `/include`).

## Updated CLI Code Snippet

```python
# In cli.py, update print_help:
cmds = {
    ...
    "exclude": "set exclude directories (comma-separated)",
    ...
}
logging.info("  /{cmd:<20} — {desc}")

# In cli.py, in the command loop:
elif cmd == "exclude":
    if not args:
        logging.warning("Usage: /exclude <comma-sep-dirs>")
    else:
        dirs = [d.strip() for d in args[0].split(',') if d.strip()]
        svc.set_exclude_dirs(dirs)
        logging.info("Exclude folders set to: %s", dirs)
```

## Updated Service Code Snippet

```python
# In service.py, in __init__:
self.exclude_dirs = {"node_modules", "dist"}

# Add new method in RobodogService:
def set_exclude_dirs(self, dirs):
    if isinstance(dirs, str):
        dirs = dirs.split(',')
    if isinstance(dirs, list):
        self.exclude_dirs = set(d.strip() for d in dirs if d.strip())
    self.exclude_dirs = set(dirs)  # fallback

# Update search_files:
exclude_dirs = set(exclude_dirs or self.exclude_dirs)
```

Usage example: `/exclude node_modules,dist,.git`

This enhancement allows flexible exclusion for `/include`, `/import`, and other file-searching commands. If needed, we can later add per-command exclude flags.