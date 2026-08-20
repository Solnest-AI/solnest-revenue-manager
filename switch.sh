#!/usr/bin/env bash
# Flip the installed revenue-manager between the stable v4.1.0 and this RC.
# Only one is active at a time, so there is never a skill-name collision.
# Restart Claude Code after switching -- plugins bind at startup.
set -euo pipefail

STABLE="/Users/ryan_/Documents/Solnest-Repos-Windows/revenue-manager-plugin"
RC="/Users/ryan_/Documents/Claude Code Repo/revenue-manager-next"
SETTINGS="$HOME/.claude/settings.json"

usage() { echo "usage: $0 {rc|stable|status}"; exit 1; }
[ $# -eq 1 ] || usage

python3 - "$1" "$STABLE" "$RC" "$SETTINGS" <<'PY'
import json, sys, shutil, datetime, pathlib
mode, stable, rc, settings_path = sys.argv[1:5]
p = pathlib.Path(settings_path)
d = json.loads(p.read_text())
mkts = d.setdefault("extraKnownMarketplaces", {})
cur = mkts.get("revenue-manager-local", {}).get("source", {}).get("path", "?")

if mode == "status":
    which = "RC (4.2.0-rc1)" if cur == rc else "STABLE (4.1.0)" if cur == stable else "UNKNOWN"
    print(f"active: {which}\n  path: {cur}")
    sys.exit(0)

target = rc if mode == "rc" else stable if mode == "stable" else None
if target is None:
    sys.exit("usage: switch.sh {rc|stable|status}")

shutil.copy(p, p.with_suffix(f".json.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}"))
mkts["revenue-manager-local"] = {"source": {"source": "directory", "path": target}}
p.write_text(json.dumps(d, indent=2) + "\n")
print(f"switched to {mode.upper()}\n  path: {target}\n\nNow: quit and reopen Claude Code, then run /revenue-manager.")
PY
