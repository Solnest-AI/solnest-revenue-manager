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

# --- customization_write: fix round 1 (coordinator review, Groups A-D) -----------
# Independently re-verified against the shipped module before implementing any fix (see
# the fix report). All ten findings reproduced as described, with one correction: the
# literal claim that listing_id="../../x" "escapes out_dir" did not reproduce -- it
# raised FileNotFoundError instead (the "snapshot_" prefix glued onto the crafted value
# breaks a clean ".." path component in every craft tried). The underlying concern is
# still real (an unsanitized listing_id can crash write_snapshot in a confusing way) so
# the sanitization fix ships anyway; see the fix report for the full evidence.

# Group A: validate() must not return [] for the exact failures it exists to prevent.
# These four payloads are the coordinator's own, used verbatim.
check("A1: a partial day-of-week write (Fri only, no toggle restated) is rejected",
      cw.validate({"day_of_week_adjustment": {"dow_factor_value_fri": 20.0}}),
      "THE MEASURED WIPE: 6 unstated days would reset to 0 on a live calendar")
check("A2: an out-of-range last-minute value/dfd is rejected even with no toggle stated",
      cw.validate({"last_minute_prices": {"last_min_factor_value": -80,
                                          "last_min_factor_dfd": 900}}),
      "-80 exceeds the 75-point discount cap and 900 exceeds the 90-day dfd cap")
check("A4: last_min_factor_type='fix' (the far_out enum) is rejected -- INVERSE ENUM TRAP",
      cw.validate({"last_minute_prices": {"last_min_factor_value": -20,
                                          "last_min_factor_dfd": 14,
                                          "last_min_factor_type": "fix"}}),
      "last_minute_prices uses `fixed`; `fix` is the far_out_premium spelling")
check("A(4th payload): a stray dow_factor_value_* key survives seven valid days undetected no more",
      cw.validate({"day_of_week_adjustment": dict(
          RULES["day_of_week_adjustment"], dow_factor_value_monday=-80.0)}),
      "the typo key is not one of the seven canonical DOW_KEYS and must not be invisible")

# A3: an unknown or missing far_out_premium_type used to silently skip every check.
check("A3: far-out value 9999 and start -50 are rejected when the type is missing",
      cw.validate({"far_out_premium": {"far_out_premium_value": 9999,
                                       "far_out_premium_start": -50}}),
      "a missing type used to skip range checks entirely, not just the type check")

# A3/design correctness: a market-driven type is a legitimate, real PriceLabs value (see
# attribution.MARKET_DRIVEN) and must NOT be flagged as "unknown" just because it carries
# no numeric field to range-check. Written to guard the else-branch added for A3 from
# becoming a new false positive.
check("a market-driven far_out_premium_type ('recommended') is not flagged as unknown",
      not cw.validate({"far_out_premium": {"far_out_premium_type": "recommended"}}),
      f"got {cw.validate({'far_out_premium': {'far_out_premium_type': 'recommended'}})}")
check("a market-driven last_min_factor_type ('conservative') is not flagged as unknown",
      not cw.validate({"last_minute_prices": {"last_min_factor_type": "conservative"}}))

# a genuinely unrecognized type (not the enum trap, not market-driven, not a real type)
# must still be caught -- this is what A3's else branch is actually for
check("a genuinely unknown far_out_premium_type is rejected",
      cw.validate({"far_out_premium": {"far_out_premium_type": "moonbeam",
                                       "far_out_premium_value": 5}}),
      "the else branch added for A3 must still fire on real garbage")

# --- Group B: echo_diff must not be blind to a per-day inversion -----------------
fixture_effective = ("Mon -10% discount, Tue -10% discount, "
                     "Fri +15% premium, Sat +15% premium")

