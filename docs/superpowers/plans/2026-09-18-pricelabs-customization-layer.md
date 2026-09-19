# PriceLabs Customization Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the revenue-manager skill to read the six PriceLabs listing customizations, attribute an observed price to the layer that produced it, and change a rule behind the existing approval gate without inverting a sign or wiping a weekday.

**Architecture:** Three new modules under `skills/revenue-manager/fetch/`. `attribution.py` is pure arithmetic over price rows plus rule configs, no network, so the reasoning is unit-testable. `reduce_customizations.py` follows the established reducer contract exactly: fetch over plain HTTP, cache the raw payload outside the plugin tree, print a compact table, exit 2 when it cannot produce a trustworthy answer. `customization_write.py` owns the write path: snapshot, validate, merge, echo check. Runbook wiring lands last so the skill never references a module that does not exist yet.

**Tech Stack:** Python 3 stdlib only (`urllib.request`, `csv`, `json`, `argparse`). No third-party dependencies anywhere in `fetch/`. Tests are plain asserts through the repo's own `check()` harness, not pytest.

**Spec:** `docs/superpowers/specs/2026-09-18-pricelabs-customization-layer-design.md`

## Global Constraints

- **Repo is PUBLIC** (`Solnest-AI/solnest-revenue-manager`). No property names, guest names, listing UUIDs, group ids, profile ids, or Supabase project refs in any committed file. Fixtures use synthetic values. Run the leak scan in Task 8 before the final commit.
- **Python 3 stdlib only.** `fetch/` has zero third-party imports. Match that.
- **Exit 2 means "cannot produce a trustworthy answer this run", never "there is none."** Exit 0 with a zero count is the valid empty answer. This distinction already exists in `reduce_overrides.py` and must be preserved.
- **`guestName` is PII.** It is dropped at the parsing boundary and never cached or printed. No new code may read it.
- **Never print the API key.** Read it with the existing `resolve_key()` pattern.
- **Direct calls to `api.pricelabs.co` return 403 without a browser-like `User-Agent`.** Every request sets `UA`.
- **Rate limits:** 60 requests/minute, 1,000/hour.
- **No writes are executed by any code in this plan.** `customization_write.py` builds, validates and compares payloads. The actual POST is the operator's approved action in Step 8, and Task 4 ships no code path that fires one unattended.
- **Plugin cache is version-keyed.** `claude plugin update` is a no-op unless the version string changes. Every RC bump changes `revenue-manager-plugin/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` together.
- Branch: `feat/token-reducer`. Current version: `4.2.0-rc9`.

---

## File Structure

| File | Responsibility |
|---|---|
| `fetch/attribution.py` (new) | Pure: `ce` per date, grouping by weekday / lead time / month, which rules cover which dates, candidate vs confirmed. No network, no I/O. |
| `fetch/reduce_customizations.py` (new) | Fetch and reduce the rule stack, profiles, actions, nudges and logs into one compact table. |
| `fetch/customization_write.py` (new) | Snapshot, range validation, full-object day-of-week merge, echo comparison, the gated action-sign conversion. |
| `fetch/test_fixture_customizations.json` (new) | Synthetic payload exercising every rule type, both signs, on and off. |
| `fetch/smoke_test_customizations.py` (new) | Offline tests for the three modules above. Same `check()` pattern as `smoke_test.py`. |
| `fetch/factcheck.py` (modify) | Add the `customizations` fact class so the reducer's table is proved against the raw payload. |
| `SKILL.md` (modify) | Steps 4c, 5.5, 7, 8, 9. |
| `references/audit-write.md` (modify) | The layer and snapshot columns on the audit rows. |

---

### Task 1: `attribution.py` — ce arithmetic and the co-incidence test

**Files:**
- Create: `revenue-manager-plugin/skills/revenue-manager/fetch/attribution.py`
- Create: `revenue-manager-plugin/skills/revenue-manager/fetch/test_fixture_customizations.json`
- Create: `revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces, all used by Tasks 2, 3 and 5:
  - `ce_rows(price_rows: list[dict], today: str) -> list[dict]` with keys `date`, `ce`, `dow` (0=Mon), `days_out`, `month`
  - `group_ce(rows: list[dict], key: str) -> dict[str, dict]`, `key` in `{"dow", "lead", "month"}`, values `{"n", "median_ce", "min_ce", "max_ce"}`
  - `rule_covers(rule: str, cfg: dict, row: dict) -> bool`
  - `rule_direction(rule: str, cfg: dict, row: dict | None = None) -> str` returning `"down"`, `"up"`, `"none"` or `"unknown"`
  - `classify(affected_dates: set[str], rows: list[dict], rules: dict) -> list[dict]` with keys `rule`, `verdict`, `direction`, `covered_affected`, `covered_unaffected`, `why`
  - `SENTINELS: set`

- [ ] **Step 1: Write the fixture**

Create `fetch/test_fixture_customizations.json`. Synthetic values, chosen so every branch is exercised: a negative day-of-week pair, a positive one, a last-minute discount, a far-out premium, one market-driven rule whose direction is unknowable, and two rules that are OFF (one of them holding dormant seasons).

```json
{
  "customizations": {
    "day_of_week_adjustment": {
      "dow_factor_on": true,
      "dow_factor_value_mon": -10.0,
      "dow_factor_value_tue": -10.0,
      "dow_factor_value_wed": 0.0,
      "dow_factor_value_thu": 0.0,
      "dow_factor_value_fri": 15.0,
      "dow_factor_value_sat": 15.0,
      "dow_factor_value_sun": 0.0,
      "effective": "Mon -10% discount, Tue -10% discount, Fri +15% premium, Sat +15% premium"
    },
    "last_minute_prices": {
      "last_min_factor_on": true,
      "last_min_factor_type": "linear_gradual",
      "last_min_factor_value": -20.0,
      "last_min_factor_dfd": 14,
      "effective": "up to 20% discount starting 14 days from check-in"
    },
    "far_out_premium": {
      "far_out_premium_on": true,
      "far_out_premium_type": "linear",
      "far_out_premium_value": 25.0,
      "far_out_premium_start": 180,
      "far_out_premium_step": 1,
      "effective": "up to 25% premium reaching maximum 180 days out"
    },
    "demand_factor": {
      "tone_demand_factor_on": true,
      "tone_demand_factor": "recommended",
      "effective": "Market Driven - Balanced"
    },
    "seasonality": {
      "seasonality_customization_on": false,
      "seasonality_type": "recommended",
      "effective": "off: the market-driven seasonal curve applies"
    },
    "custom_seasonal_profile": {
      "custom_seasonal_profile_on": false,
      "custom_seasonal_profile": {
        "price_type": "percentage",
        "seasons": [
          {"season_name": "SeasonA", "start_month": "4", "start_day": "17",
           "end_month": "5", "end_day": "12", "base_price": -5,
           "lowest_price": null, "highest_price": -5},
          {"season_name": "SeasonB", "start_month": "5", "start_day": "28",
           "end_month": "7", "end_day": "19", "base_price": 5,
           "lowest_price": 15, "highest_price": null}
        ]
      },
      "effective": "off: 2 stored seasons are dormant"
    }
  },
  "profiles": {
    "minstay": [
      {"id": 1001, "name": "ProfileA", "archived": false},
      {"id": 1002, "name": "ProfileB", "archived": false}
    ],
    "pricing": [],
    "checkincheckout": []
  },
  "price_rows": [
    {"date": "2026-09-21", "price": 90,  "uncustomized_price": 100},
    {"date": "2026-09-22", "price": 90,  "uncustomized_price": 100},
    {"date": "2026-09-23", "price": 100, "uncustomized_price": 100},
    {"date": "2026-09-24", "price": 100, "uncustomized_price": 100},
    {"date": "2026-09-25", "price": 115, "uncustomized_price": 100},
    {"date": "2026-09-26", "price": 115, "uncustomized_price": 100},
    {"date": "2026-09-27", "price": 100, "uncustomized_price": 100},
    {"date": "2026-09-28", "price": 90,  "uncustomized_price": 100},
    {"date": "2026-09-29", "price": 90,  "uncustomized_price": 100},
    {"date": "2026-10-01", "price": -1,  "uncustomized_price": 100},
    {"date": "2026-10-02", "price": 100, "uncustomized_price": -2},
    {"date": "2026-10-03", "price": 100, "uncustomized_price": 0}
  ]
}
```

2026-09-21 is a Monday. So Mon/Tue are the 0.90 rows, Fri/Sat are the 1.15 rows, and the last three rows are the sentinel and divide-by-zero cases that must be dropped.

- [ ] **Step 2: Write the failing tests**

Create `fetch/smoke_test_customizations.py`:

```python
#!/usr/bin/env python3
"""Offline tests for the customization layer -- no API key, no network.

Guards the traps that make a customization write dangerous:
  1. ce is exact in total but must never be attributed to a single rule
     without the co-incidence test passing
  2. a market-driven rule's direction is unknowable, so it can never be
     "confirmed"
  3. day-of-week days omitted from a write reset to 0
  4. the sign is accepted either way, so an out-of-range or wrong-signed
     value must be caught before the request is built
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import attribution as at  # noqa: E402

FIX = json.load(open(HERE / "test_fixture_customizations.json"))
RULES = FIX["customizations"]
TODAY = "2026-09-18"
fails = []

def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}: {label}{'' if cond else '  -> ' + detail}")
    if not cond:
        fails.append(label)

print("customization layer smoke test\n")

# --- ce_rows ----------------------------------------------------------------
rows = at.ce_rows(FIX["price_rows"], TODAY)
check("sentinel and zero-denominator rows are dropped", len(rows) == 9,
      f"got {len(rows)}, want 9")
check("ce is price / uncustomized_price",
      abs(rows[0]["ce"] - 0.90) < 1e-9, f"got {rows[0]['ce']}")
check("2026-09-21 is Monday (dow 0)", rows[0]["dow"] == 0, f"got {rows[0]['dow']}")
check("days_out counts from today",
      rows[0]["days_out"] == 3, f"got {rows[0]['days_out']}")

# --- group_ce ---------------------------------------------------------------
by_dow = at.group_ce(rows, "dow")
check("Monday group median ce is 0.90",
      abs(by_dow["0"]["median_ce"] - 0.90) < 1e-9, f"got {by_dow['0']}")
check("Friday group median ce is 1.15",
      abs(by_dow["4"]["median_ce"] - 1.15) < 1e-9, f"got {by_dow['4']}")
check("Wednesday group is unmoved",
      abs(by_dow["2"]["median_ce"] - 1.00) < 1e-9, f"got {by_dow['2']}")

# --- rule_covers ------------------------------------------------------------
mon = rows[0]
wed = [r for r in rows if r["dow"] == 2][0]
check("day-of-week covers a day with a non-zero value",
      at.rule_covers("day_of_week_adjustment", RULES["day_of_week_adjustment"], mon))
check("day-of-week does NOT cover a day whose value is 0",
      not at.rule_covers("day_of_week_adjustment", RULES["day_of_week_adjustment"], wed))
check("last-minute covers dates inside its window",
      at.rule_covers("last_minute_prices", RULES["last_minute_prices"], mon))
far = dict(mon, days_out=200)
check("far-out covers dates past its start",
      at.rule_covers("far_out_premium", RULES["far_out_premium"], far))
check("far-out does not cover near dates",
      not at.rule_covers("far_out_premium", RULES["far_out_premium"], mon))
check("a rule toggled OFF still covers, because off is not off",
      at.rule_covers("seasonality", RULES["seasonality"], mon),
      "off hands the date to the market-driven default, which is still an effect")

# --- rule_direction ---------------------------------------------------------
check("negative day-of-week value reads as down",
      at.rule_direction("day_of_week_adjustment", RULES["day_of_week_adjustment"], mon) == "down")
check("positive day-of-week value reads as up",
      at.rule_direction("day_of_week_adjustment", RULES["day_of_week_adjustment"],
                        [r for r in rows if r["dow"] == 4][0]) == "up")
check("a market-driven type has unknown direction",
      at.rule_direction("demand_factor", RULES["demand_factor"]) == "unknown",
      "a market-driven rule's sign cannot be read from its config")

# --- classify: the co-incidence test ----------------------------------------
affected = {r["date"] for r in rows if r["ce"] < 1.0}     # the four Mon/Tue dates
res = {c["rule"]: c for c in at.classify(affected, rows, RULES)}

check("day-of-week is CONFIRMED when it covers every affected date and no other",
      res["day_of_week_adjustment"]["verdict"] == "confirmed",
      f"got {res.get('day_of_week_adjustment')}")
check("last-minute is only a CANDIDATE: it also covers unaffected dates",
      res["last_minute_prices"]["verdict"] == "candidate",
      f"got {res.get('last_minute_prices')}")
check("a candidate reports how many unaffected dates it also covers",
      res["last_minute_prices"]["covered_unaffected"] > 0)
check("a market-driven rule can never be confirmed",
      res["demand_factor"]["verdict"] != "confirmed",
      "unknown direction must cap the verdict at candidate")
check("far-out is excluded entirely: it covers none of the affected dates",
      res["far_out_premium"]["verdict"] == "excluded",
      f"got {res.get('far_out_premium')}")
check("every rule gets a verdict, including the off ones",
      len(res) == 6, f"got {len(res)} rules classified, want 6")

# --- summary ----------------------------------------------------------------
print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed.")
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `ModuleNotFoundError: No module named 'attribution'`

- [ ] **Step 4: Write `attribution.py`**

```python
#!/usr/bin/env python3
"""Attribute an observed price to the layer that produced it.

