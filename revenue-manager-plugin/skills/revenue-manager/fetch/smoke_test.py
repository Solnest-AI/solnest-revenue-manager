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

may = months["2027-05"]
check("STLY blocked night excluded from STLY denominator", may["stly_occ_pct"] == "100.0",
      f"got {may['stly_occ_pct']!r}, want 100.0 (1 booked / (2 - 1 blocked))")

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
txt2 = rp.reason_slice(rows, {"2027-04-01", "2026-01-01"})
check("reason names a requested date that was not fetched", "2026-01-01" in txt2 and "not in the response" in txt2,
      txt2[-160:])

# --- CLI ----------------------------------------------------------------
p = subprocess.run([sys.executable, str(HERE / "reduce_prices.py")],
                   capture_output=True, text=True)
check("CLI exits non-zero with no args", p.returncode != 0)

# (summary moved to the end of the file)

# --- AirROI reducer + fact-class harness ----------------------------------
print("\nreduce_comps + factcheck smoke test\n")
import os, tempfile  # noqa: E402
import factcheck as fc  # noqa: E402
import reduce_comps as rc  # noqa: E402

fx = json.load(open(HERE / "test_fixture_airroi.json"))
fx_mixed = json.load(open(HERE / "test_fixture_airroi_mixed.json"))

def run_reducer(fixture, *extra):
    """Run reduce_comps against a fixture by pointing its cache at a temp dir."""
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, AIRROI_API_KEY="offline-test-key-never-used")
        params = {"bedrooms": 4, "baths": 2.0, "guests": 8, "radius": 0, "latitude": 50.88, "longitude": -119.9}
        # the subprocess resolves RC_CACHE_DIR/airroi via _cache; seed exactly there
        rc.CACHE_DIR = os.path.join(td, "airroi"); os.makedirs(rc.CACHE_DIR, exist_ok=True)
        blob = {"pulled_at": "2026-01-01T00:00:00+00:00", "request": params, "listings": fixture["listings"]}
        json.dump(blob, open(rc.cache_path(params), "w"))
        p = subprocess.run([sys.executable, str(HERE / "reduce_comps.py"), "--bedrooms", "4", "--baths", "2",
                            "--guests", "8", "--lat", "50.88", "--lng", "-119.9", "--ttl-days", "36500", *extra],
                           capture_output=True, text=True, env=dict(env, RC_CACHE_DIR=td))
        return p

# reduce_comps reads CACHE_DIR at import; make the subprocess honour the temp dir
import _cache  # noqa: E402
_probe = os.environ.get("RC_CACHE_DIR")
os.environ["RC_CACHE_DIR"] = "/tmp/rc-probe-xyz"
check("caches resolve under RC_CACHE_DIR when set (never inside the plugin tree)",
      _cache.cache_dir("airroi") == "/tmp/rc-probe-xyz/airroi")
os.environ.pop("RC_CACHE_DIR"); os.environ.update({"RC_CACHE_DIR": _probe} if _probe else {})
check("default cache root is under the user cache dir, not the plugin", "revenue-manager" in _cache.cache_dir() and str(HERE) not in _cache.cache_dir())

p = run_reducer(fx, "--currency", "CAD")
check("reducer exits 0 on a clean CAD set", p.returncode == 0, p.stderr[:200])
out = p.stdout
check("output has header + medians + CSV", out.count("\n") >= 8 and out.startswith("# source=airroi"), out[:120])
check("description/photos are NOT in the default output", "x" * 50 not in out and "photo" not in out)

full = fc.airroi_facts_full(fx)
try:
    red = fc.airroi_facts_reduced(out)
    bad = fc.compare(full, red, fc.AIRROI_FACTS)
except Exception as e:  # noqa: BLE001
    red, bad = {}, [f"reduced output unparseable: {e}"]
check("all 13 fact classes preserved (no subject)", not bad, "; ".join(bad))
check("median ADR from reduced CSV equals median at decision precision", red.get("adr_median") == full["adr_median"], f"{red.get('adr_median')} vs {full['adr_median']}")

p2 = run_reducer(fx, "--currency", "CAD", "--subject-id", "9999", "--subject-name", "subject")
check("subject exclusion exits 0", p2.returncode == 0, p2.stderr[:200])
full2 = fc.airroi_facts_full(fx, subject_id="9999")
try:
    red2 = fc.airroi_facts_reduced(p2.stdout); bad2 = fc.compare(full2, red2, fc.AIRROI_FACTS)
