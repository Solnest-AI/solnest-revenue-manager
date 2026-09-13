#!/usr/bin/env bash
# Flip the installed revenue-manager between a stable checkout and this RC.
# Only one is active at a time, so there is never a skill-name collision.
# Restart Claude Code after switching -- plugins bind at startup.
#
#   ./switch.sh rc        point the marketplace at THIS checkout
#   ./switch.sh stable    point it back at $REVENUE_MANAGER_STABLE
#   ./switch.sh status    show which one is active
#
# RC is wherever this script lives. STABLE comes from the environment so the
# script carries no machine-specific paths:
#   export REVENUE_MANAGER_STABLE=/path/to/your/stable/checkout
set -euo pipefail

RC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STABLE="${REVENUE_MANAGER_STABLE:-}"
MARKETPLACE="${REVENUE_MANAGER_MARKETPLACE:-revenue-manager-local}"
SETTINGS="$HOME/.claude/settings.json"

usage() { echo "usage: $0 {rc|stable|status}"; exit 1; }
[ $# -eq 1 ] || usage

python3 - "$1" "$STABLE" "$RC" "$SETTINGS" "$MARKETPLACE" <<'PY'
import json, sys, shutil, datetime, pathlib
mode, stable, rc, settings_path, mkt = sys.argv[1:6]
p = pathlib.Path(settings_path)
d = json.loads(p.read_text())
mkts = d.setdefault("extraKnownMarketplaces", {})
cur = mkts.get(mkt, {}).get("source", {}).get("path", "?")

def version_of(path):
    try:
        for cand in ("revenue-manager-plugin", "revenue-manager"):
            pj = pathlib.Path(path) / cand / ".claude-plugin" / "plugin.json"
            if pj.exists():
                return json.loads(pj.read_text()).get("version", "?")
    except Exception:
        pass
    return "?"

if mode == "status":
    label = "RC" if cur == rc else "STABLE" if stable and cur == stable else "OTHER"
    print(f"active: {label} ({version_of(cur)})\n  path: {cur}")
    if not stable:
        print("  (REVENUE_MANAGER_STABLE not set; 'stable' mode unavailable)")
    sys.exit(0)

if mode == "rc":
    target = rc
elif mode == "stable":
    if not stable:
        sys.exit("REVENUE_MANAGER_STABLE is not set. export it to your stable checkout first.")
    target = stable
else:
    sys.exit("usage: switch.sh {rc|stable|status}")

if not (pathlib.Path(target) / ".claude-plugin" / "marketplace.json").exists():
    sys.exit(f"refusing: no .claude-plugin/marketplace.json under {target}")

shutil.copy(p, p.with_suffix(f".json.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}"))
mkts[mkt] = {"source": {"source": "directory", "path": target}}
p.write_text(json.dumps(d, indent=2) + "\n")
print(f"switched to {mode.upper()} ({version_of(target)})\n  path: {target}\n\nNow: quit and reopen Claude Code, then run /revenue-manager.")
PY
