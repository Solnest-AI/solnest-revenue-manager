#!/usr/bin/env python3
"""Reduce the PriceLabs customization stack to one compact table.

    python3 reduce_customizations.py --listing <pricelabs id> [--pms smartbnb]

Five endpoints, one table:
  GET  /v1/customizations/listing?toggled_on=false   the six pricing rules
  GET  /v1/customization_profiles                    shared min-stay / pricing / CICO
  GET  /v1/actions                                   PriceLabs' own issue list
  GET  /v1/nudges/available                          pending vendor suggestions
  POST /v1/logs                                      change history, incl. changes made
                                                     outside this skill

`toggled_on=false` is MANDATORY. The default omits every rule whose toggle is off, and an
off rule is not a no-op: it hands the date back to the algorithm's market-driven default.
Measured live, a listing reading "off" on every lever ran a 40% same-day discount, and
another hid a dormant custom seasonal profile holding two real seasons.

Customizations are stable (measured unchanged over 18 days on a live account) while
override state decays, so the default TTL here is 7 days, not 1.

Prints:
    # source=pricelabs_customizations pulled=... cache=hit|miss listing=... rules=6 on=N off=M ...
    ## rules
    rule,toggle,type,value,window,effective
    ## profiles
    kind,id,name,archived
    ## actions
    action_type,title,current,recommended
    ## nudges
    nudge_id,field,current,suggested,reason,expires
    ## logs
    created_at,action,user_id,summary

Exit 0: printed, including a zero-row section, which is a valid answer.
Exit 2: cannot produce a trustworthy table (no key, API error, unexpected shape).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _cache import cache_dir  # noqa: E402
from attribution import DOW_KEYS, to_number  # noqa: E402

BASE = "https://api.pricelabs.co"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"  # WAF 403s bare clients
ENV_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
                 "mcp-servers", "pricelabs", ".env"),
    "./mcp-servers/pricelabs/.env", "../mcp-servers/pricelabs/.env",
    "~/.claude/mcp-servers/pricelabs/.env",
]
CACHE_DIR = cache_dir("customizations")

RULE_COLUMNS = ["rule", "toggle", "type", "value", "window", "effective"]
PROFILE_COLUMNS = ["kind", "id", "name", "archived"]
ACTION_COLUMNS = ["action_type", "title", "current", "recommended"]
NUDGE_COLUMNS = ["nudge_id", "field", "current", "suggested", "reason", "expires"]
LOG_COLUMNS = ["created_at", "action", "user_id", "summary"]

ALL_RULES = ["seasonality", "last_minute_prices", "far_out_premium",
             "day_of_week_adjustment", "demand_factor", "custom_seasonal_profile"]

TOGGLE_KEY = {
    "seasonality": "seasonality_customization_on",
    "last_minute_prices": "last_min_factor_on",
    "far_out_premium": "far_out_premium_on",
    "day_of_week_adjustment": "dow_factor_on",
    "demand_factor": "tone_demand_factor_on",
    "custom_seasonal_profile": "custom_seasonal_profile_on",
}
TYPE_KEY = {
    "seasonality": "seasonality_type",
    "last_minute_prices": "last_min_factor_type",
    "far_out_premium": "far_out_premium_type",
    "demand_factor": "tone_demand_factor",
}


class CannotProduce(Exception):
    pass


def resolve_key() -> str:
    for name in ("PRICELABS_API_KEY", "PRICELABS_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    for path in ENV_CANDIDATES:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded):
            for line in open(expanded):
                match = re.match(r"\s*(PRICELABS_API_KEY|PRICELABS_KEY)\s*=\s*(.+?)\s*$", line)
                if match:
                    return match.group(2).strip('"').strip("'")
    raise CannotProduce("No PRICELABS_API_KEY in the environment or in " + ", ".join(ENV_CANDIDATES))


def call(method: str, path: str, key: str, query: dict | None = None,
         body: dict | None = None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-API-Key": key, "User-Agent": UA,
        "Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:200].decode("utf-8", "replace")
        raise CannotProduce(f"PriceLabs HTTP {exc.code} on {path}: {detail}")
    except Exception as exc:  # noqa: BLE001
        raise CannotProduce(f"PriceLabs request failed on {path}: {exc}")


def rule_window(rule: str, cfg: dict) -> str:
    """How much of the horizon this rule reaches."""
    if rule == "last_minute_prices":
        dfd = to_number(cfg.get("last_min_factor_dfd"))
        return f"<={int(dfd)}d" if dfd else "all"
    if rule == "far_out_premium":
        start = to_number(cfg.get("far_out_premium_start"))
        return f">={int(start)}d" if start else "all"
    if rule == "day_of_week_adjustment":
        days = [k[-3:] for k in DOW_KEYS if (to_number(cfg.get(k)) or 0.0) != 0.0]
        return ",".join(days) if days else "none"
    if rule == "custom_seasonal_profile":
        profile = cfg.get("custom_seasonal_profile") or {}
        count = len(profile.get("seasons") or []) + len(profile.get("non_repeating_seasons") or [])
        return f"{count} seasons"
    return "all"


def rule_value(rule: str, cfg: dict) -> str:
    if rule == "day_of_week_adjustment":
        return " ".join(f"{k[-3:]}={to_number(cfg.get(k)) or 0.0:g}" for k in DOW_KEYS)
    for key in ("last_min_factor_value", "far_out_premium_value"):
        if key in cfg:
            value = to_number(cfg.get(key))
            return "-" if value is None else f"{value:g}"
    return "-"


def normalize_rules(customizations: dict) -> list[dict]:
    """One row per rule present in the payload, off rules included and flagged."""
    out = []
    for rule in ALL_RULES:
        if rule not in customizations:
            continue
        cfg = customizations[rule] or {}
        on = bool(cfg.get(TOGGLE_KEY[rule], False))
        effective = cfg.get("effective")
        out.append({
            "rule": rule,
            "toggle": "on" if on else "OFF",     # upper case so an off rule cannot be skimmed past
            "type": str(cfg.get(TYPE_KEY.get(rule, ""), "") or "-"),
            "value": rule_value(rule, cfg),
            "window": rule_window(rule, cfg),
            "effective": str(effective).replace("\n", " ") if effective else "(no effective block returned)",
        })
    return out


def flatten_actions(payload) -> list[list]:
    rows = payload if isinstance(payload, list) else (payload or {}).get("data") or []
    out = []
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        for action in entry.get("actions") or []:
            meta = action.get("metadata") or {}
            out.append([action.get("action_type", ""), str(action.get("title", "")).replace("\n", " "),
                        json.dumps(meta.get("current", {}), separators=(",", ":")),
                        json.dumps(meta.get("recommended", {}), separators=(",", ":"))])
    return out


def load_or_fetch(listing: str, pms: str, ttl_days: float, use_cache: bool,
                  skip_logs: bool) -> tuple[dict, str]:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"cz_{listing[:8]}_{pms}.json")
    if use_cache and os.path.isfile(path):
        blob = json.load(open(path))
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(blob["pulled_at"])).total_seconds()
        if age <= ttl_days * 86400 and bool(blob.get("has_logs")) != skip_logs:
            return blob, "hit"
    key = resolve_key()
    since = (date.today() - timedelta(days=90)).isoformat()
    data = {
        "rules": call("GET", "/v1/customizations/listing", key,
                      {"listing_id": listing, "pms_name": pms, "toggled_on": "false"}),
        "profiles": call("GET", "/v1/customization_profiles", key),
        "actions": call("GET", "/v1/actions", key),
        "nudges": call("GET", "/v1/nudges/available", key),
        "logs": None if skip_logs else call("POST", "/v1/logs", key, None, {
            "log_type": "listing", "listings": [{"listing_id": listing, "pms": pms}],
            "start_date": since, "end_date": date.today().isoformat(), "limit": 50}),
    }
    blob = {"pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "listing": listing, "pms": pms, "has_logs": not skip_logs, "data": data}
    tmp = path + ".tmp"
    json.dump(blob, open(tmp, "w"))
    os.replace(tmp, path)
    return blob, "miss"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--listing", required=True)
    ap.add_argument("--pms", default="smartbnb")
    ap.add_argument("--ttl-days", type=float, default=7,
                    help="customizations are stable; 7 days, not 1")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--skip-logs", action="store_true",
                    help="skip POST /v1/logs when the account lacks log access")
    args = ap.parse_args()

    blob, how = load_or_fetch(args.listing, args.pms, args.ttl_days,
                              not args.no_cache, args.skip_logs)
    data = blob["data"]

    customizations = (data["rules"] or {}).get("customizations")
    if not isinstance(customizations, dict):
        raise CannotProduce(f"unexpected customizations shape: {type(customizations).__name__}")
    rules = normalize_rules(customizations)

    profiles_raw = (data["profiles"] or {}).get("profiles") or {}
    profile_rows = [[kind, p.get("id"), str(p.get("name", "")).replace("\n", " "), p.get("archived")]
                    for kind, items in profiles_raw.items() for p in (items or [])]
    action_rows = flatten_actions(data["actions"])
    nudges = (data["nudges"] or {}).get("nudges") or []
    log_rows = ((data["logs"] or {}).get("data") or []) if data["logs"] else []

    on = sum(1 for r in rules if r["toggle"] == "on")
    print(f"# source=pricelabs_customizations pulled={blob['pulled_at']} cache={how} "
          f"listing={args.listing[:8]} rules={len(rules)} on={on} off={len(rules) - on} "
          f"profiles={len(profile_rows)} actions={len(action_rows)} nudges={len(nudges)} "
          f"logs={len(log_rows) if data['logs'] else 'skipped'}")

    writer = csv.writer(sys.stdout, lineterminator="\n")
    print("## rules"); writer.writerow(RULE_COLUMNS)
    for r in rules:
        writer.writerow([r[c] for c in RULE_COLUMNS])
    print("## profiles"); writer.writerow(PROFILE_COLUMNS)
    for row in profile_rows:
        writer.writerow(row)
    print("## actions"); writer.writerow(ACTION_COLUMNS)
    for row in action_rows:
        writer.writerow(row)
    print("## nudges"); writer.writerow(NUDGE_COLUMNS)
    for n in nudges:
        writer.writerow([n.get("nudge_id", n.get("id", "")), n.get("field", ""),
                         n.get("current_value", ""), n.get("suggested_value", ""),
                         str(n.get("reason", "")).replace("\n", " "), n.get("expires_at", "")])
    print("## logs"); writer.writerow(LOG_COLUMNS)
    for entry in log_rows:
        writer.writerow([entry.get("created_at", ""), entry.get("action", ""),
                         (entry.get("user") or {}).get("id", ""),
                         str(entry.get("action_label", "")).replace("\n", " ")])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotProduce as exc:
        print(f"CUSTOMIZATIONS UNAVAILABLE: {exc}", file=sys.stderr)
        print("Do not assume the listing has no customizations; say the source could not be read.",
              file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"CUSTOMIZATIONS UNAVAILABLE: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