except Exception as e:  # noqa: BLE001
    red2, bad2 = {"subject_in_set": None, "subject_rank_revenue": None, "comp_count": None}, [f"unparseable: {e}"]
check("all 13 fact classes preserved (subject excluded)", not bad2, "; ".join(bad2))
check("subject reported in set at rank 6 of 6", red2["subject_in_set"] and red2["subject_rank_revenue"] == 6,
      f"{red2['subject_in_set']} {red2['subject_rank_revenue']}")
check("subject removed from CSV rows", "9999" not in p2.stdout.split("\n", 2)[2])
check("comp_count drops by exactly one", red2["comp_count"] == 5, str(red2["comp_count"]))
check("subject-name guard fires on a matching comp name", "WARNING subject_name" in p2.stdout or "SUBJECT" not in p2.stdout.split("\n",2)[2])

p3 = run_reducer(fx, "--currency", "USD")
check("currency guard: CAD set + expected USD -> exit 2", p3.returncode == 2, f"rc={p3.returncode}")
check("currency guard prints nothing to stdout on refusal", p3.stdout.strip() == "", p3.stdout[:80])

p4 = run_reducer(fx_mixed, "--currency", "CAD")
check("mixed-currency set -> exit 2 even when expected matches most", p4.returncode == 2, f"rc={p4.returncode}")

p5 = run_reducer(fx, "--currency", "CAD", "--full")
check("--full includes description column", "description" in p5.stdout.split("\n", 2)[2].split("\n")[0])

p6 = subprocess.run([sys.executable, str(HERE / "reduce_comps.py"), "--bedrooms", "4", "--baths", "2", "--guests", "8"],
                    capture_output=True, text=True)
check("no location -> argparse error, exit 2", p6.returncode == 2)

# (summary moved to the end of the file)

# --- neighborhood reducer + fact-class harness -----------------------------
print("\nreduce_neighborhood + factcheck smoke test\n")
import reduce_neighborhood as rn  # noqa: E402

nfx = json.load(open(HERE / "test_fixture_neighborhood.json"))

def run_nb(*extra, seed=True):
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ, RC_CACHE_DIR=td, PRICELABS_API_KEY="offline-test-key-never-used")
        if seed:
            os.makedirs(os.path.join(td, "neighborhood"), exist_ok=True)
            for name in ("nb_loc_50.88_-119.9_smartbnb.json", "nb_fixture-_smartbnb.json"):
                json.dump({"pulled_at": "2026-01-01T00:00:00+00:00", "listing": "fixture-listing", "pms": "smartbnb",
                           "data": nfx["data"]}, open(os.path.join(td, "neighborhood", name), "w"))
        return subprocess.run([sys.executable, str(HERE / "reduce_neighborhood.py"), "--listing", "fixture-listing",
                               "--ttl-days", "36500", "--today", "2026-06-01", *extra], capture_output=True, text=True, env=env)

p = run_nb("--bedrooms", "4", "--lat", "50.88", "--lng", "-119.9", "--currency", "CAD")
check("neighborhood reducer exits 0", p.returncode == 0, p.stderr[:200])
check("three blocks present", all(f"## {b}" in p.stdout for b in ("daily", "monthly", "kpi")), p.stdout[:200])
check("history dates are NOT in the daily block", "2026-12-2" not in p.stdout.split("## daily")[1].split("## monthly")[0])
check("only the requested category's base prices", "base_p50=790" in p.stdout and "base_p50=400" not in p.stdout)
nfull = fc.neighborhood_facts_full(nfx, "4")
nred = fc.neighborhood_facts_reduced(p.stdout)
nbad = fc.compare(nfull, nred, fc.NEIGHBORHOOD_FACTS)
check("all 25 neighborhood fact classes preserved", not nbad, "; ".join(nbad))
check("per-date p50 digest matches (every daily value survived)", nred["p50_by_date_digest"] == nfull["p50_by_date_digest"])

p2 = run_nb("--bedrooms", "4", "--lat", "50.88", "--lng", "-119.9", "--days", "5")
nfull5 = fc.neighborhood_facts_full(nfx, "4", 5)
nred5 = fc.neighborhood_facts_reduced(p2.stdout)
check("--days 5 -> exactly 5 daily rows", nred5["daily_rows"] == 5, str(nred5["daily_rows"]))
check("--days 5 -> all 25 facts preserved for the shorter window", not fc.compare(nfull5, nred5, fc.NEIGHBORHOOD_FACTS))

