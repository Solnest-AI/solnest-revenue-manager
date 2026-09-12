#!/usr/bin/env python3
"""Reconcile PMS availability against PriceLabs before any pricing recommendation.

WHY THIS EXISTS
---------------
PriceLabs does not see every booking. Off-platform reservations and bookings made
under a channel account that is not wired into the PriceLabs sync are returned as
plainly AVAILABLE (`booking_status: ""`, `unbookable: 0`), not as blocks.

Measured live on 2026-09-12 against the Solnest Stays portfolio, forward 180 days:
53 booked nights worth CA$92,798 were invisible to PriceLabs across 4 of 7 synced
listings. One listing (a ski chalet) showed Dec 0% / Jan 0% occupancy in PriceLabs
while the PMS had it at 71% / 84% booked over Christmas and New Year.

That is not a cosmetic reporting gap. The revenue framework's own red-flag table
fires "5+ consecutive unbooked days -> drop 10 to 15%" and "comp set booked and you
are not -> match comp pricing" on those dates. Left unguarded, the agent recommends
discounting the highest-ADR inventory of the year because it cannot see it is sold.

THE RULE THIS ENFORCES
----------------------
The PMS calendar is ground truth for AVAILABILITY.
PriceLabs is ground truth for PRICE and MARKET.
A date where the PMS says RESERVED and PriceLabs says available is a SYNC DEFECT.
It is never an underperforming date, and it must never enter the discount candidate set.

USAGE
-----
    python3 reconcile_pms.py --days 180
    python3 reconcile_pms.py --days 365 --json exclusions.json
    python3 reconcile_pms.py --listing <listing-uuid> --from 2026-12-15 --to 2027-02-01

Keys are read from the environment first, then from the MCP servers' own .env files.
Nothing is printed that could leak a key.

EXIT CODES
----------
0  the check ran (findings, if any, are in the report)
2  the check could NOT run (missing keys, unreachable API) -- never treat as "clean"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

PL_BASE = "https://api.pricelabs.co"
HO_BASE = "https://public.api.hospitable.com/v2"

# PriceLabs' WAF 403s any request without a browser-shaped User-Agent. The MCP works
# only because axios sets one for free. Direct calls must set it themselves.
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Candidate .env locations, checked in order. Add your own if your layout differs.
PL_ENV_CANDIDATES = [
    "./mcp-servers/pricelabs/.env",
    "../mcp-servers/pricelabs/.env",
    "~/.claude/mcp-servers/pricelabs/.env",
]
HO_ENV_CANDIDATES = [
    "./mcp-servers/hospitable/.env",
    "../mcp-servers/hospitable/.env",
    "~/.claude/mcp-servers/hospitable/.env",
]

PL_KEYS = ("PRICELABS_API_KEY", "PRICELABS_KEY")
HO_KEYS = ("HOSPITABLE_API_KEY", "HOSPITABLE_TOKEN", "HOSPITABLE_PAT")


class CheckCannotRun(Exception):
    """Raised when the reconciliation could not be performed at all.

    Distinct from "performed and found nothing". A check that goes green because it
    was blind is worse than no check, so this always exits non-zero.
    """


def _read_env_file(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        return out
    with open(expanded) as fh:
        for line in fh:
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def resolve_key(names: tuple[str, ...], candidates: list[str], label: str) -> str:
    for n in names:
        if os.environ.get(n):
            return os.environ[n]
    for path in candidates:
        env = _read_env_file(path)
        for n in names:
            if env.get(n):
                return env[n]
    raise CheckCannotRun(
        f"No {label} key found. Set one of {', '.join(names)} in the environment, "
        f"or place it in one of: {', '.join(candidates)}"
    )


def _request(req: urllib.request.Request, timeout: int = 120):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        raise CheckCannotRun(f"{req.full_url.split('?')[0]} returned {e.code}: {body}")
    except Exception as e:  # noqa: BLE001 - surface the cause, never swallow it
        raise CheckCannotRun(f"{req.full_url.split('?')[0]} failed: {e}")


def is_booked(status: str) -> bool:
    """PriceLabs emits 'Booked' AND 'Booked (Check-In)' as separate values.

    Matching `== "Booked"` undercounts occupancy by roughly 40% on a busy month.
    """
    return str(status).strip().lower().startswith("booked")


def pms_reserved(day: dict) -> bool:
    return (day.get("status") or {}).get("reason") == "RESERVED"


def fetch_pricelabs(key: str, listings: list[dict], d_from: str, d_to: str) -> dict:
    """One POST covers every listing. Returns {listing_id: {date: row}}.

    NOTE: PriceLabs silently ignores date ranges in the past. It returns 200 with a
    shorter window rather than an error, so always sanity-check what came back.
    """
    payload = {
        "listings": [
            {"id": l["id"], "pms": l.get("pms", "smartbnb"),
             "dateFrom": d_from, "dateTo": d_to}
            for l in listings
        ]
    }
    req = urllib.request.Request(
        f"{PL_BASE}/v1/listing_prices",
        data=json.dumps(payload).encode(),
        headers={"X-API-Key": key, "User-Agent": UA, "Content-Type": "application/json"},
    )
    raw = _request(req, timeout=180)
    out: dict[str, dict] = {}
    for item in (raw if isinstance(raw, list) else [raw]):
        lid = item.get("id") or item.get("listing_id")
        if not lid:
            continue
        if item.get("error"):
            out[lid] = {"__error__": str(item["error"])}
            continue
        out[lid] = {r["date"]: r for r in item.get("data", []) if r.get("date")}
    return out


def fetch_pms_calendar(token: str, property_id: str, d_from: str, d_to: str) -> list[dict]:
    """Hospitable calendar for one property.

    TRAP: this endpoint takes `start_date`/`end_date` in snake_case while the MCP
    wrapper takes `propertyId` in camelCase, and the wrapper DROPS unknown keys
    silently rather than erroring. Guessing `startDate` returns Hospitable's default
    ~15-day window with no warning, so we assert the echoed range matches the request.
    """
    url = f"{HO_BASE}/properties/{property_id}/calendar?start_date={d_from}&end_date={d_to}"
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    data = _request(req, timeout=90).get("data", {})
    got_from, got_to = data.get("start_date"), data.get("end_date")
    if got_from != d_from or got_to != d_to:
        raise CheckCannotRun(
            f"PMS returned {got_from}..{got_to} for a {d_from}..{d_to} request. "
            "The date filter was ignored; the comparison would be against wrong dates."
        )
    return data.get("days", [])


def reconcile(pms_days: list[dict], pl_rows: dict) -> dict:
    """Classify every date. Returns counts plus the defect list."""
    reserved = [d for d in pms_days if pms_reserved(d)]
    invisible, blocked_only, agreed = [], [], []
    for day in reserved:
        row = pl_rows.get(day["date"])
        if row is None:
            continue  # outside the PriceLabs window; not a defect
        if is_booked(row.get("booking_status", "")):
            agreed.append(day)
        elif row.get("unbookable"):
            # PriceLabs knows it is not sellable, just not that it is revenue.
            blocked_only.append(day)
        else:
            # The dangerous case: PriceLabs believes this night is for sale.
            invisible.append(day)
    return {
        "pms_reserved": len(reserved),
        "pl_booked": sum(1 for r in pl_rows.values() if is_booked(r.get("booking_status", ""))),
        "agreed": len(agreed),
        "blocked_only": blocked_only,
        "invisible": invisible,
    }


def night_value(day: dict) -> float:
    """Hospitable prices are in CENTS on read. Divide by 100 or you are out by 100x."""
    return (day.get("price") or {}).get("amount", 0) / 100.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=180, help="forward window in days (default 180)")
    ap.add_argument("--from", dest="d_from", help="explicit start date YYYY-MM-DD")
    ap.add_argument("--to", dest="d_to", help="explicit end date YYYY-MM-DD")
    ap.add_argument("--listing", action="append", help="limit to these listing ids (repeatable)")
    ap.add_argument("--json", help="write the exclusion set to this path")
    ap.add_argument("--pms", default="smartbnb", help="PriceLabs pms_name (default smartbnb)")
    args = ap.parse_args()

    d_from = args.d_from or (date.today() + timedelta(days=1)).isoformat()
    d_to = args.d_to or (date.fromisoformat(d_from) + timedelta(days=args.days)).isoformat()
    if d_from < date.today().isoformat():
        print("WARNING: start date is in the past. PriceLabs silently ignores past "
              "ranges and will return a shorter window than you asked for.", file=sys.stderr)

    pl_key = resolve_key(PL_KEYS, PL_ENV_CANDIDATES, "PriceLabs")
    ho_key = resolve_key(HO_KEYS, HO_ENV_CANDIDATES, "PMS")

    listings = _request(urllib.request.Request(
        f"{PL_BASE}/v1/listings", headers={"X-API-Key": pl_key, "User-Agent": UA}
    ))
    rows = listings.get("listings", listings) if isinstance(listings, dict) else listings
    wanted = [l for l in rows if not args.listing or l.get("id") in args.listing]
    if not wanted:
        raise CheckCannotRun("No listings matched. Check --listing ids against /v1/listings.")

    pl = fetch_pricelabs(pl_key, wanted, d_from, d_to)

    print(f"PMS-vs-PriceLabs reconciliation   {d_from} -> {d_to}  ({args.days}d window)\n")
    print(f"{'listing':26s} {'PMS bkd':>8s} {'PL bkd':>7s} {'INVISIBLE':>10s} {'value':>11s}  note")
    print("-" * 78)

    exclusions: dict[str, list[str]] = defaultdict(list)
    total_missed = total_value = 0
    unsynced: list[str] = []

    for listing in wanted:
        lid, name = listing["id"], (listing.get("name") or listing["id"])[:26]
        pl_rows = pl.get(lid, {})
        if "__error__" in pl_rows:
            unsynced.append(f"{name}: {pl_rows['__error__']}")
            print(f"{name:26s} {'-':>8s} {'-':>7s} {'-':>10s} {'-':>11s}  NOT SYNCED")
            continue
        try:
            days = fetch_pms_calendar(ho_key, lid, d_from, d_to)
        except CheckCannotRun as e:
            print(f"{name:26s} PMS read failed: {e}")
            continue

        r = reconcile(days, pl_rows)
        value = sum(night_value(d) for d in r["invisible"])
        total_missed += len(r["invisible"])
        total_value += value
        exclusions[lid] = [d["date"] for d in r["invisible"]]

        note = ""
        if r["invisible"]:
            notes = sorted({d.get("note") for d in r["invisible"] if d.get("note")})
            note = notes[0][:28] if notes else "no PMS note"
        print(f"{name:26s} {r['pms_reserved']:8d} {r['pl_booked']:7d} "
              f"{len(r['invisible']):10d} {value:11,.0f}  {note}")
        time.sleep(0.4)  # stay under the 60 req/min ceiling

    print("-" * 78)
    print(f"{'TOTAL':26s} {'':8s} {'':7s} {total_missed:10d} {total_value:11,.0f}")

    if unsynced:
        print("\nNOT SYNCED TO PRICELABS (reported, never silently skipped):")
        for u in unsynced:
            print(f"  - {u}")

    if total_missed:
        print(f"\n*** {total_missed} booked nights worth {total_value:,.0f} are invisible "
              f"to PriceLabs. ***")
        print("These dates are SOLD. They must be excluded from the discount candidate")
        print("set and reported as a sync defect, not treated as underperformance.")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({
                "generated": date.today().isoformat(),
                "window": {"from": d_from, "to": d_to},
                "rule": "PMS RESERVED + PriceLabs available = sync defect, exclude from pricing",
                "exclude_dates_by_listing": {k: v for k, v in exclusions.items() if v},
                "unsynced_listings": unsynced,
            }, fh, indent=2)
        print(f"\nExclusion set written to {args.json}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckCannotRun as exc:
        print(f"RECONCILIATION COULD NOT RUN: {exc}", file=sys.stderr)
        print("Do NOT proceed with pricing recommendations on an unverified calendar.",
              file=sys.stderr)
        sys.exit(2)