`ce = price / uncustomized_price` is the total effect of the customization stack on a
date. Verified against live data: a listing with every rule off returns ce == 1.000 on
all seven weekdays.

The ratio is exact in TOTAL and does NOT decompose per rule. Several rules overlap the
same date and the far-out premium covers most of a 365-day window, so this module never
claims a rule contributed a specific percentage. It answers a narrower question: which
rules COULD explain the affected dates, and can any of them be pinned down.

  confirmed  the rule covers every affected date and no unaffected date, and its
             direction matches the direction of the effect
  candidate  it covers some affected dates in the right direction, but also covers
             dates that were not affected, so it cannot be separated from its neighbours
  excluded   it covers none of the affected dates

A market-driven rule type (recommended / conservative / aggressive) has no readable sign
in its config, so its direction is "unknown" and it can never reach "confirmed".

Pure functions. No network, no file I/O, no API key.
"""
from __future__ import annotations

from datetime import date

# PriceLabs "no value" markers. Never let these reach arithmetic.
SENTINELS = {-1, -2, -1.0, -2.0, "-1", "-2"}

# Types whose effect is derived from live market data, so the config cannot tell you
# which way the price moved.
MARKET_DRIVEN = {"recommended", "conservative", "aggressive", "moderately_conservative",
                 "moderately_aggressive"}

DOW_KEYS = ["dow_factor_value_mon", "dow_factor_value_tue", "dow_factor_value_wed",
            "dow_factor_value_thu", "dow_factor_value_fri", "dow_factor_value_sat",
            "dow_factor_value_sun"]


def _num(value):
    """Return a float, or None for a sentinel or an unparseable value."""
    if value in SENTINELS:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out in SENTINELS else out


def ce_rows(price_rows: list[dict], today: str) -> list[dict]:
    """One row per usable date: the customization effect and the axes to group it by."""
    base = date.fromisoformat(today)
    out = []
    for row in price_rows:
        raw_date = str(row.get("date") or "")
        price = _num(row.get("price"))
        unc = _num(row.get("uncustomized_price"))
        if not raw_date or price is None or unc is None or unc <= 0:
            continue
        try:
            when = date.fromisoformat(raw_date)
        except ValueError:
            continue
        out.append({
            "date": raw_date,
            "ce": price / unc,
            "dow": when.weekday(),            # 0 = Monday
            "days_out": (when - base).days,
            "month": raw_date[:7],
        })
    return out


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def group_ce(rows: list[dict], key: str) -> dict[str, dict]:
    """Aggregate ce by weekday, lead-time bucket, or month."""
    if key not in ("dow", "lead", "month"):
        raise ValueError(f"group key must be dow, lead or month, got {key!r}")
    buckets: dict[str, list[float]] = {}
    for row in rows:
        if key == "dow":
            label = str(row["dow"])
        elif key == "month":
            label = row["month"]
        else:
            label = _lead_bucket(row["days_out"])
        buckets.setdefault(label, []).append(row["ce"])
    return {k: {"n": len(v), "median_ce": _median(v), "min_ce": min(v), "max_ce": max(v)}
            for k, v in sorted(buckets.items())}


def _lead_bucket(days_out: int) -> str:
    for edge, label in ((0, "0"), (3, "1-3"), (7, "4-7"), (14, "8-14"),
                        (30, "15-30"), (60, "31-60"), (90, "61-90"), (180, "91-180")):
        if days_out <= edge:
            return label
    return "180+"


def rule_covers(rule: str, cfg: dict, row: dict) -> bool:
    """Does this rule's window include this date?

    A rule that is toggled OFF still covers its window. Switching a rule off does not
    mean "no adjustment": it hands the date back to the algorithm's market-driven
    default, which is still an effect that has to be explained.
    """
    if rule == "day_of_week_adjustment":
        value = _num(cfg.get(DOW_KEYS[row["dow"]])) or 0.0
        return value != 0.0 or not cfg.get("dow_factor_on", False)
    if rule == "last_minute_prices":
        dfd = _num(cfg.get("last_min_factor_dfd"))
        return row["days_out"] <= dfd if dfd is not None else True
    if rule == "far_out_premium":
        start = _num(cfg.get("far_out_premium_start"))
        return row["days_out"] >= start if start is not None else True
    # seasonality, demand_factor and custom_seasonal_profile have no date window in
    # their config: they apply across the whole horizon.
    return True


def rule_direction(rule: str, cfg: dict, row: dict | None = None) -> str:
    """down, up, none, or unknown. A market-driven type is always unknown."""
    if rule == "day_of_week_adjustment":
        if row is None:
            return "unknown"
        value = _num(cfg.get(DOW_KEYS[row["dow"]])) or 0.0
        return "down" if value < 0 else "up" if value > 0 else "none"
    if rule == "last_minute_prices":
        kind = cfg.get("last_min_factor_type")
        if kind in MARKET_DRIVEN:
            return "unknown"
        if kind == "none":
            return "none"
        value = _num(cfg.get("last_min_factor_value"))
        return "unknown" if value is None else "down" if value < 0 else "up" if value > 0 else "none"
    if rule == "far_out_premium":
        kind = cfg.get("far_out_premium_type")
        if kind in MARKET_DRIVEN:
            return "unknown"
        if kind == "none":
            return "none"
        value = _num(cfg.get("far_out_premium_value"))
        return "unknown" if value is None else "down" if value < 0 else "up" if value > 0 else "none"
    # seasonality / demand_factor / custom_seasonal_profile: the config carries a tone
    # or a season set, never a single readable sign for the whole horizon.
    return "unknown"


def classify(affected_dates: set, rows: list[dict], rules: dict) -> list[dict]:
    """The co-incidence test. One verdict per rule, never a per-rule percentage."""
    affected_rows = [r for r in rows if r["date"] in affected_dates]
    other_rows = [r for r in rows if r["date"] not in affected_dates]
    # Direction of the effect itself, from the affected dates.
    effect = "down" if affected_rows and _median([r["ce"] for r in affected_rows]) < 1.0 else "up"

    out = []
    for rule, cfg in rules.items():
        hit = [r for r in affected_rows if rule_covers(rule, cfg, r)]
        # An unaffected date only counts against a rule when the rule pushes that date
        # the SAME way as the effect being explained. A day-of-week rule that discounts
        # Mon/Tue and adds a premium on Fri/Sat is not made ambiguous by the Fri/Sat
        # dates: it moves them the other way, so they are not a competing explanation.
        miss = [r for r in other_rows
                if rule_covers(rule, cfg, r)
                and rule_direction(rule, cfg, r) in (effect, "unknown")]
        if not hit:
            out.append({"rule": rule, "verdict": "excluded", "direction": "n/a",
                        "covered_affected": 0, "covered_unaffected": len(miss),
                        "why": "covers none of the affected dates"})
            continue
        directions = {rule_direction(rule, cfg, r) for r in hit}
        direction = directions.pop() if len(directions) == 1 else "unknown"
        if direction == "unknown":
            out.append({"rule": rule, "verdict": "candidate", "direction": "unknown",
                        "covered_affected": len(hit), "covered_unaffected": len(miss),
                        "why": "market-driven or mixed: the config carries no readable sign"})
        elif direction != effect:
            out.append({"rule": rule, "verdict": "excluded", "direction": direction,
                        "covered_affected": len(hit), "covered_unaffected": len(miss),
                        "why": f"moves prices {direction}, the effect is {effect}"})
        elif len(hit) == len(affected_rows) and not miss:
            out.append({"rule": rule, "verdict": "confirmed", "direction": direction,
                        "covered_affected": len(hit), "covered_unaffected": 0,
                        "why": "covers every affected date and no unaffected date"})
        else:
            out.append({"rule": rule, "verdict": "candidate", "direction": direction,
                        "covered_affected": len(hit), "covered_unaffected": len(miss),
                        "why": f"also covers {len(miss)} unaffected dates, cannot be separated"})
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `all checks passed.` and exit 0. If `far_out_premium` comes back `candidate` rather than `excluded`, check that the fixture's affected dates all sit inside 180 days: they do, so `rule_covers` must return False for them.

- [ ] **Step 6: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/fetch/attribution.py \
        revenue-manager-plugin/skills/revenue-manager/fetch/test_fixture_customizations.json \
        revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py
git commit -m "feat: attribution module with the candidate/confirmed co-incidence test

ce is exact in total and does not decompose per rule, so classify() answers which rules
could explain a set of dates rather than how much each contributed. A market-driven rule
type has no readable sign and can never reach confirmed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `reduce_customizations.py` — fetch and reduce the stack

**Files:**
- Create: `revenue-manager-plugin/skills/revenue-manager/fetch/reduce_customizations.py`
- Modify: `revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py`

**Interfaces:**
- Consumes: `attribution.SENTINELS`, `attribution.DOW_KEYS`.
- Produces, used by Tasks 3 and 5:
  - `RULE_COLUMNS = ["rule", "toggle", "type", "value", "window", "effective"]`
  - `normalize_rules(customizations: dict) -> list[dict]` with those keys
  - `rule_window(rule: str, cfg: dict) -> str`
  - `CannotProduce` exception
  - CLI: `python3 reduce_customizations.py --listing <id> [--pms smartbnb] [--ttl-days 7] [--no-cache] [--skip-logs]`

- [ ] **Step 1: Write the failing tests**

Append to `fetch/smoke_test_customizations.py`, immediately before the `# --- summary` block:

```python
# --- reduce_customizations: normalization -----------------------------------
import reduce_customizations as rc  # noqa: E402

norm = {r["rule"]: r for r in rc.normalize_rules(RULES)}
check("all six rules normalize, including the off ones", len(norm) == 6,
      f"got {sorted(norm)}")
check("an OFF rule is flagged in upper case so it cannot be skimmed past",
      norm["seasonality"]["toggle"] == "OFF", f"got {norm['seasonality']['toggle']!r}")
check("an ON rule reads lower case", norm["demand_factor"]["toggle"] == "on")
check("the day-of-week value lists all seven days",
      norm["day_of_week_adjustment"]["value"].count("=") == 7,
      f"got {norm['day_of_week_adjustment']['value']!r}")
check("the last-minute window is expressed in days from check-in",
      norm["last_minute_prices"]["window"] == "<=14d",
      f"got {norm['last_minute_prices']['window']!r}")
check("the far-out window is expressed as days out",
      norm["far_out_premium"]["window"] == ">=180d",
      f"got {norm['far_out_premium']['window']!r}")
check("the effective string is carried through verbatim",
      "discount" in norm["last_minute_prices"]["effective"])
check("a dormant seasonal profile reports its stored season count",
      "2 seasons" in norm["custom_seasonal_profile"]["window"],
      f"got {norm['custom_seasonal_profile']['window']!r}")

# a rule with no effective block must not silently render as empty
bare = {"demand_factor": {"tone_demand_factor_on": True, "tone_demand_factor": "recommended"}}
check("a missing effective block renders as an explicit marker, never blank",
      rc.normalize_rules(bare)[0]["effective"] == "(no effective block returned)",
      f"got {rc.normalize_rules(bare)[0]['effective']!r}")
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `ModuleNotFoundError: No module named 'reduce_customizations'`

- [ ] **Step 3: Write `reduce_customizations.py`**

```python
#!/usr/bin/env python3
"""Reduce the PriceLabs customization stack to one compact table.

    python3 reduce_customizations.py --listing <pricelabs id> [--pms smartbnb]

