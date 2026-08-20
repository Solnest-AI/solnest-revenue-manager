#!/usr/bin/env python3
"""Offline smoke test for reduce_prices.py -- no API key, no network.

Guards the four traps found against live PriceLabs data:
  1. 'Booked (Check-In)' is a booked night (matching == 'Booked' misses ~40%)
  2. Blocked nights are out of the occupancy denominator
  3. Empty booking_status_STLY means "no data", not "was available":
     a month with zero coverage must render blank, never 0%
  4. -1 / -2 sentinels never surface as real numbers
"""
import csv, io, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import reduce_prices as rp  # noqa: E402

rows = json.load(open(HERE / "test_fixture.json"))[0]["data"]
fails = []

def check(label, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}: {label}{'' if cond else '  -> ' + detail}")
    if not cond:
        fails.append(label)

print("reduce_prices smoke test\n")

# --- Tier B -------------------------------------------------------------
roll, exc, totals = rp.tier_b(rows, gap_pct=12.0)
months = {r["month"]: r for r in csv.DictReader(io.StringIO(roll))}

apr = months["2027-04"]
check("check-in night counts as booked", apr["booked"] == "2", f"got {apr['booked']}, want 2")
check("blocked night excluded from denominator", apr["bookable"] == "3", f"got {apr['bookable']}, want 3")
check("occupancy = booked/bookable", apr["occ_pct"] == "66.7", f"got {apr['occ_pct']}, want 66.7")
check("STLY reported when history exists", apr["stly_occ_pct"] not in ("", None),
      "blank despite 2/4 coverage")

sep = months["2026-09"]
check("STLY blank when zero coverage", sep["stly_occ_pct"] == "",
      f"got {sep['stly_occ_pct']!r}, want '' (0% would read as a YoY collapse)")
check("STLY coverage is shown", sep["stly_cov"] == "0/2", f"got {sep['stly_cov']}")

ex = list(csv.DictReader(io.StringIO(exc)))
check("gap >= threshold surfaces as an exception", len(ex) == 1, f"got {len(ex)} rows")
if ex:
    check("exception carries the right date", ex[0]["date"] == "2027-04-04", ex[0]["date"])

# --- Tier A -------------------------------------------------------------
a = rp.tier_a(rows)
arows = list(csv.DictReader(io.StringIO(a)))
check("Tier A emits one row per date", len(arows) == len(rows), f"{len(arows)} vs {len(rows)}")
check("-1 sentinel blanked in ADR", arows[0]["ADR"] == "", f"got {arows[0]['ADR']!r}")
check("-2 sentinel blanked in ADR_STLY", arows[0]["ADR_STLY"] == "", f"got {arows[0]['ADR_STLY']!r}")
check("Tier A is smaller than raw JSON", len(a) < len(json.dumps(rows, indent=2)))

# --- num() --------------------------------------------------------------
check("num(-1) is None", rp.num(-1) is None)
check("num(-2) is None", rp.num(-2) is None)
check("num('407') parses", rp.num("407") == 407.0)

# --- reason flattening --------------------------------------------------
txt = rp.reason_slice(rows, {"2027-04-01"})
check("reason renders a factor line", "Seasonality -13% -> 608" in txt, txt[:120])
check("reason omits bulky listing_info", "avg_los" not in txt)

# --- CLI ----------------------------------------------------------------
p = subprocess.run([sys.executable, str(HERE / "reduce_prices.py")],
                   capture_output=True, text=True)
check("CLI exits non-zero with no args", p.returncode != 0)

print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed.")
