#!/usr/bin/env python3
"""Build and check a PriceLabs customization write. Never send one.

Every function here is a guard against a measured failure that returns HTTP 200:

  merge_dow           days omitted from a write default to 0, they do NOT keep their
                      previous value, so a Fri/Sat write wipes Mon-Thu
  validate            one invalid value rejects the whole request, so ranges are checked
                      before the payload is built, not after a partial mental model of it
  snapshot_payload    the rollback. The exact object needed to re-POST the prior state
  echo_diff           the sign is accepted either way, because a premium is a legitimate
                      setting. Only the effective block proves which way it went
  signed_from_action  get_actions uses two conventions in one object: current.discount_pct
                      is the stored SIGNED value, recommended.discount_pct is a positive
                      MAGNITUDE. Copying the recommendation writes a premium where a
                      discount was meant

The POST itself is the operator's approved action in Step 8. This module has no network code.

A note on the parser used throughout: attribution.py exposes two of them. to_number() is the
PRICE-field parser -- it filters PriceLabs' -1/-2 "no value" sentinels and must never see a
customization setting. to_setting() is the CONFIG-field parser -- no sentinel filtering,
because a day-of-week/last-minute/far-out percentage is documented -75..1000, so -1% and -2%
are ordinary, real values there, not "no data". Every value this module touches is a
customization config value, so everything here goes through to_setting(). Using to_number()
anywhere in this file -- merge_dow in particular -- would silently zero a live -1% or -2%
setting on the next read-modify-write. (An earlier draft of this module's interface named
attribution._num, which has never existed in shipped code; the two real parsers are
to_number() and to_setting(), and this module uses to_setting() exclusively. See
references/pricelabs-gotchas.md and attribution.py's own module docstring.)
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attribution import DOW_KEYS, to_setting  # noqa: E402
from _cache import cache_dir  # noqa: E402

VALID_RULES = {"seasonality", "last_minute_prices", "far_out_premium",
               "day_of_week_adjustment", "demand_factor", "custom_seasonal_profile"}

RANGES = {
    "dow": (-75.0, 1000.0),
    "last_min_discount": (0.0, 75.0),      # magnitude when the value is negative
    "last_min_premium": (0.0, 500.0),      # magnitude when the value is positive
    "last_min_dfd": (1.0, 90.0),
    "far_out_value": (-30.0, 500.0),
    "far_out_start": (1.0, 999.0),
    "far_out_step": (1.0, 999.0),
}

# Fields the account may not be entitled to. Including one rejects the WHOLE request
# with ERR-FEATURE-NOT-ENABLED, so they are refused locally rather than at the API.
FEATURE_GATED = {"hotel_compset_type", "hotel_wt", "non_repeating_seasons",
                 "price_type_non_repeating"}

# Runtime cache, outside the plugin tree (see _cache.py) so `claude plugin update` never
# duplicates it. Kept in its OWN subfolder rather than reduce_customizations.CACHE_DIR:
# that directory is a TTL'd, disposable fetch cache that gets overwritten on every re-pull,
# while a snapshot is the rollback kill switch and write_snapshot() below refuses to ever
# overwrite one. Mixing the two would let a future cache-clear silently take the rollback
# data with it. Callers may pass any out_dir to write_snapshot(); this is just the default.
SNAPSHOT_DIR = cache_dir("customization_snapshots")


def merge_dow(current: dict, changes: dict) -> dict:
    """Return a FULL seven-day object. Never send a partial day-of-week write."""
    out = {"dow_factor_on": bool(current.get("dow_factor_on", True))}
    for key in DOW_KEYS:
        if key in changes:
            out[key] = changes[key]
        else:
            # Explicit None-check, not `to_setting(...) or 0.0`: a legitimate 0, 0.0 or
            # False must never be silently replaced by the fallback just because it is
            # falsy. Matches reduce_customizations.clean_text's `is None or == ""` idiom.
            value = to_setting(current.get(key))
            out[key] = 0.0 if value is None else value
    return out


def _in_range(value, bounds, label, errors):
    number = to_setting(value)
    if number is None:
        errors.append(f"{label}: {value!r} is not a number")
        return
    low, high = bounds
    if not (low <= number <= high):
        errors.append(f"{label}: {number:g} is outside {low:g}..{high:g}")


def validate(customizations: dict) -> list[str]:
    """Return every problem found. An empty list means the payload is safe to send."""
    errors: list[str] = []
    for rule, cfg in customizations.items():
        if rule not in VALID_RULES:
            errors.append(f"{rule}: not a customization name PriceLabs accepts")
            continue
        cfg = cfg or {}
        for field in cfg:
            if field in FEATURE_GATED:
                errors.append(f"{rule}.{field}: feature-gated, rejects the whole request")

        if rule == "day_of_week_adjustment":
            present = [k for k in DOW_KEYS if k in cfg]
            if cfg.get("dow_factor_on") and len(present) != 7:
                errors.append("day_of_week_adjustment: all seven days must be sent; "
                              f"got {len(present)}. Omitted days reset to 0")
            for key in present:
                _in_range(cfg[key], RANGES["dow"], f"day_of_week_adjustment.{key}", errors)

        elif rule == "last_minute_prices" and cfg.get("last_min_factor_on"):
            kind = cfg.get("last_min_factor_type")
            if kind in ("linear", "linear_gradual", "fixed"):
                value = to_setting(cfg.get("last_min_factor_value"))
                if value is None:
                    errors.append("last_minute_prices: last_min_factor_value is required "
                                  f"for type {kind}")
                elif kind != "fixed":
                    bounds = RANGES["last_min_discount"] if value < 0 else RANGES["last_min_premium"]
                    _in_range(abs(value), bounds, "last_minute_prices.last_min_factor_value", errors)
                _in_range(cfg.get("last_min_factor_dfd"), RANGES["last_min_dfd"],
                          "last_minute_prices.last_min_factor_dfd", errors)

        elif rule == "far_out_premium" and cfg.get("far_out_premium_on"):
            kind = cfg.get("far_out_premium_type")
            if kind in ("linear", "fix"):
                _in_range(cfg.get("far_out_premium_value"), RANGES["far_out_value"],
                          "far_out_premium.far_out_premium_value", errors)
                _in_range(cfg.get("far_out_premium_start"), RANGES["far_out_start"],
                          "far_out_premium.far_out_premium_start", errors)
                if kind == "linear":
                    _in_range(cfg.get("far_out_premium_step"), RANGES["far_out_step"],
                              "far_out_premium.far_out_premium_step", errors)
            elif kind == "fixed":
                errors.append("far_out_premium: the enum is `fix`, not `fixed` "
                              "(last_minute uses `fixed`; they differ)")
    return errors


def snapshot_payload(listing_id: str, pms: str, current: dict) -> dict:
    """The exact object that restores the prior state. This is the kill switch."""
    return {"listing_id": listing_id, "pms_name": pms, "customizations": current}


def write_snapshot(payload: dict, out_dir: str) -> str:
    """Persist the rollback payload and return its path. Never overwrite a snapshot."""
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    listing = str(payload.get("listing_id", "unknown"))[:8]
    path = os.path.join(out_dir, f"snapshot_{listing}_{stamp}.json")
    with open(path, "x") as handle:            # x: refuse to clobber an existing snapshot
        json.dump(payload, handle, indent=2)
    return path


def echo_diff(intent: dict, after: dict) -> list[str]:
    """Compare what you meant against what the dashboard now renders.

    `intent` is {"direction": "down"|"up", "magnitude": <positive number>}.
    `after` is the rule object re-read after the write, carrying its `effective` block.
    """
    effective = (after or {}).get("effective")
    if not effective:
        return ["no effective block returned; the write cannot be confirmed"]
    text = str(effective).lower()
    saw_down = "discount" in text
    saw_up = "premium" in text
    problems = []
    if intent["direction"] == "down" and not saw_down:
        problems.append(f"intended a discount, effective reads {effective!r}")
    if intent["direction"] == "up" and not saw_up:
        problems.append(f"intended a premium, effective reads {effective!r}")
    if intent["direction"] == "down" and saw_up and not saw_down:
        problems.append("SIGN INVERTED: a discount was written as a premium")
    magnitudes = [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
    if magnitudes and not any(abs(m - float(intent["magnitude"])) < 0.51 for m in magnitudes):
        problems.append(f"intended {intent['magnitude']}%, effective shows {magnitudes}")
    return problems


def signed_from_action(action: dict) -> tuple[float, bool]:
    """Convert an action's recommendation into a signed customization value.

    Returns (value, confirmed). `confirmed` is always False: the convention is inferred
    from the stored value matching `current` exactly plus the meaning of the action type,
    and it has not been proven with a write. A caller must not auto-apply an unconfirmed
    value. See references/pricelabs-gotchas.md, "two sign conventions".
    """
    meta = action.get("metadata") or {}
    recommended = to_setting((meta.get("recommended") or {}).get("discount_pct"))
    if recommended is None:
        raise ValueError("action has no recommended.discount_pct")
    kind = str(action.get("action_type", ""))
    if "last_minute" in kind:
        return -abs(recommended), False
    return recommended, False