Five endpoints, one table:
  GET  /v1/customizations/listing?toggled_on=false   the six pricing rules
  GET  /v1/customization_profiles                    shared min-stay / pricing / CICO
  GET  /v1/actions                                   PriceLabs' own issue list
  GET  /v1/nudges/available                          pending vendor suggestions
  POST /v1/logs                                      change history, incl. changes made
                                                     outside this skill

`toggled_on=false` is MANDATORY. The default omits every rule whose toggle is off, and an
off rule is not a no-op: it hands the date back to the algorithm's market-driven default.
Measured live, a listing reading "off" on every lever ran a 40% same-day discount, and
another hid a dormant custom seasonal profile holding two real seasons.

Customizations are stable (measured unchanged over 18 days on a live account) while
override state decays, so the default TTL here is 7 days, not 1.

Prints:
    # source=pricelabs_customizations pulled=... cache=hit|miss listing=... rules=6 on=N off=M ...
    ## rules
    rule,toggle,type,value,window,effective
    ## profiles
    kind,id,name,archived
    ## actions
    action_type,title,current,recommended
    ## nudges
    nudge_id,field,current,suggested,reason,expires
    ## logs
    created_at,action,user_id,summary

Exit 0: printed, including a zero-row section, which is a valid answer.
Exit 2: cannot produce a trustworthy table (no key, API error, unexpected shape).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cache_dir  # noqa: E402
from attribution import DOW_KEYS, _num  # noqa: E402

BASE = "https://api.pricelabs.co"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"  # WAF 403s bare clients
ENV_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
                 "mcp-servers", "pricelabs", ".env"),
    "./mcp-servers/pricelabs/.env", "../mcp-servers/pricelabs/.env",
    "~/.claude/mcp-servers/pricelabs/.env",
]
CACHE_DIR = cache_dir("customizations")

RULE_COLUMNS = ["rule", "toggle", "type", "value", "window", "effective"]
PROFILE_COLUMNS = ["kind", "id", "name", "archived"]
ACTION_COLUMNS = ["action_type", "title", "current", "recommended"]
NUDGE_COLUMNS = ["nudge_id", "field", "current", "suggested", "reason", "expires"]
LOG_COLUMNS = ["created_at", "action", "user_id", "summary"]

ALL_RULES = ["seasonality", "last_minute_prices", "far_out_premium",
             "day_of_week_adjustment", "demand_factor", "custom_seasonal_profile"]

TOGGLE_KEY = {
    "seasonality": "seasonality_customization_on",
    "last_minute_prices": "last_min_factor_on",
    "far_out_premium": "far_out_premium_on",
    "day_of_week_adjustment": "dow_factor_on",
    "demand_factor": "tone_demand_factor_on",
    "custom_seasonal_profile": "custom_seasonal_profile_on",
}
TYPE_KEY = {
    "seasonality": "seasonality_type",
    "last_minute_prices": "last_min_factor_type",
    "far_out_premium": "far_out_premium_type",
    "demand_factor": "tone_demand_factor",
}