p3 = run_nb("--bedrooms", "7", "--lat", "50.88", "--lng", "-119.9")
check("absent bedroom category -> exit 2, never substituted", p3.returncode == 2 and "3', '4'" in p3.stderr, p3.stderr[:120])
p4 = run_nb("--bedrooms", "4", "--lat", "50.88", "--lng", "-119.9", "--currency", "USD")
check("currency mismatch -> exit 2", p4.returncode == 2 and p4.stdout.strip() == "")
p5 = run_nb("--bedrooms", "3", "--lat", "50.8849", "--lng", "-119.9021")
check("second listing ~300 m away shares the market cache entry (cache=hit)", "cache=hit" in p5.stdout and "category=3" in p5.stdout, p5.stdout[:160] + p5.stderr[:120])
p6 = run_nb("--bedrooms", "4", seed=False)
check("no cache + no real key -> exit 2, not a crash", p6.returncode == 2, p6.stderr[:120])

# (summary moved to the end of the file)

# --- calendar reconciliation block + fact-class harness ---------------------
print("\nreconcile_pms calendar block + factcheck smoke test\n")
import reconcile_pms as rp2  # noqa: E402

def day(d, status="AVAILABLE", price_cents=40000, min_stay=2, note=None):
    return {"date": d, "min_stay": min_stay, "note": note,
            "status": {"reason": status, "available": status == "AVAILABLE"},
            "price": {"amount": price_cents, "currency": "CAD"}}
def pl(price=400, status="", min_stay=2, unbookable=0):
    return {"price": price, "booking_status": status, "min_stay": min_stay, "unbookable": unbookable}

cal_days = [
    day("2027-01-01"),                                        # clean pair, ratio 1.0
    day("2027-01-02"),
    day("2027-01-03", "RESERVED", 60000),                     # PL says booked too: agreed
    day("2027-01-04", "RESERVED", 70000, note="Off the platform"),   # PL says available: INVISIBLE
    day("2027-01-05", "RESERVED", 50000, note="Owner's Stay"),       # invisible + owner stay
    day("2027-01-06", price_cents=44000),                     # ratio 1.10 -> price drift
    day("2027-01-07", min_stay=3),                            # min-stay 3 vs PL 2 -> mismatch
    day("2027-01-08", min_stay=3),                            # min-stay 3 vs PL sentinel -1 -> NOT a mismatch
    day("2027-01-09", price_cents=0),                         # zero price: excluded from pairs
    day("2027-01-10"),
]
cal_pl = {
    "2027-01-01": pl(), "2027-01-02": pl(), "2027-01-03": pl(600, "Booked"),
    "2027-01-04": pl(700), "2027-01-05": pl(500), "2027-01-06": pl(400),
    "2027-01-07": pl(), "2027-01-08": pl(min_stay=-1), "2027-01-09": pl(), "2027-01-10": pl(),
}
c = fc.calendar_rows(cal_days, cal_pl)
check("reserved nights counted", c["pms_reserved"] == 3, str(c["pms_reserved"]))
check("invisible = PMS reserved but PL available (2)", len(c["invisible"]) == 2 and {d["date"] for d in c["invisible"]} == {"2027-01-04", "2027-01-05"})
check("owner stay detected from the PMS note", c["owner_stay_count"] == 1)
check("agreed booked night is NOT invisible", "2027-01-03" not in {d["date"] for d in c["invisible"]})
check("markup measured on available, non-zero, paired nights only (6)", c["paired_dates"] == 6, str(c["paired_dates"]))
check("markup median is 1.0 for a no-markup listing", c["markup_median"] == 1.0, str(c["markup_median"]))
check("ratio 1.10 date is a price drift row", any(d["date"] == "2027-01-06" and "price" in d["why"] for d in c["drift"]))
check("min-stay 3 vs 2 is a mismatch", c["min_stay_mismatch"] == 1 and any(d["date"] == "2027-01-07" for d in c["drift"]), str(c["min_stay_mismatch"]))
check("PL sentinel -1 min-stay is NOT a mismatch", not any(d["date"] == "2027-01-08" for d in c["drift"]))
check("pms_min_mode is the most common PMS min-stay", c["pms_min_mode"] == 2)

