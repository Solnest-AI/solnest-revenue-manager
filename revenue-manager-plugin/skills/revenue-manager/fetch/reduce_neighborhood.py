#!/usr/bin/env python3
"""Fetch PriceLabs neighborhood data (the comp engine), cache it, print only what a decision reads.

WHY THIS EXISTS
---------------
One `pricelabs_get_neighborhood_data` response is ~118,000 tokens. It carries every bedroom
category the market has (3, 4, 5 for a 4BR listing), 540 days of occupancy of which the
first 180 are the past, and ten series where the decision reads seven. The listing's own
category over the forward year is a few thousand tokens. `fetch/factcheck.py neighborhood`
proves 25 decision facts survive the cut, per-date values included.

WHAT SURVIVES, AND WHY
----------------------
  daily   the 365-day forward ask curve (p25/p50/p75/p90), the median BOOKED price
          (cleared, not ask: the ask-vs-cleared spread is a core signal), N bookings,
          market occupancy, occupancy STLY (pacing at equal lead time), occupancy LY
          (how the date finished last year), new bookings and cancellations (pickup),
          available listings (supply)
  monthly the same percentiles rolled up by month (seasonality at a glance)
  kpi     booking window, LOS, 7-day pickup and STLY, by month plus trailing 365/730

Dropped: the other bedroom categories, the 180 days of daily history (the monthly KPI
block carries history), Occupancy_L2Y / ST2Y, last-year supply.

MARKET SHARING
--------------
The response is computed from the listing's location and contains all categories, so two
listings in the same market get the same payload. The cache is keyed by location rounded
to 2 dp (~1 km) when --lat/--lng are given, so a portfolio in three markets makes three
calls, not eight. The header line names the key so this is never silent.

USAGE
-----
    python3 reduce_neighborhood.py --listing <pricelabs listing id> --bedrooms 4 \
        [--pms smartbnb] [--lat 50.88 --lng -119.90] [--days 365] [--currency CAD] [--no-cache]

EXIT CODES
----------
0  printed
2  could not produce a trustworthy table (no key, API error, bedroom category absent,
   currency mismatch). Never treat 2 as "no market data".
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cache_dir  # noqa: E402
from factcheck import (  # noqa: E402
    NB_DAILY_COLUMNS, NB_KPI_COLUMNS, NB_KPI_SERIES, NB_MONTHLY_COLUMNS, NB_PCT_SERIES,
    _nb_kind, _r, neighborhood_daily_from_raw,
)

BASE = "https://api.pricelabs.co"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"  # WAF 403s bare clients
ENV_CANDIDATES = [
    "./mcp-servers/pricelabs/.env", "../mcp-servers/pricelabs/.env",
    "../../../../mcp-servers/pricelabs/.env", "~/.claude/mcp-servers/pricelabs/.env",
]
CACHE_DIR = cache_dir("neighborhood")


class CannotProduce(Exception):
    pass


def resolve_key() -> str:
    for n in ("PRICELABS_API_KEY", "PRICELABS_KEY"):
        if os.environ.get(n):
            return os.environ[n]
    for path in ENV_CANDIDATES:
        p = os.path.expanduser(path)
        if os.path.isfile(p):
            for line in open(p):
                m = re.match(r"\s*(PRICELABS_API_KEY|PRICELABS_KEY)\s*=\s*(.+?)\s*$", line)
                if m:
                    return m.group(2).strip('"').strip("'")
    raise CannotProduce("No PRICELABS_API_KEY in the environment or in " + ", ".join(ENV_CANDIDATES))


def cache_path(listing: str, pms: str, lat: float | None, lng: float | None) -> tuple[str, str]:
    if lat is not None and lng is not None:
        key = f"loc:{round(lat, 2)},{round(lng, 2)}"
        name = f"nb_loc_{round(lat, 2)}_{round(lng, 2)}_{pms}.json"
    else:
        key = f"listing:{listing[:8]}"
        name = f"nb_{listing[:8]}_{pms}.json"
    return os.path.join(CACHE_DIR, name), key


def fetch(listing: str, pms: str, key: str) -> dict:
    url = f"{BASE}/v1/neighborhood_data?{urllib.parse.urlencode({'listing_id': listing, 'pms': pms})}"
    req = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise CannotProduce(f"PriceLabs HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
    except Exception as e:  # noqa: BLE001
        raise CannotProduce(f"PriceLabs request failed: {e}")
    if "data" not in data:
        raise CannotProduce(f"unexpected response shape: {list(data)[:5]}")
    return {"pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "listing": listing, "pms": pms, "data": data["data"]}


def load_or_fetch(listing, pms, lat, lng, ttl_days, use_cache):
    path, ckey = cache_path(listing, pms, lat, lng)
    if use_cache and os.path.isfile(path):
        try:
            blob = json.load(open(path))
            if time.time() - datetime.fromisoformat(blob["pulled_at"]).timestamp() <= ttl_days * 86400:
                return blob, "hit", ckey
        except Exception:  # noqa: BLE001
            pass
    blob = fetch(listing, pms, resolve_key())
    tmp = path + ".tmp"
    json.dump(blob, open(tmp, "w"))
    os.replace(tmp, path)
    return blob, "miss", ckey


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listing", required=True, help="PriceLabs listing id")
    ap.add_argument("--bedrooms", required=True, help="the listing's bedroom count; selects the category")
    ap.add_argument("--pms", default="smartbnb")
    ap.add_argument("--lat", type=float); ap.add_argument("--lng", type=float)
    ap.add_argument("--days", type=int, default=365, help="forward window (default 365)")
    ap.add_argument("--currency", help="expected ISO code; the payload must report it")
    ap.add_argument("--ttl-days", type=float, default=1, help="cache lifetime (default 1: percentiles move daily)")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    blob, how, ckey = load_or_fetch(a.listing, a.pms, a.lat, a.lng, a.ttl_days, not a.no_cache)
    d = blob["data"]
    cats = sorted(d.get("Future Percentile Prices", {}).get("Category", {}).keys(), key=lambda x: (len(x), x))
    cat = str(a.bedrooms)
    if cat not in cats:
        raise CannotProduce(f"bedroom category {cat} is not in this market's data (available: {cats}). "
                            "Refusing to substitute a neighbouring category.")
    cur = d.get("currency")
    if a.currency and str(cur).upper() != a.currency.upper():
        raise CannotProduce(f"currency mismatch: expected {a.currency}, neighborhood reports {cur}")

    daily = neighborhood_daily_from_raw({"data": d}, cat, a.days)
    if not daily:
        raise CannotProduce("no forward dates in the percentile series")
    pct_cat = d["Future Percentile Prices"]["Category"][cat]
    base = d["Summary Table Base Price"]["Category"][cat]["Y_values"]
    mp = d["Future Percentile Prices Monthly"]["Category"][cat]
    mlabels = d["Future Percentile Prices"]["Labels"]
    kp = d["Market KPI"]["Category"][cat]
    klabels = d["Market KPI"]["Labels"]

    n30 = daily[:30]
    def mean(col, kind):
        v = [float(r[col]) for r in n30 if r.get(col) is not None]
        return _r(sum(v) / len(v), kind) if v else ""
    def total(col):
        return int(sum(float(r[col]) for r in n30 if r.get(col) is not None))

    print(f"# source=pricelabs_neighborhood pulled={blob['pulled_at']} cache={how} cache_key={ckey} "
          f"listing={a.listing[:8]} category={cat} listings_used={pct_cat.get('Listings Used')} "
          f"active={pct_cat.get('Active Used')} currency={cur} days={len(daily)} "
          f"daily_first={daily[0]['date']} daily_last={daily[-1]['date']} categories_available={','.join(cats)}")
    print(f"# base_p25={_r(base[0], 'nb_price')} base_p50={_r(base[1], 'nb_price')} "
          f"base_p75={_r(base[2], 'nb_price')} base_p90={_r(base[3], 'nb_price')}")
    print(f"# next30 p50={mean('p50', 'nb_price')} p90={mean('p90', 'nb_price')} "
          f"booked_med={mean('booked_med', 'nb_price')} occ={mean('occ', 'nb_pct')} "
          f"occ_stly={mean('occ_stly', 'nb_pct')} occ_ly={mean('occ_ly', 'nb_pct')} "
          f"new_bk={total('new_bk')} avail={mean('avail', 'count')}")

    w = csv.writer(sys.stdout, lineterminator="\n")
    print("## daily"); w.writerow(NB_DAILY_COLUMNS)
    for r in daily:
        w.writerow([r[c] if r.get(c) is not None else "" for c in NB_DAILY_COLUMNS])
    print("## monthly"); w.writerow(NB_MONTHLY_COLUMNS)
    for i, m in enumerate(mp["X_values"]):
        w.writerow([m] + [_r(mp["Y_values"][mlabels.index(lab)][i], _nb_kind(col)) for lab, col in NB_PCT_SERIES.items()])
    print("## kpi"); w.writerow(NB_KPI_COLUMNS)
    for i, m in enumerate(kp["X_values"]):
        w.writerow([m] + [_r(kp["Y_values"][klabels.index(lab)][i], "count") for lab in NB_KPI_SERIES])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotProduce as e:
        print(f"NEIGHBORHOOD UNAVAILABLE: {e}", file=sys.stderr)
        print("Do not price against comps this run; report the market as unverified.", file=sys.stderr)
        sys.exit(2)
