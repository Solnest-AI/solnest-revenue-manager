"""Decision comparator for the full-vs-reduced eval.

Turns a decision JSON (see schema.py) into canonical *positions* and diffs two position sets.
Every divergence carries a severity:

  HARD  a different decision: opposite sign on a price field, a change of more than PCT_TOL
        points against a hold, gate blocked vs pass, a hard flag present on one side only,
        opposite direction on the same month for dated changes.
  SOFT  same decision, different shading: a small move vs hold, magnitude differences,
        soft flags, dated changes present on one side only.

`attribute()` then classifies each key across reps: AGREE (both conditions agree),
NOISE (a condition disagrees with itself on that key, so the model is unstable there and
nothing can be attributed to the reduction) or DIVERGE (both conditions are internally
consistent and disagree with each other: the reduction changed the decision).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

HARD = "HARD"
SOFT = "SOFT"
PCT_TOL = 5.0        # a move of at most this many percent against a hold is shading, not a decision
PCT_MAG_TOL = 10.0   # same sign, magnitudes further apart than this are reported as SOFT

GLOBAL_FIELDS = ("base_price", "min_price", "max_price", "min_stay")
DATED_FIELDS = ("date_override", "orphan_gap", "dow_adjustment", "last_minute_discount", "other")
HARD_FLAGS = {
    "SYNC_DEFECT_INVISIBLE_NIGHTS", "PRICE_DRIFT", "LONG_TERM_RENTAL", "NOT_SYNCED",
    "MIN_BELOW_BASE", "FLOOR_PINNED", "CURRENCY_MISMATCH",
}
DIRECTION_SIGN = {"raise": 1, "lower": -1, "hold": 0, "mixed": 0, "blocked": 0}


@dataclass(frozen=True)
class Divergence:
    key: str
    severity: str
    a: object
    b: object


def _sign(action: str) -> int:
    return {"raise": 1, "lower": -1}.get(action, 0)


def _months(d_from: str | None, d_to: str | None) -> list[str]:
    if not d_from:
        return []
    try:
        a = dt.date.fromisoformat(d_from[:10])
        b = dt.date.fromisoformat((d_to or d_from)[:10])
    except ValueError:
        return []
    if b < a:
        a, b = b, a
    out, cur = [], dt.date(a.year, a.month, 1)
    while cur <= b:
        out.append(cur.strftime("%Y-%m"))
        cur = dt.date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)
    return out


def positions(decision: dict) -> dict:
    """Canonical positions. Absent global fields are 'hold'."""
    glob = {f: (0, 0.0) for f in GLOBAL_FIELDS}
    dated: dict[str, int] = {}
    for ch in decision.get("changes", []):
        field, action = ch.get("field"), ch.get("action")
        pct = ch.get("pct_move")
        pct = float(pct) if isinstance(pct, (int, float)) else 0.0
        s = _sign(action)
        if action == "set" and ch.get("old") not in (None, 0) and ch.get("new") is not None:
            # a "set" is a raise or lower in disguise
            pct = (float(ch["new"]) - float(ch["old"])) / float(ch["old"]) * 100.0 if not pct else pct
            s = 1 if pct > 0 else (-1 if pct < 0 else 0)
        if field in GLOBAL_FIELDS:
            glob[field] = (s, pct)
        elif field in DATED_FIELDS:
            for m in _months(ch.get("date_from"), ch.get("date_to")):
                k = f"{m}:{field}"
                dated[k] = dated.get(k, 0) + (s if s else (1 if action == "set" else 0))
    flags = set(decision.get("flags") or [])
    gate = (decision.get("gate") or {}).get("status", "not_run")
    return {
        "gate": gate,
        "direction": decision.get("overall_direction", "hold"),
        "global": glob,
        "dated": {k: (1 if v > 0 else -1 if v < 0 else 0) for k, v in dated.items()},
        "hard_flags": flags & HARD_FLAGS,
        "soft_flags": flags - HARD_FLAGS,
    }


def diff(pa: dict, pb: dict) -> list[Divergence]:
    out: list[Divergence] = []
    if pa["gate"] != pb["gate"]:
        blocking = {"blocked", "not_synced"}
        sev = HARD if ((pa["gate"] in blocking) != (pb["gate"] in blocking)) else SOFT
        out.append(Divergence("gate", sev, pa["gate"], pb["gate"]))
    if pa["direction"] != pb["direction"]:
        sa, sb = DIRECTION_SIGN.get(pa["direction"], 0), DIRECTION_SIGN.get(pb["direction"], 0)
        out.append(Divergence("direction", HARD if sa * sb < 0 else SOFT, pa["direction"], pb["direction"]))
    for f in GLOBAL_FIELDS:
        (sa, pa_pct), (sb, pb_pct) = pa["global"][f], pb["global"][f]
        if sa == sb:
            if sa and abs(pa_pct - pb_pct) > PCT_MAG_TOL:
                out.append(Divergence(f"global:{f}", SOFT, pa_pct, pb_pct))
            continue
        if sa * sb < 0:
            out.append(Divergence(f"global:{f}", HARD, (sa, pa_pct), (sb, pb_pct)))
        else:  # one holds, the other moves
            moving = pa_pct if sa else pb_pct
            sev = HARD if (f == "min_stay" or abs(moving) > PCT_TOL) else SOFT
            out.append(Divergence(f"global:{f}", sev, (sa, pa_pct), (sb, pb_pct)))
    for k in sorted(set(pa["dated"]) | set(pb["dated"])):
        sa, sb = pa["dated"].get(k), pb["dated"].get(k)
        if sa is None or sb is None:
            out.append(Divergence(f"dated:{k}", SOFT, sa, sb))
        elif sa * sb < 0:
            out.append(Divergence(f"dated:{k}", HARD, sa, sb))
    for fl in sorted(pa["hard_flags"] ^ pb["hard_flags"]):
        out.append(Divergence(f"flag:{fl}", HARD, fl in pa["hard_flags"], fl in pb["hard_flags"]))
    for fl in sorted(pa["soft_flags"] ^ pb["soft_flags"]):
        out.append(Divergence(f"flag:{fl}", SOFT, fl in pa["soft_flags"], fl in pb["soft_flags"]))
    return out


def _pairs(items):
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            yield items[i], items[j]


def _describe(p: dict, key: str):
    if key == "gate":
        return p["gate"]
    if key == "direction":
        return p["direction"]
    if key.startswith("global:"):
        s, pct = p["global"][key[7:]]
        return {1: "raise", -1: "lower"}.get(s, "hold") + (f" {pct:+.1f}%" if s else "")
    if key.startswith("dated:"):
        return {1: "raise", -1: "lower", 0: "set"}.get(p["dated"].get(key[6:]), "none")
    if key.startswith("flag:"):
        fl = key[5:]
        return fl in p["hard_flags"] or fl in p["soft_flags"]
    return None


def attribute(reduced: list[dict], full: list[dict]) -> dict[str, dict]:
    """Classify every key that appears in any pairwise diff.

    Returns {key: {status, severity, reduced, full}} where status is AGREE, NOISE or DIVERGE,
    `reduced`/`full` are the per-rep descriptions of that key, and severity is the worst
    severity seen on any cross pair (None when AGREE).
    """
    pr = [positions(d) for d in reduced]
    pf = [positions(d) for d in full]
    within_r = {d.key for a, b in _pairs(pr) for d in diff(a, b)}
    within_f = {d.key for a, b in _pairs(pf) for d in diff(a, b)}
    cross: dict[str, list[Divergence]] = {}
    n_cross = 0
    for a in pf:
        for b in pr:
            n_cross += 1
            for d in diff(a, b):
                cross.setdefault(d.key, []).append(d)
    keys = set(cross) | within_r | within_f | {"gate", "direction"} | {f"global:{f}" for f in GLOBAL_FIELDS}
    out = {}
    for k in sorted(keys):
        ds = cross.get(k, [])
        if k in within_r or k in within_f:
            status = "NOISE"
        elif ds and len(ds) == n_cross:
            status = "DIVERGE"
        elif ds:
            status = "NOISE"   # some cross pairs differ, some do not, yet within pairs agree: only possible with 1 rep somewhere
        else:
            status = "AGREE"
        sev = None
        if ds:
            sev = HARD if any(d.severity == HARD for d in ds) else SOFT
        out[k] = {
            "status": status, "severity": sev,
            "reduced": [_describe(p, k) for p in pr],
            "full": [_describe(p, k) for p in pf],
            "unstable_in": [c for c, s in (("reduced", within_r), ("full", within_f)) if k in s],
        }
    return out