import io as _io
buf = _io.StringIO(); rp2.print_calendar_block("fixture-listing-id", "Fixture House", c, buf)
block = buf.getvalue()
check("block has header + invisible + drift sections", "## calendar" in block and "### invisible" in block and "### drift" in block)
cfull = fc.calendar_facts_full({"pms_days": cal_days, "pl_rows": cal_pl})
cred = fc.calendar_facts_reduced(block)
cbad = fc.compare(cfull, cred, fc.CALENDAR_FACTS)
check("all 13 calendar fact classes survive the printed block", not cbad, "; ".join(cbad))
check("trailing non-CSV text after a blank line does not pollute the drift block",
      not fc.compare(cfull, fc.calendar_facts_reduced(block + "\nExclusion set written to /x\n*** 2 nights ***\n"), fc.CALENDAR_FACTS))
ltr = fc.calendar_rows([day(f"2027-02-{i:02d}", min_stay=90) for i in range(1, 8)], {f"2027-02-{i:02d}": pl(min_stay=-1) for i in range(1, 8)})
buf2 = _io.StringIO(); rp2.print_calendar_block("x", "LTR", ltr, buf2)
check("90-night min-stay prints the long-term-rental NOTE, zero drift rows", "long-term rental" in buf2.getvalue() and len(ltr["drift"]) == 0)

# (summary moved to the end of the file)

# --- reservations reducer + fact-class harness ------------------------------
print("\nreduce_reservations + factcheck smoke test\n")
import reduce_reservations as rr  # noqa: E402

def resv(rid, ci, booked, nights, rev, status="booked", channel="airbnb", cancelled_on=None):
    return {"listing_id": "fixture-listing", "reservation_id": rid, "check_in": ci,
            "check_out": ci, "booking_status": status, "booked_date": booked + "T12:00:00.000Z",
            "rental_revenue": str(rev), "no_of_days": nights, "currency": "CAD",
            "cancelled_on": cancelled_on, "booking_channel": channel, "guestName": "Jane Q. Private",
            "guest_count": 2}
TODAY = "2027-01-15"
res_fx = {"data": [
    resv("r1", "2027-02-01", "2026-11-01", 3, 900.0),                      # lead 92, LOS 3
    resv("r2", "2027-02-10", "2027-01-10", 1, 200.0, channel="vrbo"),        # lead 31, LOS 1, recent (5d)
    resv("r3", "2027-02-20", "2027-01-14", 7, 2100.0, channel="manual"),     # lead 37, LOS 7, recent (1d)
    resv("r4", "2027-03-05", "2026-12-01", 2, 500.0, status="cancelled"),    # cancelled: counted, excluded
    resv("r5", "2027-03-10", "2027-03-08", 4, 1000.0, channel="bcom"),       # lead 2, LOS 4
    resv("r6", "2027-03-12", "2026-06-01", 2, 400.0, cancelled_on="2026-07-01"),  # cancelled via date
]}
json.dump(res_fx, open(HERE / "test_fixture_reservations.json", "w"), indent=1)

rows = fc.reservation_rows(res_fx["data"], TODAY)
t = fc.reservation_tables(rows)
check("live bookings = 4, cancelled = 2 (status OR cancelled_on)", t["bookings"] == 4 and t["cancelled"] == 2, f"{t['bookings']}/{t['cancelled']}")
check("nights and revenue exclude cancelled", t["nights"] == 15 and t["revenue"] == 4200, f"{t['nights']}/{t['revenue']}")
check("overall ADR = revenue / nights", t["adr"] == 280.0, str(t["adr"]))
check("LOS distribution sums to 100", abs(sum(v for v in t["los"].values()) - 100.0) < 0.2, str(t["los"]))
check("lead-time buckets: one 0-7, one 31-60 x2, one 61+", t["lead"]["d0_7"] == 25.0 and t["lead"]["d31_60"] == 50.0 and t["lead"]["d61p"] == 25.0, str(t["lead"]))
check("channel mix counts live bookings only", t["channels"] == {"airbnb": 1, "vrbo": 1, "bcom": 1, "manual": 1, "other": 0}, str(t["channels"]))
check("recent = booked within 14 days of today (2)", len(t["recent"]) == 2, str(len(t["recent"])))
check("monthly rows by check-in month (2027-02, 2027-03)", [m["month"] for m in t["monthly"]] == ["2027-02", "2027-03"])
check("guestName is dropped by the row normaliser", not any("guestName" in r or "Jane" in json.dumps(r) for r in rows))
check("strip_pii removes every PII field", "guestName" not in rr.strip_pii(res_fx["data"][0]))