# the coordinator's own reproduction: one string, two opposite intents, both silent
down_whole = cw.echo_diff({"direction": "down", "magnitude": 15}, {"effective": fixture_effective})
up_whole = cw.echo_diff({"direction": "up", "magnitude": 15}, {"effective": fixture_effective})
check("B1: a mixed-sign block no longer satisfies both opposite intents at once "
      "(at least one of down/up must be non-empty against magnitude 15)",
      bool(down_whole) or bool(up_whole),
      f"down={down_whole} up={up_whole} -- before the fix both were []")

# scoped to the day that actually changed: Friday is a premium, not a discount
check("B1: echo_diff scoped to Fri catches a discount intent against an actual Fri premium",
      cw.echo_diff({"direction": "down", "magnitude": 15, "day": "Fri"},
                   {"effective": fixture_effective}),
      "before the fix, Mon/Tue's 'discount' text masked Friday's actual inversion")
check("B1: echo_diff scoped to Fri is silent when the intent (premium) matches",
      not cw.echo_diff({"direction": "up", "magnitude": 15, "day": "Fri"},
                       {"effective": fixture_effective}))
check("B1: echo_diff scoped to Mon is silent when the intent (discount) matches",
      not cw.echo_diff({"direction": "down", "magnitude": 10, "day": "Mon"},
                       {"effective": fixture_effective}))
check("B1: echo_diff scoped to Mon catches a premium intent against an actual Mon discount",
      cw.echo_diff({"direction": "up", "magnitude": 10, "day": "Mon"},
                   {"effective": fixture_effective}))
check("B1: echo_diff reports a day it cannot find in the effective text, rather than "
      "silently passing",
      cw.echo_diff({"direction": "down", "magnitude": 10, "day": "Wed"},
                   {"effective": fixture_effective}),
      "Wednesday has no entry in this fixture at all")
check("B1: without a day, echo_diff still falls back to whole-block matching for a "
      "single-statement rule (last_minute/far_out shape, no per-day breakdown)",
      not cw.echo_diff({"direction": "down", "magnitude": 10},
                       {"effective": "up to 10% discount starting 7 days from check-in"}))

# B2: a direction that is neither "down" nor "up" used to skip every check and return []
check("B2: echo_diff rejects an unrecognized direction rather than silently passing a "
      "literal inversion",
      cw.echo_diff({"direction": "sideways", "magnitude": 10}, {"effective": "Mon 10% premium"}),
      "direction='sideways' used to make every branch a no-op and return []")

# --- Group C: the kill switch -----------------------------------------------------
import os  # noqa: E402
import tempfile as _tempfile  # noqa: E402
import datetime as _datetime_module  # noqa: E402

# C1: snapshot_payload must deep-copy, not alias, current
c1_source = {"day_of_week_adjustment": {"dow_factor_value_mon": -10.0}}
c1_snap = cw.snapshot_payload("cz-listing1", "smartbnb", c1_source)
c1_source["day_of_week_adjustment"]["dow_factor_value_mon"] = 999.0
check("C1: snapshot_payload deep-copies current -- mutating the source afterward does "
      "not change the snapshot",
      c1_snap["customizations"]["day_of_week_adjustment"]["dow_factor_value_mon"] == -10.0,
      f"got {c1_snap['customizations']['day_of_week_adjustment']['dow_factor_value_mon']}, "
      "want -10.0 -- a live reference would let the rollback restore the BROKEN state")

