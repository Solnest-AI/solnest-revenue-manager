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

# --- fix round 1, finding 1: sums/counts are blind to mislabeling -----------
# dow_abs_total is a sum and rules_on/off are counts. Both are invariant under
# permutation: swap which day carries which value, or which two rules are off, and the
# number does not move. Only a digest over the actual (label, value) pairs can see it.

swap_buf = io.StringIO()
swap_buf.write("## rules\n")
sw = __import__("csv").writer(swap_buf, lineterminator="\n")
sw.writerow(rc.RULE_COLUMNS)
for r in rc.normalize_rules(RULES):
    row = dict(r)
    if row["rule"] == "day_of_week_adjustment":
        # simulate a reducer bug that trades Monday's and Friday's printed values while
        # every day label stays in its normal position: abs(-10)+abs(15) either way, so
        # dow_abs_total cannot see this, but dow_digest must.
        row["value"] = "mon=15 tue=-10 wed=0 thu=0 fri=-10 sat=15 sun=0"
    sw.writerow([row[c] for c in rc.RULE_COLUMNS])
swap_reduced = fc.customization_facts_reduced(swap_buf.getvalue())
check("a day-value permutation leaves dow_abs_total unchanged (the blind spot)",
      abs(swap_reduced["dow_abs_total"] - full["dow_abs_total"]) < 1e-9,
      f"full={full['dow_abs_total']} swapped={swap_reduced['dow_abs_total']}")
swap_bad = fc.compare(full, swap_reduced, fc.CUSTOMIZATION_FACTS)
check("but dow_digest catches the permutation",
      any(b.startswith("dow_digest") for b in swap_bad), f"got bad={swap_bad}")

rules_swap_buf = io.StringIO()
rules_swap_buf.write("## rules\n")
rsw = __import__("csv").writer(rules_swap_buf, lineterminator="\n")
rsw.writerow(rc.RULE_COLUMNS)
for r in rc.normalize_rules(RULES):
    row = dict(r)
    if row["rule"] == "seasonality":             # really OFF in RULES
        row["toggle"] = "on"
    elif row["rule"] == "demand_factor":          # really on in RULES
        row["toggle"] = "OFF"
    rsw.writerow([row[c] for c in rc.RULE_COLUMNS])
rules_swap_reduced = fc.customization_facts_reduced(rules_swap_buf.getvalue())
check("swapping which two rules are off leaves rules_on/rules_off unchanged (the blind spot)",
      rules_swap_reduced["rules_on"] == full["rules_on"]
      and rules_swap_reduced["rules_off"] == full["rules_off"],
      f"got on={rules_swap_reduced['rules_on']} off={rules_swap_reduced['rules_off']}")
rules_swap_bad = fc.compare(full, rules_swap_reduced, fc.CUSTOMIZATION_FACTS)
check("but rules_digest catches which specific rules moved",
      any(b.startswith("rules_digest") for b in rules_swap_bad), f"got bad={rules_swap_bad}")

# --- fix round 1, finding 2: :g print-precision must not cause a false mismatch --
# the reducer prints each day value with :g (6 significant digits). Comparing a raw
# full-precision float against that truncation with exact != is a false mismatch waiting
# to happen. PRECISION exists for exactly this; dow_abs_total and dow_digest must use it.

hp_rules = {**RULES, "day_of_week_adjustment": dict(RULES["day_of_week_adjustment"],
                                                     dow_factor_value_mon=14.285714285714286)}
hp_full = fc.customization_facts_full({"customizations": hp_rules})
hp_buf = io.StringIO()
hp_buf.write("## rules\n")
hpw = __import__("csv").writer(hp_buf, lineterminator="\n")
hpw.writerow(rc.RULE_COLUMNS)
for r in rc.normalize_rules(hp_rules):
    hpw.writerow([r[c] for c in rc.RULE_COLUMNS])
hp_reduced = fc.customization_facts_reduced(hp_buf.getvalue())
hp_bad = fc.compare(hp_full, hp_reduced, fc.CUSTOMIZATION_FACTS)
check("a high-precision day value (14.285714285714286 prints as '14.2857') round-trips "
      "without a false mismatch",
      not hp_bad, f"changed: {hp_bad}")

# --- fix round 1, finding 3: sentinel collision on customization config values ----
# attribution.SENTINELS = {-1, -2} is PriceLabs' "no value" marker on a PRICE field. Every
# customization config reader used to run through to_number(), which applies that filter
# to percentages too -- but -1%/-2% is an ordinary, real value there (documented range
# -75..1000), not "no data". to_setting() is the sentinel-free config parser; to_number()
# now serves price fields only.

check("to_setting(-1.0) returns -1.0, not None (a real -1% setting is not a price sentinel)",
      at.to_setting(-1.0) == -1.0, f"got {at.to_setting(-1.0)!r}")
check("to_setting(-2.0) returns -2.0, not None",
      at.to_setting(-2.0) == -2.0, f"got {at.to_setting(-2.0)!r}")
check("to_setting(None) is still None (genuinely missing stays missing)",
      at.to_setting(None) is None)
check("to_setting('not a number') is still None (unparseable stays unparseable)",
      at.to_setting("not a number") is None)

