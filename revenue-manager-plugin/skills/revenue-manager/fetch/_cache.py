"""Where the reducers keep raw API payloads.

Runtime caches do not belong inside the plugin tree: `claude plugin update` copies the
whole directory into ~/.claude/plugins/cache/, so a payload cached beside the script gets
duplicated on every version bump. Everything lands under one user-level directory instead.

Resolution order:
  1. $RC_CACHE_DIR                       (tests, or an operator who wants it elsewhere)
  2. $XDG_CACHE_HOME/revenue-manager
  3. ~/.cache/revenue-manager
"""
import os


def cache_dir(sub: str = "") -> str:
    root = os.environ.get("RC_CACHE_DIR")
    if not root:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        root = os.path.join(base, "revenue-manager")
    path = os.path.join(root, sub) if sub else root
    os.makedirs(path, exist_ok=True)
    return path
