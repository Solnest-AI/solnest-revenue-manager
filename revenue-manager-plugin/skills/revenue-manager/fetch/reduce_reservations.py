#!/usr/bin/env python3
"""Fetch PriceLabs reservation history, cache it, print a rollup a decision can read.

WHY THIS EXISTS
---------------
Two years of reservations is ~13,000 tokens of JSON per listing, every booking as a full
record, and the record carries the guest's name. A pricing decision reads none of that
per booking. It reads pacing (nights and ADR by month), lead time and length-of-stay
distributions, channel mix, cancellations, and the handful of bookings that landed in the
last two weeks (the "booked within hours of going live" red flag needs those individually).
That is ~700 tokens. `fetch/factcheck.py reservations` proves 12 facts survive the cut.

`guestName` is dropped at the parsing boundary and never written anywhere, including the
cache.

USAGE
-----
    python3 reduce_reservations.py --listing <pricelabs id> [--pms smartbnb]
        [--back 730] [--forward 365] [--currency CAD] [--no-cache] [--ttl-days 1]

EXIT CODES
----------
0  printed
2  could not produce a trustworthy rollup (no key, API error, currency mismatch)
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
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cache_dir  # noqa: E402
from factcheck import (  # noqa: E402
    CHANNELS, LEAD_BUCKETS, LOS_BUCKETS, RES_MONTHLY_COLUMNS, RES_RECENT_COLUMNS,
    reservation_rows, reservation_tables,
)

BASE = "https://api.pricelabs.co"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
ENV_CANDIDATES = ["./mcp-servers/pricelabs/.env", "../mcp-servers/pricelabs/.env",
                  "../../../../mcp-servers/pricelabs/.env", "~/.claude/mcp-servers/pricelabs/.env"]
CACHE_DIR = cache_dir("reservations")
PAGE_SIZE = 100
MAX_PAGES = 20
PII_FIELDS = ("guestName", "guest_name", "email", "phone")


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


def strip_pii(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in PII_FIELDS}


def fetch(listing: str, pms: str, d_from: str, d_to: str, key: str) -> list[dict]:
    """Pages with `offset`/`limit`. Returns rows with PII already removed.

    TRAP (found 2026-09-12 by a row-count check, not by the fact harness): the endpoint
    paginates on `offset`, and `next_page` is a bare boolean. A `page=N` parameter is
    silently ignored, so the old loop fetched page 1 twenty times and every monthly total
    for a busy listing came out up to 20x too high. Both the raw cache and the reduced table
    carried the same duplicates, so raw-vs-reduced agreement proved nothing. Rows are
    de-duplicated on reservation_id and the loop stops the moment a page adds nothing new.
    """
    rows, seen_ids, offset, pages = [], set(), 0, 0
    while pages < MAX_PAGES:
        q = {"listing_id": listing, "pms": pms, "start_date": d_from, "end_date": d_to,
             "limit": PAGE_SIZE, "offset": offset}
        url = f"{BASE}/v1/reservation_data?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(url, headers={"X-API-Key": key, "User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            raise CannotProduce(f"PriceLabs HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
        except Exception as e:  # noqa: BLE001
            raise CannotProduce(f"PriceLabs request failed: {e}")
        page_rows = data.get("data") or []
        new = [r for r in page_rows if r.get("reservation_id") not in seen_ids]
        for r in new:
            seen_ids.add(r.get("reservation_id"))
        rows.extend(strip_pii(r) for r in new)
        pages += 1
        offset += len(page_rows)
        if not data.get("next_page") or not page_rows or not new:
            break
    else:
        raise CannotProduce(f"more than {MAX_PAGES * PAGE_SIZE} reservations in the window; refusing to truncate silently")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listing", required=True)
    ap.add_argument("--pms", default="smartbnb")
    ap.add_argument("--back", type=int, default=730, help="days of history (default 730)")
    ap.add_argument("--forward", type=int, default=365, help="days ahead (default 365)")
    ap.add_argument("--currency", help="expected ISO code; every booking must match")
    ap.add_argument("--today", default=date.today().isoformat(), help=argparse.SUPPRESS)
    ap.add_argument("--ttl-days", type=float, default=1)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    today = date.fromisoformat(a.today)
    d_from, d_to = (today - timedelta(days=a.back)).isoformat(), (today + timedelta(days=a.forward)).isoformat()
    path = os.path.join(CACHE_DIR, f"res_{a.listing[:8]}_{a.pms}_{d_from}_{d_to}.json")
    blob, how = None, "miss"
    if not a.no_cache and os.path.isfile(path):
        try:
            b = json.load(open(path))
            if time.time() - datetime.fromisoformat(b["pulled_at"]).timestamp() <= a.ttl_days * 86400:
                blob, how = b, "hit"
        except Exception:  # noqa: BLE001
            blob = None
    if blob is None:
        rows = fetch(a.listing, a.pms, d_from, d_to, resolve_key())
        blob = {"pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "listing": a.listing, "pms": a.pms, "window": [d_from, d_to], "data": rows}
        tmp = path + ".tmp"; json.dump(blob, open(tmp, "w")); os.replace(tmp, path)

    rows = reservation_rows(blob["data"], a.today)
    t = reservation_tables(rows)
    if a.currency and t["currency"] and t["currency"].upper() != a.currency.upper():
        raise CannotProduce(f"currency mismatch: expected {a.currency}, reservations report {t['currency']}")

    print(f"# source=pricelabs_reservations pulled={blob['pulled_at']} cache={how} listing={a.listing[:8]} "
          f"window={d_from}..{d_to} today={a.today} bookings={t['bookings']} cancelled={t['cancelled']} "
          f"nights={t['nights']} revenue={t['revenue']} adr={t['adr'] if t['adr'] is not None else 'none'} "
          f"currency={t['currency'] or 'none'} "
          f"channels={','.join(f'{c}:{n}' for c, n in t['channels'].items())}")
    print("# los " + " ".join(f"{k}={t['los'][k] if t['los'][k] is not None else 'none'}" for k, _, _ in LOS_BUCKETS)
          + "   (share of live bookings by length of stay, %)")
    print("# lead " + " ".join(f"{k}={t['lead'][k] if t['lead'][k] is not None else 'none'}" for k, _, _ in LEAD_BUCKETS)
          + "   (share of live bookings by days between booking and check-in, %)")
    w = csv.writer(sys.stdout, lineterminator="\n")
    print("## monthly (by check-in month; cancelled bookings counted but excluded from nights/revenue/adr)")
    w.writerow(RES_MONTHLY_COLUMNS)
    for m in t["monthly"]:
        w.writerow([m[c] if m.get(c) is not None else "" for c in RES_MONTHLY_COLUMNS])
    print(f"## recent (booked in the last 14 days; individual rows for the booked-fast red flag)")
    w.writerow(RES_RECENT_COLUMNS)
    for r in t["recent"]:
        w.writerow([r["booked"], r["check_in"], r["lead_days"], r["nights"], r["adr"], r["channel"], "live"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotProduce as e:
        print(f"RESERVATIONS UNAVAILABLE: {e}", file=sys.stderr)
        print("Do not reason about pacing or lead time this run; say history is unverified.", file=sys.stderr)
        sys.exit(2)