# reading: a live -1% Monday must be seen as covering the date and pushing it down, not
# read as an absent/market-driven rule
live_dow = {"dow_factor_on": True,
            "dow_factor_value_mon": -1.0, "dow_factor_value_tue": -2.0,
            "dow_factor_value_wed": 0.0, "dow_factor_value_thu": 0.0,
            "dow_factor_value_fri": 0.0, "dow_factor_value_sat": 0.0,
            "dow_factor_value_sun": 0.0}
check("a live -1% Monday is read as covering the date, not sentinel-stripped to absent",
      at.rule_covers("day_of_week_adjustment", live_dow, mon))
check("a live -1% Monday reads its real direction (down), not collapsed to 'none'",
      at.rule_direction("day_of_week_adjustment", live_dow, mon) == "down")

# reading through the printed table: the reducer must render -1/-2, not blank them to 0
live_norm = rc.normalize_rules({"day_of_week_adjustment": live_dow})[0]
check("the reducer prints a live -1% Monday as -1, not silently blanked to 0",
      "mon=-1" in live_norm["value"], f"got {live_norm['value']!r}")
check("the reducer prints a live -2% Tuesday as -2, not silently blanked to 0",
      "tue=-2" in live_norm["value"], f"got {live_norm['value']!r}")

# writing: the read-modify-write hazard. customization_write.merge_dow (Task 4) has not
# been built yet, but the shape of the bug does not need it -- ANY code that carries a
# day's CURRENT value forward through the wrong parser during a partial update will zero
# it. Reproduce that exact read-modify-write shape with the correct parser and prove the
# live values survive; a real merge_dow, once built, must show the same result.
def _simulate_partial_write(current: dict, changes: dict, parser) -> dict:
    return {k: (changes[k] if k in changes else parser(current.get(k)) or 0.0)
            for k in at.DOW_KEYS}

merged = _simulate_partial_write(live_dow, {"dow_factor_value_sat": 20.0}, at.to_setting)
check("a live -1% Monday survives a partial day-of-week write untouched, not zeroed",
      merged["dow_factor_value_mon"] == -1.0, f"got {merged['dow_factor_value_mon']}")
check("a live -2% Tuesday survives a partial day-of-week write untouched, not zeroed",
      merged["dow_factor_value_tue"] == -2.0, f"got {merged['dow_factor_value_tue']}")
check("the actually-changed Saturday value applies",
      merged["dow_factor_value_sat"] == 20.0, f"got {merged['dow_factor_value_sat']}")

# the identical read-modify-write shape using the OLD price parser reproduces the exact
# bug the reviewer found. Kept as a permanent regression guard: if this ever stops
# zeroing mon/tue, to_number()'s SENTINELS set changed underneath this test.
broken = _simulate_partial_write(live_dow, {"dow_factor_value_sat": 20.0}, at.to_number)
check("using the price parser on config data reproduces the exact bug (why the split matters)",
      broken["dow_factor_value_mon"] == 0.0 and broken["dow_factor_value_tue"] == 0.0,
      f"got mon={broken['dow_factor_value_mon']} tue={broken['dow_factor_value_tue']}")

# the PRICE-field meaning of -1/-2 must be unchanged by this fix: ce_rows still drops them
check("PRICE-field -1/-2 sentinels are still dropped by ce_rows (unchanged by this fix)",
      not any(r["date"] in ("2026-10-01", "2026-10-02") for r in rows),
      f"got dates={[r['date'] for r in rows]}")

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

# --- customization_write: merge_dow regression guard (not in the brief) -----------
# The brief's interface line named `attribution._num`, which has never existed in shipped
# code -- attribution.py exposes to_number() (price fields, filters PriceLabs' -1/-2 "no
# value" sentinels) and to_setting() (customization config fields, no sentinel filtering,
# because -1%/-2% is an ordinary day-of-week value; see live_dow and
# _simulate_partial_write above). customization_write.merge_dow is built on to_setting().
# This closes the gap the comment above _simulate_partial_write called out explicitly:
# prove the REAL merge_dow does what the simulation only modeled -- a live -1%/-2% day
# survives a partial day-of-week write. If to_setting() were ever swapped back for
# to_number() inside merge_dow, to_number()'s SENTINELS filter would read -1.0/-2.0 as
# "no value", fall through to the `or 0.0`-style default, and this check would fail.
live_merged = cw.merge_dow(live_dow, {"dow_factor_value_sat": 20.0})
check("merge_dow preserves a live -1% Monday through a partial write, not zeroed",
      live_merged["dow_factor_value_mon"] == -1.0,
      f"got {live_merged['dow_factor_value_mon']}; to_number() here would silently wipe it")
check("merge_dow preserves a live -2% Tuesday through a partial write, not zeroed",
      live_merged["dow_factor_value_tue"] == -2.0,
      f"got {live_merged['dow_factor_value_tue']}; to_number() here would silently wipe it")
check("merge_dow still applies the day that was actually changed",
      live_merged["dow_factor_value_sat"] == 20.0, f"got {live_merged['dow_factor_value_sat']}")

# --- summary ----------------------------------------------------------------
print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed.")