# C2: write_snapshot needs real coverage -- round trip, atomic write, no clobber, no
# path escape. Zero of this existed before fix round 1.
with _tempfile.TemporaryDirectory() as c2_tmp:
    c2_payload = cw.snapshot_payload("cz-listing2", "smartbnb",
                                     {"day_of_week_adjustment": {"dow_factor_value_mon": -5.0}})
    c2_path = cw.write_snapshot(c2_payload, c2_tmp)
    check("write_snapshot returns a path that exists", os.path.isfile(c2_path))
    check("write_snapshot leaves no stray .tmp file behind after a clean write",
          not os.path.exists(c2_path + ".tmp"))
    c2_roundtrip = json.load(open(c2_path))
    check("write_snapshot round-trips the exact payload (the rollback restores exactly "
          "what was snapshotted)",
          c2_roundtrip == c2_payload, f"got {c2_roundtrip}")

    # force a deterministic same-instant collision by freezing the module's clock --
    # two real calls microseconds apart would almost never collide on their own, which
    # would make this test flaky rather than a real guarantee
    class _FrozenDatetime(_datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return _datetime_module.datetime(2026, 1, 1, 12, 0, 0, 0, tzinfo=tz)

    _real_datetime = cw.datetime
    cw.datetime = _FrozenDatetime
    try:
        c2_frozen_payload = cw.snapshot_payload("cz-frozen", "smartbnb", {"x": 1})
        c2_first_path = cw.write_snapshot(c2_frozen_payload, c2_tmp)
        collision_exc = None
        try:
            cw.write_snapshot(c2_frozen_payload, c2_tmp)
        except FileExistsError as exc:
            collision_exc = exc
        check("a second write at the identical microsecond raises, never overwrites",
              collision_exc is not None,
              "write_snapshot must refuse to clobber an existing snapshot file")
        check("the collision raises a clear operator-facing message, not a bare OS error",
              collision_exc is not None and "must not proceed" in str(collision_exc),
              f"got: {collision_exc}")
        check("the original snapshot is unchanged after the refused second write",
              json.load(open(c2_first_path)) == c2_frozen_payload)
    finally:
        cw.datetime = _real_datetime

    # sanitization: a crafted listing_id must never change which directory the file
    # lands in, whatever the exact OS-level failure mode of the unsanitized version was
    c2_traversal_payload = cw.snapshot_payload("../../x", "smartbnb", {})
    c2_traversal_path = cw.write_snapshot(c2_traversal_payload, c2_tmp)
    check("a crafted listing_id cannot change which directory write_snapshot writes into",
          os.path.dirname(os.path.abspath(c2_traversal_path)) == os.path.abspath(c2_tmp),
          f"got {c2_traversal_path}")
    check("write_snapshot succeeds (no confusing crash) on a crafted listing_id",
          os.path.isfile(c2_traversal_path))

# --- Group D: merge_dow ------------------------------------------------------------
# D1: an absent dow_factor_on must not silently default to True (or False) -- raise.
try:
    cw.merge_dow({}, {"dow_factor_value_mon": -10.0})
    d1_raised = False
except ValueError:
    d1_raised = True
check("D1: merge_dow refuses to guess an absent dow_factor_on rather than defaulting "
      "it to True",
      d1_raised,
      "a missing toggle silently defaulting to True would enable a rule with no evidence")

# D2: the toggle round-trip must be proven both ways, not just the True fixture value --
# the original test passed identically against a version that hardcoded True.
d2_off_current = dict(RULES["day_of_week_adjustment"], dow_factor_on=False)
d2_off_merged = cw.merge_dow(d2_off_current, {"dow_factor_value_fri": 5.0})
check("D2: merge_dow preserves an explicit dow_factor_on=False, not just True",
      d2_off_merged["dow_factor_on"] is False,
      f"got {d2_off_merged['dow_factor_on']}; the old test only ever proved True round-trips")

# D3: an unrecognized key in `changes` must raise, not vanish silently. Reproduces the
# coordinator's exact typo ('_monday' vs '_mon') through the real merge_dow, the layer
# that is supposed to prevent this shape from ever reaching validate() at all.
try:
    cw.merge_dow(RULES["day_of_week_adjustment"], {"dow_factor_value_monday": -80.0})
    d3_raised = False
except ValueError:
    d3_raised = True
check("D3: merge_dow raises on an unrecognized key in changes rather than dropping it",
      d3_raised,
      "a typo'd key would otherwise vanish silently: not applied, not flagged, and "
      "invisible to validate() too -- a successful write that changed nothing")

# --- summary ----------------------------------------------------------------
print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed.")