with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, RC_CACHE_DIR=td, PRICELABS_API_KEY="offline-test-key-never-used")
    os.makedirs(os.path.join(td, "reservations"), exist_ok=True)
    from datetime import date as _d, timedelta as _td
    d_from = (_d.fromisoformat(TODAY) - _td(days=730)).isoformat(); d_to = (_d.fromisoformat(TODAY) + _td(days=365)).isoformat()
    json.dump({"pulled_at": "2027-01-15T00:00:00+00:00", "listing": "fixture-listing", "pms": "smartbnb",
               "window": [d_from, d_to], "data": [rr.strip_pii(r) for r in res_fx["data"]]},
              open(os.path.join(td, "reservations", f"res_fixture-_smartbnb_{d_from}_{d_to}.json"), "w"))
    pr = subprocess.run([sys.executable, str(HERE / "reduce_reservations.py"), "--listing", "fixture-listing",
                         "--today", TODAY, "--currency", "CAD", "--ttl-days", "36500"], capture_output=True, text=True, env=env)
check("reservations reducer exits 0 from cache", pr.returncode == 0, pr.stderr[:200])
check("output never contains a guest name", "Jane" not in pr.stdout and "guest" not in pr.stdout.lower().replace("guest_count", ""))
rfull = fc.reservation_facts_full(res_fx, TODAY)
try:
    rred = fc.reservation_facts_reduced(pr.stdout); rbad = fc.compare(rfull, rred, fc.RESERVATION_FACTS)
except Exception as e:  # noqa: BLE001
    rbad = [f"unparseable: {e}"]
check("all 12 reservation fact classes survive the printed rollup", not rbad, "; ".join(rbad))
with tempfile.TemporaryDirectory() as td:
    env = dict(os.environ, RC_CACHE_DIR=td, PRICELABS_API_KEY="offline-test-key-never-used")
    os.makedirs(os.path.join(td, "reservations"), exist_ok=True)
    json.dump({"pulled_at": "2027-01-15T00:00:00+00:00", "listing": "fixture-listing", "pms": "smartbnb",
               "window": [d_from, d_to], "data": [rr.strip_pii(r) for r in res_fx["data"]]},
              open(os.path.join(td, "reservations", f"res_fixture-_smartbnb_{d_from}_{d_to}.json"), "w"))
    pr2 = subprocess.run([sys.executable, str(HERE / "reduce_reservations.py"), "--listing", "fixture-listing",
                          "--today", TODAY, "--currency", "USD", "--ttl-days", "36500"], capture_output=True, text=True, env=env)
check("currency mismatch -> exit 2, nothing printed", pr2.returncode == 2 and pr2.stdout.strip() == "")

# --- pagination: the endpoint pages on `offset`; a repeated page must not be summed twice ---
import io as _io
import urllib.request as _ur


class _FakeResp(_io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _serve(pages_by_offset):
    calls = []
    def fake_urlopen(req, timeout=0):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(req.full_url).query)
        off = int(q.get("offset", ["0"])[0]); calls.append(off)
        body = pages_by_offset(off)
        return _FakeResp(json.dumps(body).encode())
    return fake_urlopen, calls


_orig = _ur.urlopen
try:
    # 1) API that ignores offset (the bug's shape): same 3 rows forever, next_page always true
    same = {"pms_name": "smartbnb", "next_page": True,
            "data": [{"reservation_id": f"R{i}", "guestName": "x", "check_in": "2027-01-01"} for i in range(3)]}
    _ur.urlopen, calls = _serve(lambda off: same)
    got = rr.fetch("fixture-listing", "smartbnb", "2026-01-01", "2027-12-31", "k")
    check("repeated page is not double counted (3 rows, 2 calls, stop)", len(got) == 3 and len(calls) == 2, f"rows={len(got)} calls={calls}")
    check("guest names stripped by the pager", all("guestName" not in r for r in got))
    # 2) honest offset pagination: 2 full pages + a short last page, next_page false at the end
    def paged(off):
        n = {0: 100, 100: 100, 200: 7}.get(off, 0)
        return {"pms_name": "smartbnb", "next_page": off + n < 207,
                "data": [{"reservation_id": f"R{off + i}", "check_in": "2027-01-01"} for i in range(n)]}
    _ur.urlopen, calls = _serve(paged)
    got = rr.fetch("fixture-listing", "smartbnb", "2026-01-01", "2027-12-31", "k")
    check("offset pagination collects every distinct row once (207)", len(got) == 207 and calls == [0, 100, 200], f"rows={len(got)} calls={calls}")
finally:
    _ur.urlopen = _orig

# --- summary ----------------------------------------------------------------
print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed.")
