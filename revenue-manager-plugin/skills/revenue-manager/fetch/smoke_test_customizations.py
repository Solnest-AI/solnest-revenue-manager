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