class CannotProduce(Exception):
    pass


def resolve_key() -> str:
    for name in ("PRICELABS_API_KEY", "PRICELABS_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    for path in ENV_CANDIDATES:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded):
            for line in open(expanded):
                match = re.match(r"\s*(PRICELABS_API_KEY|PRICELABS_KEY)\s*=\s*(.+?)\s*$", line)
                if match:
                    return match.group(2).strip('"').strip("'")
    raise CannotProduce("No PRICELABS_API_KEY in the environment or in " + ", ".join(ENV_CANDIDATES))


def call(method: str, path: str, key: str, query: dict | None = None,
         body: dict | None = None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-API-Key": key, "User-Agent": UA,
        "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode("utf-8", "replace")
        raise CannotProduce(f"PriceLabs HTTP {exc.code} on {path}: {detail}")
    except Exception as exc:  # noqa: BLE001
        raise CannotProduce(f"PriceLabs request failed on {path}: {exc}")


def rule_window(rule: str, cfg: dict) -> str:
    """How much of the horizon this rule reaches."""
    if rule == "last_minute_prices":
        dfd = _num(cfg.get("last_min_factor_dfd"))
        return f"<={int(dfd)}d" if dfd else "all"
    if rule == "far_out_premium":
        start = _num(cfg.get("far_out_premium_start"))
        return f">={int(start)}d" if start else "all"
    if rule == "day_of_week_adjustment":
        days = [k[-3:] for k in DOW_KEYS if (_num(cfg.get(k)) or 0.0) != 0.0]
        return ",".join(days) if days else "none"
    if rule == "custom_seasonal_profile":
        profile = cfg.get("custom_seasonal_profile") or {}
        count = len(profile.get("seasons") or []) + len(profile.get("non_repeating_seasons") or [])
        return f"{count} seasons"
    return "all"


def rule_value(rule: str, cfg: dict) -> str:
    if rule == "day_of_week_adjustment":
        return " ".join(f"{k[-3:]}={_num(cfg.get(k)) or 0.0:g}" for k in DOW_KEYS)
    for key in ("last_min_factor_value", "far_out_premium_value"):
        if key in cfg:
            value = _num(cfg.get(key))
            return "-" if value is None else f"{value:g}"
    return "-"


def normalize_rules(customizations: dict) -> list[dict]:
    """One row per rule present in the payload, off rules included and flagged."""
    out = []
    for rule in ALL_RULES:
        if rule not in customizations:
            continue
        cfg = customizations[rule] or {}
        on = bool(cfg.get(TOGGLE_KEY[rule], False))
        effective = cfg.get("effective")
        out.append({
            "rule": rule,
            "toggle": "on" if on else "OFF",     # upper case so an off rule cannot be skimmed past
            "type": str(cfg.get(TYPE_KEY.get(rule, ""), "") or "-"),
            "value": rule_value(rule, cfg),
            "window": rule_window(rule, cfg),
            "effective": effective if effective else "(no effective block returned)",
        })
    return out


def flatten_actions(payload) -> list[list]:
    rows = payload if isinstance(payload, list) else (payload or {}).get("data") or []
    out = []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        for action in entry.get("actions") or []:
            meta = action.get("metadata") or {}
            out.append([action.get("action_type", ""), action.get("title", ""),
                        json.dumps(meta.get("current", {}), separators=(",", ":")),
                        json.dumps(meta.get("recommended", {}), separators=(",", ":"))])
    return out


def load_or_fetch(listing: str, pms: str, ttl_days: float, use_cache: bool,
                  skip_logs: bool) -> tuple[dict, str]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"cz_{listing[:8]}_{pms}.json")
    if use_cache and os.path.isfile(path):
        blob = json.load(open(path))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(blob["pulled_at"])).total_seconds()
        if age <= ttl_days * 86400 and bool(blob.get("has_logs")) != skip_logs:
            return blob, "hit"
    key = resolve_key()
    since = (date.today() - timedelta(days=90)).isoformat()
    data = {
        "rules": call("GET", "/v1/customizations/listing", key,
                      {"listing_id": listing, "pms_name": pms, "toggled_on": "false"}),
        "profiles": call("GET", "/v1/customization_profiles", key),
        "actions": call("GET", "/v1/actions", key),
        "nudges": call("GET", "/v1/nudges/available", key),
        "logs": None if skip_logs else call("POST", "/v1/logs", key, None, {
            "log_type": "listing", "listings": [{"listing_id": listing, "pms": pms}],
            "start_date": since, "end_date": date.today().isoformat(), "limit": 50}),
    }
    blob = {"pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "listing": listing, "pms": pms, "has_logs": not skip_logs, "data": data}
    tmp = path + ".tmp"
    json.dump(blob, open(tmp, "w"))
    os.replace(tmp, path)
    return blob, "miss"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listing", required=True)
    ap.add_argument("--pms", default="smartbnb")
    ap.add_argument("--ttl-days", type=float, default=7,
                    help="customizations are stable; 7 days, not 1")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--skip-logs", action="store_true",
                    help="skip POST /v1/logs when the account lacks log access")
    args = ap.parse_args()

    blob, how = load_or_fetch(args.listing, args.pms, args.ttl_days,
                              not args.no_cache, args.skip_logs)
    data = blob["data"]

    customizations = (data["rules"] or {}).get("customizations")
    if not isinstance(customizations, dict):
        raise CannotProduce(f"unexpected customizations shape: {type(customizations).__name__}")
    rules = normalize_rules(customizations)

    profiles_raw = (data["profiles"] or {}).get("profiles") or {}
    profile_rows = [[kind, p.get("id"), p.get("name"), p.get("archived")]
                    for kind, items in profiles_raw.items() for p in (items or [])]
    action_rows = flatten_actions(data["actions"])
    nudges = (data["nudges"] or {}).get("nudges") or []
    log_rows = ((data["logs"] or {}).get("data") or []) if data["logs"] else []

    on = sum(1 for r in rules if r["toggle"] == "on")
    print(f"# source=pricelabs_customizations pulled={blob['pulled_at']} cache={how} "
          f"listing={args.listing[:8]} rules={len(rules)} on={on} off={len(rules) - on} "
          f"profiles={len(profile_rows)} actions={len(action_rows)} nudges={len(nudges)} "
          f"logs={len(log_rows) if data['logs'] else 'skipped'}")

    writer = csv.writer(sys.stdout, lineterminator="\n")
    print("## rules"); writer.writerow(RULE_COLUMNS)
    for r in rules:
        writer.writerow([r[c] for c in RULE_COLUMNS])
    print("## profiles"); writer.writerow(PROFILE_COLUMNS)
    for row in profile_rows:
        writer.writerow(row)
    print("## actions"); writer.writerow(ACTION_COLUMNS)
    for row in action_rows:
        writer.writerow(row)
    print("## nudges"); writer.writerow(NUDGE_COLUMNS)
    for n in nudges:
        writer.writerow([n.get("nudge_id", n.get("id", "")), n.get("field", ""),
                         n.get("current_value", ""), n.get("suggested_value", ""),
                         str(n.get("reason", "")).replace("\n", " "), n.get("expires_at", "")])
    print("## logs"); writer.writerow(LOG_COLUMNS)
    for entry in log_rows:
        writer.writerow([entry.get("created_at", ""), entry.get("action", ""),
                         (entry.get("user") or {}).get("id", ""),
                         str(entry.get("action_label", "")).replace("\n", " ")])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotProduce as exc:
        print(f"CUSTOMIZATIONS UNAVAILABLE: {exc}", file=sys.stderr)
        print("Do not assume the listing has no customizations; say the source could not be read.",
              file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"CUSTOMIZATIONS UNAVAILABLE: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `all checks passed.`

- [ ] **Step 5: Run it live against one listing and read the table**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch
python3 reduce_customizations.py --listing <a real pricelabs listing id> --pms smartbnb
```

Expected: a header line with `rules=6`, then five `##` sections. Confirm `on=` plus `off=` equals 6, and that at least one row shows `OFF`. If `rules=4`, the `toggled_on=false` parameter is not reaching the request, which is the whole point of the module.

- [ ] **Step 6: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/fetch/reduce_customizations.py \
        revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py
git commit -m "feat: reduce_customizations.py, the rule stack in one table

Five endpoints reduced to five CSV sections. toggled_on=false is mandatory: the default
omits every off rule, and off is not a no-op. TTL is 7 days because customizations are
stable while override state decays.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: factcheck the customization table against the raw payload

**Files:**
- Modify: `revenue-manager-plugin/skills/revenue-manager/fetch/factcheck.py`
- Modify: `revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py`

**Interfaces:**
- Consumes: `reduce_customizations.RULE_COLUMNS`, `normalize_rules`.
- Produces: `CUSTOMIZATION_FACTS`, `customization_facts_full(raw)`, `customization_facts_reduced(text)`, and a `"customizations"` entry in `SOURCES`.

Every other reducer is covered by a fact class that re-derives the same named facts from the raw payload through a separate parsing path. Without one, a change to `normalize_rules` can silently alter what the skill reads.

- [ ] **Step 1: Write the failing tests**

Append to `fetch/smoke_test_customizations.py`, before the `# --- summary` block:

```python
# --- factcheck round trip ----------------------------------------------------
import io, contextlib  # noqa: E402
import factcheck as fc  # noqa: E402

check("customizations is a registered fact source", "customizations" in fc.SOURCES)

full = fc.customization_facts_full({"customizations": RULES})
check("full extractor counts all six rules", full["rules_total"] == 6, f"got {full}")
check("full extractor counts the off ones", full["rules_off"] == 2, f"got {full}")
check("full extractor sums the day-of-week magnitude",
      abs(full["dow_abs_total"] - 50.0) < 1e-9,
      f"got {full['dow_abs_total']}, want 50 (10+10+15+15)")
check("full extractor records the dormant season count",
      full["stored_seasons"] == 2, f"got {full['stored_seasons']}")

# render the same rules through the reducer's own table, then read it back
buf = io.StringIO()
buf.write("## rules\n")
w = __import__("csv").writer(buf, lineterminator="\n")
w.writerow(rc.RULE_COLUMNS)
for r in rc.normalize_rules(RULES):
    w.writerow([r[c] for c in rc.RULE_COLUMNS])
reduced = fc.customization_facts_reduced(buf.getvalue())
bad = fc.compare(full, reduced, fc.CUSTOMIZATION_FACTS)
check("every customization fact survives the reducer", not bad, f"changed: {bad}")
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `AttributeError: module 'factcheck' has no attribute 'customization_facts_full'`

- [ ] **Step 3: Add the fact class to `factcheck.py`**

Insert immediately above the `SOURCES = {` line (currently line 793):

```python
# --------------------------------------------------------------- customizations
CUSTOMIZATION_FACTS = ["rules_total", "rules_on", "rules_off", "dow_abs_total",
                       "stored_seasons"]

_CZ_TOGGLE_KEY = {
    "seasonality": "seasonality_customization_on",
    "last_minute_prices": "last_min_factor_on",
    "far_out_premium": "far_out_premium_on",
    "day_of_week_adjustment": "dow_factor_on",
    "demand_factor": "tone_demand_factor_on",
    "custom_seasonal_profile": "custom_seasonal_profile_on",
}
_CZ_DOW_KEYS = ["dow_factor_value_mon", "dow_factor_value_tue", "dow_factor_value_wed",
                "dow_factor_value_thu", "dow_factor_value_fri", "dow_factor_value_sat",
                "dow_factor_value_sun"]


def customization_facts_full(raw: dict) -> dict:
    """Derive the facts straight from the API payload, not from the reducer."""
    rules = raw.get("customizations") or {}
    on = sum(1 for name, cfg in rules.items()
             if (cfg or {}).get(_CZ_TOGGLE_KEY.get(name, ""), False))
    dow = rules.get("day_of_week_adjustment") or {}
    dow_abs = sum(abs(float(dow.get(k) or 0)) for k in _CZ_DOW_KEYS)
    profile = (rules.get("custom_seasonal_profile") or {}).get("custom_seasonal_profile") or {}
    seasons = len(profile.get("seasons") or []) + len(profile.get("non_repeating_seasons") or [])
    return {"rules_total": len(rules), "rules_on": on, "rules_off": len(rules) - on,
            "dow_abs_total": dow_abs, "stored_seasons": seasons}


def customization_facts_reduced(text: str) -> dict:
    """Re-derive the same facts by parsing the reducer's printed table."""
    rows = []
    in_rules = False
    for line in text.splitlines():
        if line.startswith("## rules"):
            in_rules = True
            continue
        if line.startswith("## "):
            in_rules = False
            continue
        if in_rules and line.strip():
            rows.append(line)
    if not rows:
        return {n: None for n in CUSTOMIZATION_FACTS}
    parsed = list(csv.DictReader(io.StringIO("\n".join(rows))))
    on = sum(1 for r in parsed if r["toggle"] == "on")
    dow_abs = 0.0
    seasons = 0
    for r in parsed:
        if r["rule"] == "day_of_week_adjustment":
            for pair in r["value"].split():
                dow_abs += abs(float(pair.split("=")[1]))
        if r["rule"] == "custom_seasonal_profile":
            match = re.match(r"(\d+) seasons", r["window"])
            seasons = int(match.group(1)) if match else 0
    return {"rules_total": len(parsed), "rules_on": on, "rules_off": len(parsed) - on,
            "dow_abs_total": dow_abs, "stored_seasons": seasons}
```

Then add the entry to `SOURCES`:

```python
    "customizations": (CUSTOMIZATION_FACTS, customization_facts_full, customization_facts_reduced),
```

- [ ] **Step 4: Confirm `csv`, `io` and `re` are already imported in `factcheck.py`**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && head -25 factcheck.py | grep -nE "^import|^from"
```

Expected: `csv`, `io` and `re` appear. If any is missing, add it to the import block at the top of the file, not inside the function.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py && python3 smoke_test.py
```

Expected: `all checks passed.` from both. The second command is a regression check: `factcheck.py` is shared, and `smoke_test.py` exercises the other four fact classes.

- [ ] **Step 6: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/fetch/factcheck.py \
        revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py
git commit -m "test: prove the customization table against the raw payload

Five fact classes re-derived through a separate parsing path, matching the pattern used
for prices, neighborhood, calendar, reservations and overrides.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `customization_write.py` — snapshot, validate, merge, echo

**Files:**
- Create: `revenue-manager-plugin/skills/revenue-manager/fetch/customization_write.py`
- Modify: `revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py`

**Interfaces:**
- Consumes: `attribution.DOW_KEYS`, `attribution._num`, `reduce_customizations.CACHE_DIR`.
- Produces, used by Task 7:
  - `merge_dow(current: dict, changes: dict) -> dict`
  - `validate(customizations: dict) -> list[str]`
  - `snapshot_payload(listing_id: str, pms: str, current: dict) -> dict`
  - `write_snapshot(payload: dict, out_dir: str) -> str`
  - `echo_diff(intent: dict, after: dict) -> list[str]`
  - `signed_from_action(action: dict) -> tuple[float, bool]`
  - `RANGES: dict`

This module builds and checks payloads. **It never sends one.** The POST is the operator's approved action in Step 8.

- [ ] **Step 1: Write the failing tests**

Append to `fetch/smoke_test_customizations.py`, before the `# --- summary` block:

```python
# --- customization_write -----------------------------------------------------
import customization_write as cw  # noqa: E402

# the trap: a partial day-of-week write silently zeroes the days you left out
partial = {"dow_factor_value_fri": 20.0, "dow_factor_value_sat": 20.0}
merged = cw.merge_dow(RULES["day_of_week_adjustment"], partial)
check("merge_dow emits all seven days", sum(1 for k in merged if k.startswith("dow_factor_value")) == 7,
      f"got {sorted(k for k in merged if k.startswith('dow_factor_value'))}")
check("merge_dow preserves days the caller did not mention",
      merged["dow_factor_value_mon"] == -10.0,
      "a partial write would have reset Monday to 0")
check("merge_dow applies the days the caller did mention",
      merged["dow_factor_value_fri"] == 20.0)
check("merge_dow keeps the toggle", merged["dow_factor_on"] is True)

# range validation, all-or-nothing
check("a day-of-week value below -75 is rejected",
      cw.validate({"day_of_week_adjustment": dict(merged, dow_factor_value_mon=-80)}),
      "-80 is outside the -75..1000 range and must not reach the API")
check("a day-of-week value of 1000 is allowed",
      not cw.validate({"day_of_week_adjustment": dict(merged, dow_factor_value_mon=1000)}))
check("a last-minute discount over 75 is rejected",
      cw.validate({"last_minute_prices": {"last_min_factor_on": True,
                                          "last_min_factor_type": "linear",
                                          "last_min_factor_value": -80,
                                          "last_min_factor_dfd": 7}}))
check("a far-out start over 999 is rejected",
      cw.validate({"far_out_premium": {"far_out_premium_on": True,
                                       "far_out_premium_type": "linear",
                                       "far_out_premium_value": 10,
                                       "far_out_premium_start": 1500,
                                       "far_out_premium_step": 1}}))
check("a valid payload returns no errors",
      not cw.validate({"day_of_week_adjustment": merged}), f"got {cw.validate({'day_of_week_adjustment': merged})}")
check("an unknown rule name is rejected rather than sent",
      cw.validate({"not_a_rule": {}}))

# the echo check: the API accepts either sign, so compare the effective block
check("echo_diff is silent when the effective block matches intent",
      not cw.echo_diff({"direction": "down", "magnitude": 10},
                       {"effective": "Mon 10% discount"}))
check("echo_diff catches a discount that came back as a premium",
      cw.echo_diff({"direction": "down", "magnitude": 10},
                   {"effective": "Mon 10% premium"}),
      "this is the inverted-sign failure and it returns HTTP 200")
check("echo_diff reports an unreadable effective block rather than passing it",
      cw.echo_diff({"direction": "down", "magnitude": 10}, {}))

# the action sign convention is INFERRED, not proven, so it is gated
value, confirmed = cw.signed_from_action(
    {"action_type": "last_minute_conservative_vs_market",
     "metadata": {"current": {"discount_pct": -12.0}, "recommended": {"discount_pct": 40.0}}})
check("an action's recommended discount is negated into a signed value",
      value == -40.0, f"got {value}, want -40.0 (a 40% discount, not a 40% premium)")
check("the conversion reports that it is unconfirmed",
      confirmed is False, "the convention is inferred and must not be auto-applied")
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `ModuleNotFoundError: No module named 'customization_write'`

- [ ] **Step 3: Write `customization_write.py`**

```python
#!/usr/bin/env python3
"""Build and check a PriceLabs customization write. Never send one.

Every function here is a guard against a measured failure that returns HTTP 200:

  merge_dow           days omitted from a write default to 0, they do NOT keep their
                      previous value, so a Fri/Sat write wipes Mon-Thu
  validate            one invalid value rejects the whole request, so ranges are checked
                      before the payload is built, not after a partial mental model of it
  snapshot_payload    the rollback. The exact object needed to re-POST the prior state
  echo_diff           the sign is accepted either way, because a premium is a legitimate
                      setting. Only the effective block proves which way it went
  signed_from_action  get_actions uses two conventions in one object: current.discount_pct
                      is the stored SIGNED value, recommended.discount_pct is a positive
                      MAGNITUDE. Copying the recommendation writes a premium where a
                      discount was meant

The POST itself is the operator's approved action in Step 8. This module has no network code.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attribution import DOW_KEYS, _num  # noqa: E402

VALID_RULES = {"seasonality", "last_minute_prices", "far_out_premium",
               "day_of_week_adjustment", "demand_factor", "custom_seasonal_profile"}

RANGES = {
    "dow": (-75.0, 1000.0),
    "last_min_discount": (0.0, 75.0),      # magnitude when the value is negative
    "last_min_premium": (0.0, 500.0),      # magnitude when the value is positive
    "last_min_dfd": (1.0, 90.0),
    "far_out_value": (-30.0, 500.0),
    "far_out_start": (1.0, 999.0),
    "far_out_step": (1.0, 999.0),
}

# Fields the account may not be entitled to. Including one rejects the WHOLE request
# with ERR-FEATURE-NOT-ENABLED, so they are refused locally rather than at the API.
FEATURE_GATED = {"hotel_compset_type", "hotel_wt", "non_repeating_seasons",
                 "price_type_non_repeating"}


def merge_dow(current: dict, changes: dict) -> dict:
    """Return a FULL seven-day object. Never send a partial day-of-week write."""
    out = {"dow_factor_on": bool(current.get("dow_factor_on", True))}
    for key in DOW_KEYS:
        if key in changes:
            out[key] = changes[key]
        else:
            out[key] = _num(current.get(key)) or 0.0
    return out


def _in_range(value, bounds, label, errors):
    number = _num(value)
    if number is None:
        errors.append(f"{label}: {value!r} is not a number")
        return
    low, high = bounds
    if not (low <= number <= high):
        errors.append(f"{label}: {number:g} is outside {low:g}..{high:g}")


def validate(customizations: dict) -> list[str]:
    """Return every problem found. An empty list means the payload is safe to send."""
    errors: list[str] = []
    for rule, cfg in customizations.items():
        if rule not in VALID_RULES:
            errors.append(f"{rule}: not a customization name PriceLabs accepts")
            continue
        cfg = cfg or {}
        for field in cfg:
            if field in FEATURE_GATED:
                errors.append(f"{rule}.{field}: feature-gated, rejects the whole request")

        if rule == "day_of_week_adjustment":
            present = [k for k in DOW_KEYS if k in cfg]
            if cfg.get("dow_factor_on") and len(present) != 7:
                errors.append("day_of_week_adjustment: all seven days must be sent; "
                              f"got {len(present)}. Omitted days reset to 0")
            for key in present:
                _in_range(cfg[key], RANGES["dow"], f"day_of_week_adjustment.{key}", errors)

        elif rule == "last_minute_prices" and cfg.get("last_min_factor_on"):
            kind = cfg.get("last_min_factor_type")
            if kind in ("linear", "linear_gradual", "fixed"):
                value = _num(cfg.get("last_min_factor_value"))
                if value is None:
                    errors.append("last_minute_prices: last_min_factor_value is required "
                                  f"for type {kind}")
                elif kind != "fixed":
                    bounds = RANGES["last_min_discount"] if value < 0 else RANGES["last_min_premium"]
                    _in_range(abs(value), bounds, "last_minute_prices.last_min_factor_value", errors)
                _in_range(cfg.get("last_min_factor_dfd"), RANGES["last_min_dfd"],
                          "last_minute_prices.last_min_factor_dfd", errors)

        elif rule == "far_out_premium" and cfg.get("far_out_premium_on"):
            kind = cfg.get("far_out_premium_type")
            if kind in ("linear", "fix"):
                _in_range(cfg.get("far_out_premium_value"), RANGES["far_out_value"],
                          "far_out_premium.far_out_premium_value", errors)
                _in_range(cfg.get("far_out_premium_start"), RANGES["far_out_start"],
                          "far_out_premium.far_out_premium_start", errors)
                if kind == "linear":
                    _in_range(cfg.get("far_out_premium_step"), RANGES["far_out_step"],
                              "far_out_premium.far_out_premium_step", errors)
            elif kind == "fixed":
                errors.append("far_out_premium: the enum is `fix`, not `fixed` "
                              "(last_minute uses `fixed`; they differ)")
    return errors


def snapshot_payload(listing_id: str, pms: str, current: dict) -> dict:
    """The exact object that restores the prior state. This is the kill switch."""
    return {"listing_id": listing_id, "pms_name": pms, "customizations": current}


def write_snapshot(payload: dict, out_dir: str) -> str:
    """Persist the rollback payload and return its path. Never overwrite a snapshot."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    listing = str(payload.get("listing_id", "unknown"))[:8]
    path = os.path.join(out_dir, f"snapshot_{listing}_{stamp}.json")
    with open(path, "x") as handle:            # x: refuse to clobber an existing snapshot
        json.dump(payload, handle, indent=2)
    return path


def echo_diff(intent: dict, after: dict) -> list[str]:
    """Compare what you meant against what the dashboard now renders.

    `intent` is {"direction": "down"|"up", "magnitude": <positive number>}.
    `after` is the rule object re-read after the write, carrying its `effective` block.
    """
    effective = (after or {}).get("effective")
    if not effective:
        return ["no effective block returned; the write cannot be confirmed"]
    text = str(effective).lower()
    saw_down = "discount" in text
    saw_up = "premium" in text
    problems = []
    if intent["direction"] == "down" and not saw_down:
        problems.append(f"intended a discount, effective reads {effective!r}")
    if intent["direction"] == "up" and not saw_up:
        problems.append(f"intended a premium, effective reads {effective!r}")
    if intent["direction"] == "down" and saw_up and not saw_down:
        problems.append("SIGN INVERTED: a discount was written as a premium")
    magnitudes = [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
    if magnitudes and not any(abs(m - float(intent["magnitude"])) < 0.51 for m in magnitudes):
        problems.append(f"intended {intent['magnitude']}%, effective shows {magnitudes}")
    return problems


def signed_from_action(action: dict) -> tuple[float, bool]:
    """Convert an action's recommendation into a signed customization value.

    Returns (value, confirmed). `confirmed` is always False: the convention is inferred
    from the stored value matching `current` exactly plus the meaning of the action type,
    and it has not been proven with a write. A caller must not auto-apply an unconfirmed
    value. See references/pricelabs-gotchas.md, "two sign conventions".
    """
    meta = action.get("metadata") or {}
    recommended = _num((meta.get("recommended") or {}).get("discount_pct"))
    if recommended is None:
        raise ValueError("action has no recommended.discount_pct")
    kind = str(action.get("action_type", ""))
    if "last_minute" in kind:
        return -abs(recommended), False
    return recommended, False
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch && python3 smoke_test_customizations.py
```

Expected: `all checks passed.`

- [ ] **Step 5: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/fetch/customization_write.py \
        revenue-manager-plugin/skills/revenue-manager/fetch/smoke_test_customizations.py
git commit -m "feat: customization write guards -- merge, validate, snapshot, echo

Each function guards a measured failure that returns HTTP 200: omitted day-of-week days
reset to 0, one bad value rejects the whole call, the sign is accepted either way, and
get_actions uses two different sign conventions in the same object. No network code: the
POST stays the operator's approved action in Step 8.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: SKILL.md Step 4c — pull the stack

**Files:**
- Modify: `revenue-manager-plugin/skills/revenue-manager/SKILL.md` (insert after Step 4a, before `## Step 4.8`)

**Interfaces:**
- Consumes: the `reduce_customizations.py` CLI from Task 2.
- Produces: the `## rules` / `## actions` / `## nudges` / `## logs` blocks that Steps 5.5 and 7 read.

- [ ] **Step 1: Insert the step**

Insert immediately before the line `## Step 4.8 — Named comps via the reducer, never the raw MCP (AirROI, optional)`:

````markdown
### Step 4c — The customization stack (the rules that produced the curve)

**Do not call `get_customizations` directly.** Run the reducer, once per listing:

```bash
cd <plugin>/skills/revenue-manager/fetch
python3 reduce_customizations.py --listing <id> --pms <pms>
```

It prints five sections: `## rules`, `## profiles`, `## actions`, `## nudges`, `## logs`.
Exit 2 means the stack could not be read this run. **Say so. Never report a listing as
having no customizations because the call failed.**

**Why this exists.** Every price you read in Step 4.0 is the output of six rules you
otherwise cannot see. Measured on a live account: one listing had 9 floor-pinned dates,
7 of them on the two weekdays carrying a -10% day-of-week rule, and the analysis argued
about the minimum price instead. A second listing read "off" on every lever and ran a
40% same-day discount.

**`toggled_on=false` is not optional and the reducer sets it.** The default response omits
every rule whose toggle is off. On a live listing that meant 4 rules returned instead of 6,
and one of the two hidden rules held a dormant custom seasonal profile with real season
values in it. **A rule showing `OFF` in the table is not neutral:** switching a rule off
hands the date back to the algorithm's market-driven default.

**The cache is deliberately long.** Customizations were unchanged over 18 days on a live
account while override state decayed 846 dates in 12. The reducer's TTL is 7 days. Pass
`--no-cache` when you have reason to think a rule just changed, and check the `## logs`
section, which tells you whether it did.

**Read `## actions` before forming your own diagnosis.** That is PriceLabs' own issue list
per listing: missing base price, occupancy adjustments off, last-minute or min-stay off
market, too many blocked dates. Report both yours and theirs. Where they agree, confidence
is high. Where they disagree, say so plainly. Never silently override the vendor.

**`## logs` is the only view of changes made outside this skill.** The Supabase audit trail
records only what this skill did. An operator who edited a base price in the PriceLabs
dashboard is invisible to it. Step 7's "prior attempts" line reads this section.
````

- [ ] **Step 2: Verify the file still parses as the runbook expects**

```bash
cd revenue-manager-plugin/skills/revenue-manager
grep -n "^## Step\|^### Step" SKILL.md
```

Expected: `### Step 4c` appears between `### Step 4a` and `## Step 4.8`, and no other step header changed.

- [ ] **Step 3: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/SKILL.md
git commit -m "feat: Step 4c pulls the customization stack, actions, nudges and logs

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: SKILL.md Step 5.5 and the Step 7 approval card

**Files:**
- Modify: `revenue-manager-plugin/skills/revenue-manager/SKILL.md` (insert before `## Step 6`; edit the card in Step 7)

**Interfaces:**
- Consumes: Step 4c's output, `attribution.py` from Task 1.
- Produces: the `Layer:` and `Blast radius:` lines other steps and the audit row in Task 7 depend on.

- [ ] **Step 1: Insert Step 5.5**

Insert immediately before the line `## Step 6 — Apply the STR revenue framework`:

````markdown
## Step 5.5 — Attribute the layer before you name a lever

**A price complaint is a layer question before it is a number question.** Work out which
layer produced the behaviour, then propose the lever that owns that layer. Changing a
number at the wrong layer is the failure this step exists to prevent.

`ce = price / uncustomized_price` is the total effect of the customization stack on a
date, and it is exact: a listing with every rule off returns 1.000 on all seven weekdays.
`fetch/attribution.py` computes it and groups it by weekday, lead time and month.

| Symptom | Layer that could own it | Evidence that decides |
|---|---|---|
| Date pinned at the floor | base, a rule pushing down, or the min itself | `ce` on that date, and whether a rule's window covers it |
| Same-day collapse | last minute, on or off-and-market-driven | `ce` by days to check-in, plus the effective string |
| One weekday systematically low | day of week | `ce` grouped by weekday |
| Far dates flat or high | far-out premium | `ce` by days out |
| A whole season wrong | seasonality or the custom profile | `ce` by month vs the neighborhood's seasonal shape |
| Price ignores the market | demand factor | `ce` variance vs neighborhood variance |
| One date odd, neighbours fine | override | the Step 4 override reducer row |
| PMS disagrees with PriceLabs | sync | the Step 4.9 ratio. **Never fix this with a price** |
| Guest sees a different number | channel markup | Step 3.2 |

### The co-incidence test

**`ce` is exact in total and does NOT decompose per rule.** Several rules overlap the same
date and the far-out premium covers most of a 365-day window. So every attribution carries
a verdict, and `attribution.classify()` produces it:

- **confirmed** — the rule covers every affected date and no unaffected date, and its
  direction matches the effect.
- **candidate** — it covers some affected dates in the right direction but also covers
  dates that were not affected.
- **excluded** — it covers none of them, or it moves prices the other way.

A market-driven rule type (`recommended`, `conservative`, `aggressive`) has no readable
sign in its config, so it can never be confirmed.

**Never write "the day-of-week rule cost you 10% on this date."** Write "these dates run
12% under the uncustomized price, three rules cover them, I cannot separate them."

### Before proposing a rule change

A rule change moves every date in its window, forward, until someone changes it back.

1. **Count and name the blast radius**: dates in the horizon the window covers, and how
   many are open.
2. **The pattern must hold.** One bad Tuesday is not a day-of-week problem.
3. **Compare occupancy inside the window against outside it.** If those dates are booking
   fine, the rule is working.

### The lever ladder

Prefer the smallest instrument that fixes the diagnosed layer:

1. **Accept a nudge** (Step 4c `## nudges`). One listing, one field, a vendor-generated value.
2. **Date override.** Bounded and obviously reversible.
3. **Bounds**, min or max.
4. **Base price.**
5. **One customization rule.**
6. **Custom seasonal profile.** A write replaces the entire stored season set.
7. **Account level, group level, or a shared profile.** A portfolio change, and **out of
   scope for this version**: surface it, explain it, never write it.

**One lever per diagnosis per run.** Never a rule change and a base change on the same
symptom in the same run, or nothing downstream can attribute which one worked.
````

- [ ] **Step 2: Replace the Step 7 approval card**

Find the fenced block in Step 7 that begins `Property:        <name>  (<currency>)` and ends with the `Flags:` line. Replace the whole block with:

```
Property:        <name>  (<currency>)
Change:          <field> from <old (PMS calendar = ground truth)> to <new>   (<+/- % move>)
Layer:           <base | bounds | customization:<rule> | override | sync | markup>
                 <confirmed | candidate>: <why, from Step 5.5>
Blast radius:    <N dates in the horizon, M of them open>   <"this date only" for an override>
Nearest bound:   min <min> / max <max>   <flag if outside or within 5%>
Comp count:      <N>  (<same-bedroom subset>)
Net / Ask / Cleared: net <calendar> / ask(airbnb) <net x (1+markup)> / cleared ADR <realized>
Reasoning:       <plain-language inputs — comps, pacing/STLY, events, lead time, orphan>
Prior attempts:  <from Step 4c `## logs` AND pricelabs_change_log, if any>
Vendor says:     <matching row from Step 4c `## actions`, or "no action raised">
Expected impact: <occupancy % / RevPAR direction>
Flags:           <large-move / thin-comp / currency / stale-data / out-of-bound / 
                  unconfirmed-attribution, if any>
```

- [ ] **Step 3: Verify both edits landed**

```bash
cd revenue-manager-plugin/skills/revenue-manager
grep -n "Step 5.5\|^Layer:\|^Blast radius:\|^Vendor says:" SKILL.md
```

Expected: the Step 5.5 header plus the three new card lines.

- [ ] **Step 4: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/SKILL.md
git commit -m "feat: Step 5.5 layer attribution, and Layer/Blast radius on the approval card

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: SKILL.md Step 8 write path and the Step 9 audit row

**Files:**
- Modify: `revenue-manager-plugin/skills/revenue-manager/SKILL.md` (Step 8)
- Modify: `revenue-manager-plugin/skills/revenue-manager/references/audit-write.md`

**Interfaces:**
- Consumes: every function from Task 4.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Add the customization write path to Step 8**

In Step 8, find the numbered list item that begins `2. Push via the detected stack's mutation tool`. Insert the following as a new block immediately after that item's sub-bullets, before item `3. Confirm a successful response.`:

````markdown
   - **Customization rules follow their own path.** Never hand-compose one. In order:

     1. **Snapshot.** `customization_write.snapshot_payload()` then `write_snapshot()`.
        Record the returned path; it is the rollback and it goes in the audit row.
        Rolling back is re-POSTing that file, unchanged.
     2. **Merge to a full object.** For day of week, `customization_write.merge_dow()`.
        **Days omitted from a write reset to 0, they do not keep their previous value.**
        For `custom_seasonal_profile`, send every season: a write replaces the whole set.
     3. **Validate.** `customization_write.validate()`. A non-empty return means do not
        send. One invalid value rejects the entire request, so a partial payload is worse
        than none: the keys that were valid still apply alongside the one that was not.
     4. **Send** the approved change through `update_customizations`.
     5. **Echo check, mandatory.** Re-read the rule and run
        `customization_write.echo_diff()`. **The sign is accepted either way**, because a
        premium is a legitimate setting, so a 200 does not mean the write did what you
        meant. Only the `effective` block proves the direction. If `echo_diff` returns
        anything, say so immediately and offer the rollback.

   - **To suppress a rule, send its type `none`** (or `no demand factor` for the demand
     factor) **with the toggle ON.** Switching the toggle off is not suppression: it hands
     the date to the market-driven default, and it **resets** the stored config for
     last-minute and far-out.
   - **Never write from an action's `recommended` value without negating it first.**
     `get_actions` uses two conventions in one object: `current.discount_pct` is the stored
     signed value, `recommended.discount_pct` is a positive magnitude.
     `customization_write.signed_from_action()` handles it and returns `confirmed=False`,
     because the convention is inferred and not proven. **Do not auto-apply an unconfirmed
     value.** See `references/pricelabs-gotchas.md`.
   - **Out of scope in this version:** account-level and group-level customizations, group
     overrides, and shared min-stay profiles. Surface them and explain them. Do not write
     them. A shared profile is an account object and changing it changes every listing
     attached to it.
````

- [ ] **Step 2: Add the layer and snapshot columns to the audit reference**

In `references/audit-write.md`, replace the `pricelabs_change_log` INSERT block with:

````markdown
### Per change → 1 row in `pricelabs_change_log`
```sql
INSERT INTO pricelabs_change_log
  (property_name, listing_id, change_type, field_changed,
   old_value, new_value, reason, changed_by, notes)
VALUES
  ($1, $2, $3, $4, $5::text, $6::text, $7, 'revenue-manager-skill', $8);
```
One row per individual field change (base, min, max, a bound override, and each DSO/override date counts as its own row).

**For a customization change**, `change_type` is `customization`, `field_changed` is the
rule name (for example `day_of_week_adjustment`), and `notes` MUST carry three things:

- the **layer verdict** from Step 5.5, `confirmed` or `candidate`, and which rules were
  candidates if it was not confirmed
- the **blast radius** that was shown at the approval gate
- the **snapshot path** returned by `customization_write.write_snapshot()`, because that
  file is the rollback

```
notes: "layer=customization:day_of_week_adjustment verdict=confirmed
        blast=104 dates (61 open) snapshot=~/.cache/revenue-manager/snapshots/snapshot_ab12cd34_20260918T204501Z.json
        echo=ok"
```

Without the snapshot path the change is not reversible by anyone who was not in the
session. Treat a missing path as a failed audit write.
````

- [ ] **Step 3: Verify both edits landed**

```bash
cd revenue-manager-plugin/skills/revenue-manager
grep -n "customization_write\." SKILL.md references/audit-write.md
```

Expected: `snapshot_payload`, `write_snapshot`, `merge_dow`, `validate`, `echo_diff` and `signed_from_action` all appear. Every name must match a function defined in Task 4.

- [ ] **Step 4: Commit**

```bash
git add revenue-manager-plugin/skills/revenue-manager/SKILL.md \
        revenue-manager-plugin/skills/revenue-manager/references/audit-write.md
git commit -m "feat: Step 8 customization write path and the audit snapshot column

Snapshot, merge to a full object, validate, send, echo check. The audit row carries the
layer verdict, the blast radius and the rollback path, because a change nobody can reverse
is not audited.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Leak scan, version bump, install and verify

**Files:**
- Modify: `revenue-manager-plugin/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run both offline test suites**

```bash
cd revenue-manager-plugin/skills/revenue-manager/fetch
python3 smoke_test.py && python3 smoke_test_customizations.py
```

Expected: `all checks passed.` from both, exit 0. **Do not continue past a failure.**

- [ ] **Step 2: Run the leak scan**

```bash
cd "$(git rev-parse --show-toplevel)"
/usr/bin/grep -rlEi -f _private/leak-patterns.txt \
  --include="*.md" --include="*.py" --include="*.json" . 2>/dev/null \
  | grep -v "^./_private/" | grep -v "^./docs/pricelabs/" | grep -v node_modules \
  || echo "CLEAN"
```

Expected: `CLEAN`. The repo is public. If anything prints, replace the identifier with a
generic descriptor and re-run before committing.

**The pattern list lives in `_private/leak-patterns.txt`, which is gitignored, and it must
stay there.** It is a list of client property names and account identifiers, so writing the
pattern into a committed file leaks exactly what the scan exists to catch. That mistake was
made once while writing this plan: the pattern was inlined here, and the names reached the
public remote before the scan output was read. Recovered by rewriting the commit and
force-pushing. **Read the scan output before you commit, never in the same `&&` chain as
the commit.**

- [ ] **Step 3: Bump the version in both files together**

```bash
cd "$(git rev-parse --show-toplevel)"
sed -i '' 's/4\.2\.0-rc9/4.2.0-rc10/' \
  revenue-manager-plugin/.claude-plugin/plugin.json .claude-plugin/marketplace.json
grep -n version revenue-manager-plugin/.claude-plugin/plugin.json .claude-plugin/marketplace.json
```

Expected: both read `4.2.0-rc10`. The plugin cache is version-keyed: if the string does not change, `claude plugin update` is a silent no-op and the installed copy stays stale.

- [ ] **Step 4: Add the changelog entry**

Insert at the top of `CHANGELOG.md`, immediately under `# Changelog`:

```markdown
## 4.2.0-rc10 (unreleased)

- The customization layer. Step 4c pulls the six pricing rules (with `toggled_on=false`,
  which is the only way to see a rule that is switched off), the shared profiles,
  `get_actions`, pending nudges and the PriceLabs change log.
- Step 5.5 attributes an observed price to the layer that produced it before any lever is
  named, with a confirmed/candidate verdict. `ce` is exact in total and never decomposed
  per rule.
- Step 7's approval card carries `Layer:`, `Blast radius:` and `Vendor says:`.
- Step 8 gains the customization write path: snapshot, full-object merge, range validation,
  send, mandatory echo check. Account-level, group-level and shared-profile writes stay
  out of scope.
- `fetch/attribution.py`, `fetch/reduce_customizations.py`, `fetch/customization_write.py`,
  `fetch/smoke_test_customizations.py`, and a `customizations` fact class in `factcheck.py`.
- Plan: `docs/superpowers/plans/2026-09-18-pricelabs-customization-layer.md`.
  Spec: `docs/superpowers/specs/2026-09-18-pricelabs-customization-layer-design.md`.
```

- [ ] **Step 5: Commit, push and install**

```bash
cd "$(git rev-parse --show-toplevel)"
git add -A
git commit -m "rc10: the customization layer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push origin feat/token-reducer
claude plugin update revenue-manager@revenue-manager-local
```

Expected: `updated from 4.2.0-rc9 to 4.2.0-rc10`.

- [ ] **Step 6: Verify the installed copy carries the new modules**

```bash
C=~/.claude/plugins/cache/revenue-manager-local/revenue-manager/4.2.0-rc10/skills/revenue-manager
ls $C/fetch/attribution.py $C/fetch/reduce_customizations.py $C/fetch/customization_write.py
grep -c "Step 4c\|Step 5.5\|Blast radius" $C/SKILL.md
cd $C/fetch && python3 smoke_test_customizations.py | tail -2
```

Expected: all three files listed, the grep count is at least 3, and the smoke test passes from inside the installed cache. A file that exists in the repo but not in the cache means the plugin manifest does not ship it.

- [ ] **Step 7: End-to-end run against one live listing**

```bash
cd ~/.claude/plugins/cache/revenue-manager-local/revenue-manager/4.2.0-rc10/skills/revenue-manager/fetch
python3 reduce_customizations.py --listing <a real pricelabs listing id> --pms smartbnb --no-cache
```

Expected: `rules=6` in the header, five `##` sections, exit 0. Then confirm the whole runbook loads by starting a fresh session and invoking `/revenue-manager`. A restart is required: the session holds the old version until it reloads.

---

## Self-Review

**Spec coverage.** Spec section 3 (what gets read) is Tasks 2 and 5. Section 4 and 4.1 (attribution, the co-incidence test) are Tasks 1 and 6. Section 5 (lever ladder) is Task 6. Section 6 (blast radius gate) is Task 6. Section 7 and 7.1 (write safety, the sign conventions) are Tasks 4 and 7. Section 8 (vendor first) is Task 5 for `actions` and `logs`, Task 6 for the card line. Section 9 (runbook changes) is Tasks 5, 6, 7 and the audit half of 7. Section 10 (scope) is enforced in Task 7's "out of scope" bullet. Section 11 (coverage of the full API) shipped in rc9 and needs no task. Section 12 risk 2 (rollback must be built with the feature) is Task 4's `write_snapshot` plus Task 7's audit column. Risk 4 (the sign convention is inferred) is Task 4's `signed_from_action` returning `confirmed=False` and Task 7's "do not auto-apply" instruction.

**Gap found and closed.** The spec's Step 9 audit change had no task when the plan was first drafted; it is now Task 7 Step 2.

**Type consistency.** `_num` and `DOW_KEYS` are defined once in `attribution.py` (Task 1) and imported by `reduce_customizations.py` (Task 2) and `customization_write.py` (Task 4). `RULE_COLUMNS` is defined in Task 2 and consumed by the Task 3 test. The toggle-key map is deliberately duplicated in `factcheck.py` as `_CZ_TOGGLE_KEY` rather than imported, because a fact-class extractor that imports the reducer's own constants cannot catch a change to them: the whole point is a separate parsing path. That duplication is intentional and is called out here so a later reader does not "fix" it.

**Placeholder scan.** No TBD, TODO, or "handle edge cases". Every code step carries runnable code. The two live-run steps take a listing id the operator supplies, which is an input, not a placeholder.
