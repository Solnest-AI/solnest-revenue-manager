#!/usr/bin/env python3
"""Fetch AirROI named comparables, cache the raw payload, print only what a decision reads.

WHY THIS EXISTS
---------------
One `get_comparables` call through the MCP is ~103,000 tokens: 25 comps at ~7.8 KB each,
of which the description and photo URLs are ~40% and are never read by a pricing
decision. The 13 fields a decision does read fit in a 75-byte CSV row. This script keeps
the full payload on disk, prints the CSV, and passes `fetch/factcheck.py` to prove no
decision-relevant fact was lost in the cut.

It also fixes three quality problems the MCP path has:

1. CURRENCY. Always sends `currency=native` explicitly and asserts every comp came back
   in the currency you expect. A server whose default is USD silently feeds USD comps to
   a CAD decision; this refuses to print anything if a single comp disagrees.
2. SUBJECT EXCLUSION. If your own listing is inside the comp set, the comp median is
   pulled toward your own price. Pass `--subject-id` and it is removed from every
   statistic, and its rank in the raw set is reported so you still learn where you stand.
3. CALLS. Comps are keyed by (location, bedrooms, guests) and change slowly. Results are
   cached for `--ttl-days` (default 7); co-located listings with the same bedroom count
   share one cache entry. A re-run inside the TTL makes zero API calls.

USAGE
-----
    python3 reduce_comps.py --bedrooms 4 --baths 2 --guests 8 \
        --lat 50.8826 --lng -119.896 --currency CAD --subject-id <your-airbnb-listing-id>

    --address "..."   instead of --lat/--lng
    --radius N        miles, widens thin markets
    --full            also print description + amenities per comp (Listing Optimizer)
    --no-cache        force a live fetch
    --ttl-days N      cache lifetime (default 7)

EXIT CODES
----------
0  printed a reduced comp table
2  could not produce a trustworthy table (no key, API error, currency mismatch)
   -- never treat 2 as "no comps"; it means "do not use comps this run"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from factcheck import AIRROI_COLUMNS, PRECISION, _r  # noqa: E402  (single source of precision)

BASE = os.environ.get("AIRROI_BASE_URL", "https://api.airroi.com")
KEY_NAMES = ("AIRROI_API_KEY",)
ENV_CANDIDATES = [
    "./mcp-servers/airroi/.env", "../mcp-servers/airroi/.env",
    "../../../../mcp-servers/airroi/.env", "~/.claude/mcp-servers/airroi/.env",
]
from _cache import cache_dir  # noqa: E402
CACHE_DIR = cache_dir("airroi")


class CannotProduce(Exception):
    pass


def _read_env(path):
    out = {}
    p = os.path.expanduser(path)
    if os.path.isfile(p):
        for line in open(p):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_key() -> str:
    for n in KEY_NAMES:
        if os.environ.get(n):
            return os.environ[n]
    for path in ENV_CANDIDATES:
        v = _read_env(path).get("AIRROI_API_KEY")
        if v:
            return v
    raise CannotProduce("No AIRROI_API_KEY in the environment or in " + ", ".join(ENV_CANDIDATES))


def cache_path(params: dict) -> str:
    """Co-located listings with the same bedrooms/guests share one entry (lat/lng to 3 dp, ~100 m)."""
    key = {k: params.get(k) for k in ("bedrooms", "baths", "guests", "radius")}
    if params.get("address"):
        key["address"] = params["address"].strip().lower()
    else:
        key["lat"] = round(float(params["latitude"]), 3)
        key["lng"] = round(float(params["longitude"]), 3)
    h = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]
    tag = f"{key.get('bedrooms')}b{key.get('guests')}g"
    return os.path.join(CACHE_DIR, f"airroi_comps_{tag}_{h}.json")


def fetch(params: dict, key: str) -> dict:
    q = {k: v for k, v in params.items() if v not in (None, "", 0)}
    q["currency"] = "native"  # always explicit; never trust a server default
    url = f"{BASE.rstrip('/')}/listings/comparables?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"X-API-KEY": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise CannotProduce(f"AirROI HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
    except Exception as e:  # noqa: BLE001
        raise CannotProduce(f"AirROI request failed: {e}")
    return {"pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "request": q, "listings": data.get("listings") or []}


def load_or_fetch(params: dict, ttl_days: float, use_cache: bool) -> tuple[dict, str]:
    path = cache_path(params)
    if use_cache and os.path.isfile(path):
        try:
            blob = json.load(open(path))
            age = time.time() - datetime.fromisoformat(blob["pulled_at"]).timestamp()
            if age <= ttl_days * 86400:
                return blob, "hit"
        except Exception:  # noqa: BLE001  corrupt cache -> refetch
            pass
    blob = fetch(params, resolve_key())
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = path + ".tmp"
    json.dump(blob, open(tmp, "w"))
    os.replace(tmp, path)
    return blob, "miss"


def flatten(c: dict) -> dict:
    li, pd, pm = c.get("listing_info", {}), c.get("property_details", {}), c.get("performance_metrics", {})
    rt, pi, bs = c.get("ratings", {}), c.get("pricing_info", {}), c.get("booking_settings", {})
    return {
        "listing_id": str(li.get("listing_id", "")),
        "name": (li.get("listing_name") or "").replace("\n", " ").strip()[:40],
        "bedrooms": pd.get("bedrooms"), "baths": pd.get("baths"), "guests": pd.get("guests"),
        "ttm_revenue": _r(pm.get("ttm_revenue"), "revenue"),
        "ttm_adr": _r(pm.get("ttm_avg_rate"), "adr"),
        "ttm_occ": _r(pm.get("ttm_occupancy"), "occ"),
        "ttm_revpar": _r(pm.get("ttm_revpar"), "revpar"),
        "rating": _r(rt.get("rating_overall"), "rating"),
        "reviews": rt.get("num_reviews"),
        "currency": pi.get("currency"),
        "min_nights": _r(bs.get("min_nights"), "min_nights"),
        "los": pm.get("ttm_avg_length_of_stay"),
        "_description": li.get("description", ""),
        "_amenities": c.get("amenities") or li.get("amenities") or "",
    }


def median(vals, kind):
    import statistics
    v = [float(x) for x in vals if x not in (None, "")]
    return _r(statistics.median(v), kind) if v else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bedrooms", type=int, required=True)
    ap.add_argument("--baths", type=float, required=True)
    ap.add_argument("--guests", type=int, required=True)
    ap.add_argument("--lat", type=float); ap.add_argument("--lng", type=float)
    ap.add_argument("--address")
    ap.add_argument("--radius", type=int, default=0)
    ap.add_argument("--currency", help="expected ISO code, e.g. CAD; every comp must match")
    ap.add_argument("--subject-id", help="your own listing id; excluded from every statistic")
    ap.add_argument("--subject-name", help="warn if a comp name matches (id-format mismatch guard)")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--ttl-days", type=float, default=7)
    a = ap.parse_args()
    if not a.address and (a.lat is None or a.lng is None):
        ap.error("give --lat/--lng or --address")

    params = {"bedrooms": a.bedrooms, "baths": a.baths, "guests": a.guests, "radius": a.radius}
    if a.address:
        params["address"] = a.address
    else:
        params["latitude"], params["longitude"] = a.lat, a.lng

    blob, how = load_or_fetch(params, a.ttl_days, not a.no_cache)
    rows = [flatten(c) for c in blob["listings"]]
    if not rows:
        raise CannotProduce("AirROI returned zero comparables for these parameters")

    # 1. currency assertion: refuse to print a mixed or wrong-currency set
    seen = sorted({r["currency"] for r in rows if r["currency"]})
    if a.currency and (len(seen) != 1 or seen[0].upper() != a.currency.upper()):
        raise CannotProduce(f"currency mismatch: expected {a.currency}, comps report {seen}. "
                            "Refusing to print; a comp in the wrong currency poisons every median.")
    if len(seen) != 1:
        raise CannotProduce(f"comps report mixed currencies {seen}; pass --currency to pick, or fix the source")

    # 2. subject exclusion, with rank reported before removal
    ranked = sorted(rows, key=lambda r: (-(float(r["ttm_revenue"] or 0)), r["listing_id"]))
    subject_rank, in_set = None, False
    if a.subject_id:
        for i, r in enumerate(ranked, 1):
            if r["listing_id"] == str(a.subject_id):
                subject_rank, in_set = i, True
        rows = [r for r in rows if r["listing_id"] != str(a.subject_id)]
    name_hits = []
    if a.subject_name:
        needle = a.subject_name.strip().lower()
        name_hits = [r["listing_id"] for r in rows if needle and needle in r["name"].lower()]

    # 3. print: header, medians, CSV
    print(f"# source=airroi pulled={blob['pulled_at']} cache={how} comps={len(rows)} "
          f"currency={seen[0]} subject_id={a.subject_id or 'none'} subject_in_set={str(in_set).lower()} "
          f"subject_rank_revenue={subject_rank if subject_rank else 'none'}")
    print(f"# medians adr={median((r['ttm_adr'] for r in rows), 'adr')} "
          f"occ={median((r['ttm_occ'] for r in rows), 'occ')} "
          f"revenue={median((r['ttm_revenue'] for r in rows), 'revenue')} "
          f"revpar={median((r['ttm_revpar'] for r in rows), 'revpar')} "
          f"rating={median((r['rating'] for r in rows), 'rating')} "
          f"min_nights={median((r['min_nights'] for r in rows), 'min_nights')}")
    if name_hits:
        print(f"# WARNING subject_name matched comps {name_hits}: your listing may be in the set under another id")
    w = csv.writer(sys.stdout, lineterminator="\n")
    cols = AIRROI_COLUMNS + (["description", "amenities"] if a.full else [])
    w.writerow(cols)
    for r in sorted(rows, key=lambda r: (-(float(r["ttm_revenue"] or 0)), r["listing_id"])):
        line = [r[c] if r.get(c) is not None else "" for c in AIRROI_COLUMNS]
        if a.full:
            line += [r["_description"].replace("\n", " ")[:600], json.dumps(r["_amenities"])[:400]]
        w.writerow(line)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotProduce as e:
        print(f"COMPS UNAVAILABLE: {e}", file=sys.stderr)
        print("Do not use named comps this run. PriceLabs neighborhood data remains the comp engine.",
              file=sys.stderr)
        sys.exit(2)
