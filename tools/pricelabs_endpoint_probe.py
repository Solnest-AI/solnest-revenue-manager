#!/usr/bin/env python3
"""Probe every published PriceLabs REST operation against one live listing.

Why this exists
---------------
The skill documents 43 operations but its reducers only call six. Documentation
is not evidence: PriceLabs renamed fields on /v1/listings inside nine days in
Aug-Sep 2026 and an ETL reading the old names silently bucketed every listing as
market "unknown". This probe answers, for each operation, three questions that
only a live call can answer:

  1. Does it authenticate and route at all on THIS account?
  2. What does it actually return -- shape, row count, size?
  3. Is the account entitled to it, or is it feature-gated / plan-gated?

Safety
------
State-changing operations are NEVER executed. They are enumerated, the exact
request that WOULD be sent is rendered, and they are reported as SKIPPED. Pass
--i-know-this-writes plus --only <key> to fire one deliberately; there is no
flag that fires them all.

Rate limits: 60 req/min, 1,000/hour. The probe paces itself.
Raw bodies are written to the cache dir, never to stdout. The API key is read
from the environment or the connector .env and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

BASE = "https://api.pricelabs.co"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
PACE_SECONDS = 1.1          # 60/min ceiling with headroom
TIMEOUT = 120

CACHE = Path(os.path.expanduser("~/.cache/revenue-manager/probe"))


# ----------------------------------------------------------------- plumbing

def load_key(env_file: Path | None) -> str:
    key = os.environ.get("PRICELABS_API_KEY")
    if key:
        return key.strip()
    candidates = [env_file] if env_file else []
    candidates.append(Path.home() / ".claude" / "mcp-servers" / "pricelabs" / ".env")
    candidates.append(Path.cwd() / ".env")
    for path in candidates:
        if path and path.is_file():
            for line in path.read_text().splitlines():
                if line.startswith("PRICELABS_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        return val
    sys.exit("error: PRICELABS_API_KEY not set and no .env found (try --env-file)")


def http(method: str, path: str, key: str, query: dict | None = None,
         body: dict | None = None) -> tuple[int, object, int, float]:
    """Return (status, parsed_or_text, byte_count, elapsed_ms). Never raises."""
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-API-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,          # required: bare requests get a WAF 403
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl.create_default_context()) as r:
            raw = r.read()
            ms = (time.time() - t0) * 1000
            try:
                return r.status, json.loads(raw), len(raw), ms
            except json.JSONDecodeError:
                return r.status, raw.decode(errors="replace"), len(raw), ms
    except urllib.error.HTTPError as e:
        raw = e.read()
        ms = (time.time() - t0) * 1000
        try:
            return e.code, json.loads(raw), len(raw), ms
        except Exception:
            return e.code, raw.decode(errors="replace")[:600], len(raw), ms
    except Exception as e:                                   # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", 0, (time.time() - t0) * 1000


def shape(obj) -> str:
    """One-line description of what came back."""
    if isinstance(obj, list):
        inner = shape(obj[0]) if obj else "empty"
        return f"list[{len(obj)}] of {inner}"
    if isinstance(obj, dict):
        keys = list(obj.keys())
        head = ",".join(keys[:6])
        return f"{{{head}{'...' if len(keys) > 6 else ''}}} ({len(keys)} keys)"
    if isinstance(obj, str):
        return f"text[{len(obj)}]"
    return type(obj).__name__


def count_rows(obj) -> str:
    """Best-effort 'how much data' for the table."""
    if isinstance(obj, list):
        return str(len(obj))
    if isinstance(obj, dict):
        for k in ("listings", "data", "results", "overrides", "actions", "nudges",
                  "groups", "logs", "reservations", "templates", "rate_plans",
                  "customizations", "profiles", "bookings"):
            v = obj.get(k)
            if isinstance(v, list):
                return f"{k}={len(v)}"
            if isinstance(v, dict):
                return f"{k}={len(v)} keys"
    return ""


# ------------------------------------------------------------------ the plan
# kind: "read" executes; "write" is enumerated and skipped.

def build_plan(ctx: dict) -> list[dict]:
    lid, pms = ctx["listing_id"], ctx["pms"]
    today = date.today()
    d_from = today.isoformat()
    d_to = (today + timedelta(days=30)).isoformat()
    hist = (today - timedelta(days=90)).isoformat()

    P = lambda **kw: kw  # noqa: E731

    return [
        # --- catalog -------------------------------------------------------
        dict(key="listings", m="GET", path="/v1/listings", kind="read"),
        dict(key="listings_minimal", m="GET", path="/v1/listings_minimal", kind="read"),
        dict(key="listing_by_id", m="GET", path=f"/v1/listings/{urllib.parse.quote(lid)}", kind="read"),
        dict(key="listing_metrics", m="GET", path="/v1/listing_metrics", kind="read",
             q=P(listing_id=lid, pms_name=pms)),
        dict(key="fetch_rate_plans", m="GET", path="/v1/fetch_rate_plans", kind="read",
             q=P(listing_id=lid, pms_name=pms)),

        # --- groups --------------------------------------------------------
        dict(key="groups", m="GET", path="/v1/groups", kind="read"),
        dict(key="group_listings", m="GET", path="/v1/group_listings", kind="read",
             q=P(group_id=ctx.get("group_id"))),

        # --- prices / calendar ---------------------------------------------
        dict(key="listing_prices", m="POST", path="/v1/listing_prices", kind="read",
             body={"listings": [{"id": lid, "pms": pms, "dateFrom": d_from,
                                 "dateTo": d_to, "reason": False}]}),

        # --- overrides ------------------------------------------------------
        dict(key="listing_overrides", m="GET",
             path=f"/v1/listings/{urllib.parse.quote(lid)}/overrides", kind="read",
             q=P(pms=pms)),
        dict(key="group_overrides", m="GET", path="/v1/group_overrides", kind="read",
             q=P(id=ctx.get("group_id"))),

        # --- market ----------------------------------------------------------
        dict(key="neighborhood_data", m="GET", path="/v1/neighborhood_data", kind="read",
             q=P(listing_id=lid, pms=pms)),

        # --- reservations -----------------------------------------------------
        dict(key="reservation_data", m="GET", path="/v1/reservation_data", kind="read",
             q=P(pms=pms, listing_id=lid, start_date=hist, end_date=d_to, limit=5)),
        dict(key="bookings_report", m="POST", path="/v1/bookings_report", kind="read",
             body={"limit": 5, "offset": 0}),

        # --- the unused diagnostics -------------------------------------------
        dict(key="actions", m="GET", path="/v1/actions", kind="read"),
        dict(key="nudges_available", m="GET", path="/v1/nudges/available", kind="read"),
        dict(key="logs", m="POST", path="/v1/logs", kind="read",
             body={"log_type": "listing",
                   "listings": [{"listing_id": lid, "pms": pms}],
                   "start_date": hist, "end_date": d_from, "limit": 50},
             note="log_type is REQUIRED; enum listing|group|account"),

        # --- customizations (the pricing rules) --------------------------------
        dict(key="cust_listing_on", m="GET", path="/v1/customizations/listing", kind="read",
             q=P(listing_id=lid, pms_name=pms)),
        dict(key="cust_listing_all", m="GET", path="/v1/customizations/listing", kind="read",
             q=P(listing_id=lid, pms_name=pms, toggled_on="false"),
             note="toggled_on=false: the only way to see OFF-but-market-driven rules"),
        dict(key="cust_account", m="GET", path="/v1/customizations/account", kind="read",
             q=P(pms_name=pms)),
        dict(key="cust_group", m="GET", path="/v1/customizations/group", kind="read",
             q=P(group_id=ctx.get("group_id"))),
        dict(key="cust_profiles", m="GET", path="/v1/customization_profiles", kind="read"),

        # --- listing optimizer --------------------------------------------------
        dict(key="lo_summary", m="GET", path="/v1/listing_optimizer/summary", kind="read"),
        dict(key="lo_report", m="GET", path="/v1/listing_optimizer/report", kind="read",
             q=P(listing_id=ctx.get("lo_id", lid), pms_name=pms),
             note="optimizer ids are NUMERIC and come from lo_summary, not the PMS uuid"),
        dict(key="lo_ranking", m="GET", path="/v1/listing_optimizer/ranking", kind="read",
             q=P(listing_id=ctx.get("lo_id", lid), pms_name=pms),
             note="optimizer ids are NUMERIC and come from lo_summary, not the PMS uuid"),

        # --- report builder -------------------------------------------------------
        dict(key="rb_templates", m="GET", path="/v1/report_builder/templates", kind="read"),
        dict(key="rb_data", m="POST", path="/v1/report_builder/data", kind="read",
             body={"template_id": ctx.get("template_id")},
             note="queues an async report job; read-only in pricing terms"),
        dict(key="rb_poll", m="POST", path="/v1/report_builder/poll", kind="read",
             body={"request_id": ctx.get("request_id")}),

        # --- revenue estimator ------------------------------------------------------
        dict(key="rev_estimator_v1", m="GET", path="/v1/revenue/estimator", kind="read",
             q=P(lat=ctx.get("lat"), lng=ctx.get("lng"), currency=ctx.get("currency", "CAD"),
                 bedroom_category=ctx.get("bedrooms", 2))),
        dict(key="rev_estimator_v2", m="GET", path="/v2/revenue/estimator", kind="read",
             q=P(lat=ctx.get("lat"), lng=ctx.get("lng"), currency=ctx.get("currency", "CAD"),
                 bedroom_category=ctx.get("bedrooms", 2))),

        # ================= STATE-CHANGING: enumerated, never executed =============
        dict(key="update_listing", m="POST", path="/v1/listings", kind="write",
             body={"listings": [{"id": lid, "pms": pms, "min": "<min>", "base": "<base>",
                                 "max": "<max>"}]},
             danger="base/min/max/tags AND push_enabled. Sync-on starts $1/listing/month billing."),
        dict(key="add_listing_data", m="POST", path="/v1/add_listing_data", kind="write",
             body={"listing_id": lid, "pms_name": pms},
             danger="Adds/overwrites listing metadata held by PriceLabs."),
        dict(key="map_listings", m="POST", path="/v1/mappings/map", kind="write",
             body={"parent": lid, "children": ["<id>"]},
             danger="Re-parents channel listings."),
        dict(key="unmap_listings", m="POST", path="/v1/mappings/unmap", kind="write",
             body={"listings": [lid]},
             danger="Unmapping a parent detaches the whole group."),
        dict(key="create_group", m="POST", path="/v1/groups", kind="write",
             body={"group_name": "<name>"},
             danger="Creates a real account-level group object."),
        dict(key="set_listing_overrides", m="POST",
             path=f"/v1/listings/{urllib.parse.quote(lid)}/overrides", kind="write",
             body={"pms": pms, "overrides": [{"date": "<YYYY-MM-DD>", "price": "<n>"}]},
             danger="Guest-facing per-date price. Pushes to the PMS and on to the OTA."),
        dict(key="delete_listing_overrides", m="DELETE",
             path=f"/v1/listings/{urllib.parse.quote(lid)}/overrides", kind="write",
             body={"pms": pms, "overrides": [{"date": "<YYYY-MM-DD>"}]},
             danger="Reverts dates to algorithmic pricing. Override history decays, so the "
                    "deleted state may be unrecoverable."),
        dict(key="set_group_overrides", m="POST", path="/v1/group_overrides", kind="write",
             body={"id": "<group_id>", "overrides": [{"date": "<YYYY-MM-DD>", "price": "<n>"}]},
             danger="PORTFOLIO: every listing in the group."),
        dict(key="delete_group_overrides", m="DELETE", path="/v1/group_overrides", kind="write",
             body={"id": "<group_id>", "overrides": [{"date": "<YYYY-MM-DD>"}]},
             danger="PORTFOLIO: every listing in the group."),
        dict(key="cust_listing_write", m="POST", path="/v1/customizations/listing", kind="write",
             body={"listing_id": lid, "pms_name": pms, "customizations": {"...": "..."}},
             danger="THE PRICING RULES. Omitted DOW days reset to 0; the sign is accepted "
                    "either way; all-or-nothing; toggling off resets last-minute/far-out."),
        dict(key="cust_group_write", m="POST", path="/v1/customizations/group", kind="write",
             body={"group_id": "<id>", "customizations": {"...": "..."}},
             danger="PORTFOLIO: rules for every listing in the group."),
        dict(key="cust_account_write", m="POST", path="/v1/customizations/account", kind="write",
             body={"pms_name": pms, "customizations": {"...": "..."}},
             danger="PORTFOLIO: rules for the entire account."),
        dict(key="accept_nudge", m="POST", path="/v1/nudges/accept", kind="write",
             body={"nudge_id": "<id>", "listing_id": lid, "pms": pms},
             danger="Applies a pending base/min change. Narrowest write in the API, "
                    "but still a live price move."),
        dict(key="refresh_listing", m="POST", path="/v1/refresh_listing", kind="write",
             body={"listing_id": lid, "pms": pms},
             danger="Recomputes and re-pushes the calendar. HARD LIMIT 3 per listing "
                    "per 24h, 10 per account per minute."),
        dict(key="create_reservations", m="POST", path="/v1/create_reservations", kind="write",
             body={"reservations": ["..."]},
             danger="Invents booking records. Corrupts occupancy, ADR and STLY forever."),
    ]


# --------------------------------------------------------------------- driver

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listing-id", required=True)
    ap.add_argument("--pms", default="smartbnb")
    ap.add_argument("--env-file", type=Path)
    ap.add_argument("--only", help="probe a single key")
    ap.add_argument("--i-know-this-writes", action="store_true",
                    help="permit ONE write, and only with --only")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    key = load_key(args.env_file)
    CACHE.mkdir(parents=True, exist_ok=True)
    ctx = {"listing_id": args.listing_id, "pms": args.pms}
    results: list[dict] = []

    # Two passes: the first discovers ids (group, template, lat/lng) that later
    # calls need, so the plan is rebuilt after the discovery calls land.
    plan = build_plan(ctx)
    if args.only:
        plan = [p for p in plan if p["key"] == args.only]
        if not plan:
            return print(f"no such key: {args.only}") or 2

    for i, step in enumerate(plan):
        if step["kind"] == "write":
            allowed = args.i_know_this_writes and args.only == step["key"]
            if not allowed:
                results.append(dict(key=step["key"], m=step["m"], path=step["path"],
                                    kind="write", status="SKIPPED", ms=0, size=0,
                                    rows="", note=step.get("danger", ""),
                                    would_send=step.get("body")))
                continue

        # rebuild so this step sees ids discovered by earlier steps
        if not args.only:
            fresh = build_plan(ctx)
            step = next(s for s in fresh if s["key"] == step["key"])

        status, payload, size, ms = http(step["m"], step["path"], key,
                                         step.get("q"), step.get("body"))

        (CACHE / f"{step['key']}.json").write_text(
            json.dumps(payload, indent=2, default=str)[:2_000_000])

        note = step.get("note", "")
        if status != 200:
            detail = payload
            if isinstance(payload, dict):
                detail = payload.get("error") or payload.get("message") or payload
            note = (note + " | " if note else "") + str(detail)[:200]

        results.append(dict(key=step["key"], m=step["m"], path=step["path"],
                            kind=step["kind"], status=status, ms=round(ms),
                            size=size, rows=count_rows(payload),
                            shape=shape(payload), note=note))

        # ---- discovery: feed ids forward
        if status == 200:
            if step["key"] == "listings" and isinstance(payload, dict):
                for l in payload.get("listings", []):
                    if str(l.get("id")) == args.listing_id:
                        ctx["lat"] = l.get("latitude") or l.get("lat")
                        ctx["lng"] = l.get("longitude") or l.get("lon")
                        ctx["currency"] = l.get("currency")
                        ctx["bedrooms"] = l.get("no_of_bedrooms") or l.get("bedrooms")
            if step["key"] == "groups":
                g = payload if isinstance(payload, list) else payload.get("groups") or []
                if g and isinstance(g[0], dict):
                    ctx["group_id"] = g[0].get("id") or g[0].get("group_id")
            if step["key"] == "lo_summary":
                d = payload.get("data") if isinstance(payload, dict) else None
                ls = (d or {}).get("listings") or []
                if ls and isinstance(ls[0], dict):
                    ctx["lo_id"] = ls[0].get("listing_id") or ls[0].get("id")
            if step["key"] == "rb_templates":
                t = payload if isinstance(payload, list) else payload.get("templates") or []
                if t and isinstance(t[0], dict):
                    ctx["template_id"] = (t[0].get("templateId") or t[0].get("template_id")
                                          or t[0].get("id"))
            if step["key"] == "rb_data" and isinstance(payload, dict):
                ctx["request_id"] = (payload.get("request_id") or payload.get("requestId")
                                         or payload.get("id")
                                         or (payload.get("data") or {}).get("request_id"))

        print(f"  [{i+1:2}/{len(plan)}] {step['m']:6} {step['key']:22} "
              f"{status} {round(ms):>6}ms {size:>9,}B", file=sys.stderr)
        time.sleep(PACE_SECONDS)

    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=2, default=str))

    # ---------------- markdown table
    print("\n| # | op | method | status | ms | bytes | rows | notes |")
    print("|---|---|---|---|---|---|---|---|")
    for n, r in enumerate(results, 1):
        note = (r.get("note") or "").replace("|", "/").replace("\n", " ")[:120]
        print(f"| {n} | `{r['key']}` | {r['m']} | {r['status']} | {r['ms']} | "
              f"{r['size']:,} | {r['rows']} | {note} |")
    ok = sum(1 for r in results if r["status"] == 200)
    bad = sum(1 for r in results if isinstance(r["status"], int) and r["status"] not in (200, 0))
    skipped = sum(1 for r in results if r["status"] == "SKIPPED")
    print(f"\n200 OK: {ok}   non-200: {bad}   writes skipped: {skipped}   "
          f"total: {len(results)}")
    print(f"raw bodies: {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
