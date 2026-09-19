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

# --- off-handling for day_of_week_adjustment --------------------------------
# Create a copy with dow_factor_on = False, leaving stale per-day values untouched
dow_off = {k: v for k, v in RULES["day_of_week_adjustment"].items()}
dow_off["dow_factor_on"] = False
check("off day-of-week still covers a day with value=0",
      at.rule_covers("day_of_week_adjustment", dow_off, wed))
check("off day-of-week returns unknown direction for a day with negative stale value",
      at.rule_direction("day_of_week_adjustment", dow_off, mon) == "unknown",
      "an off rule is market-driven, so direction is unknowable")

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

# Test that off day_of_week_adjustment cannot be confirmed
rules_with_off_dow = {
    "day_of_week_adjustment": dow_off,
    "last_minute_prices": RULES["last_minute_prices"],
    "far_out_premium": RULES["far_out_premium"],
    "demand_factor": RULES["demand_factor"],
    "seasonality": RULES["seasonality"],
    "custom_seasonal_profile": RULES["custom_seasonal_profile"],
}
res_off = {c["rule"]: c for c in at.classify(affected, rows, rules_with_off_dow)}
check("off day-of-week is NOT confirmed (unknown direction caps at candidate)",
      res_off["day_of_week_adjustment"]["verdict"] != "confirmed",
      f"got {res_off['day_of_week_adjustment']['verdict']}")

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

# an embedded newline in vendor free text must not grow a fake extra CSV row
messy = {"seasonality": {"seasonality_customization_on": True,
                         "effective": "line one\nline two"}}
check("an embedded newline in effective is scrubbed to a single line",
      "\n" not in rc.normalize_rules(messy)[0]["effective"],
      f"got {rc.normalize_rules(messy)[0]['effective']!r}")

# --- clean_text: the shared free-text helper behind all five vendor-text columns ----
check("clean_text renders an explicit None as the fallback, not the string 'None'",
      rc.clean_text(None) == "", f"got {rc.clean_text(None)!r}")
check("clean_text renders an empty string as the fallback too",
      rc.clean_text("") == "", f"got {rc.clean_text('')!r}")
check("clean_text honors a custom fallback for None",
      rc.clean_text(None, "(no effective block returned)") == "(no effective block returned)")
check("clean_text scrubs an embedded newline in real text",
      rc.clean_text("line one\nline two") == "line one line two",
      f"got {rc.clean_text('line one' + chr(10) + 'line two')!r}")

# title (flatten_actions) and name (flatten_profiles): the two sites the reviewer
# proved print the literal text "None" for an explicit null. Both must now render an
# empty cell for a null AND for a missing key -- .get() makes those indistinguishable
# by the time clean_text sees them, so both need their own check.
actions_null_title = {"data": [{"actions": [{"action_type": "x", "title": None, "metadata": {}}]}]}
actions_missing_title = {"data": [{"actions": [{"action_type": "x", "metadata": {}}]}]}
check("flatten_actions renders an explicit null title as an empty cell, not 'None'",
      rc.flatten_actions(actions_null_title)[0][1] == "",
      f"got {rc.flatten_actions(actions_null_title)[0][1]!r}")
check("flatten_actions renders a missing title as an empty cell",
      rc.flatten_actions(actions_missing_title)[0][1] == "",
      f"got {rc.flatten_actions(actions_missing_title)[0][1]!r}")

profiles_null_name = {"profiles": {"minstay": [{"id": 1, "name": None, "archived": False}]}}
profiles_missing_name = {"profiles": {"minstay": [{"id": 1, "archived": False}]}}
check("flatten_profiles renders an explicit null name as an empty cell, not 'None'",
      rc.flatten_profiles(profiles_null_name)[0][2] == "",
      f"got {rc.flatten_profiles(profiles_null_name)[0][2]!r}")
check("flatten_profiles renders a missing name as an empty cell",
      rc.flatten_profiles(profiles_missing_name)[0][2] == "",
      f"got {rc.flatten_profiles(profiles_missing_name)[0][2]!r}")

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

# --- summary ----------------------------------------------------------------
print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed.")
