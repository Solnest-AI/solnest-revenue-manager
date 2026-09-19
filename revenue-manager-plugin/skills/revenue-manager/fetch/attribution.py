#!/usr/bin/env python3
"""Attribute an observed price to the layer that produced it.

`ce = price / uncustomized_price` is the total effect of the customization stack on a
date. Verified against live data: a listing with every rule off returns ce == 1.000 on
all seven weekdays.

The ratio is exact in TOTAL and does NOT decompose per rule. Several rules overlap the
same date and the far-out premium covers most of a 365-day window, so this module never
claims a rule contributed a specific percentage. It answers a narrower question: which
rules COULD explain the affected dates, and can any of them be pinned down.

  confirmed  the rule covers every affected date and no unaffected date, and its
             direction matches the direction of the effect
  candidate  it covers some affected dates in the right direction, but also covers
             dates that were not affected, so it cannot be separated from its neighbours
  excluded   it covers none of the affected dates

A market-driven rule type (recommended / conservative / aggressive) has no readable sign
in its config, so its direction is "unknown" and it can never reach "confirmed".

A rule that is toggled OFF is also market-driven: switching a rule off does not disable
an adjustment, it hands the date to the algorithm's market-driven default. An off rule
must be treated the same as a market-driven type: direction is "unknown" and it can never
be confirmed.

Pure functions. No network, no file I/O, no API key.
"""
from __future__ import annotations

from datetime import date

# PriceLabs "no value" markers. Never let these reach arithmetic.
SENTINELS = {-1, -2, -1.0, -2.0, "-1", "-2"}

# Types whose effect is derived from live market data, so the config cannot tell you
# which way the price moved.
MARKET_DRIVEN = {"recommended", "conservative", "aggressive", "moderately_conservative",
                 "moderately_aggressive"}

DOW_KEYS = ["dow_factor_value_mon", "dow_factor_value_tue", "dow_factor_value_wed",
            "dow_factor_value_thu", "dow_factor_value_fri", "dow_factor_value_sat",
            "dow_factor_value_sun"]


def to_number(value):
    """Return a float, or None for a sentinel or an unparseable value."""
    if value in SENTINELS:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out in SENTINELS else out


def ce_rows(price_rows: list[dict], today: str) -> list[dict]:
    """One row per usable date: the customization effect and the axes to group it by."""
    base = date.fromisoformat(today)
    out = []
    for row in price_rows:
        raw_date = str(row.get("date") or "")
        price = to_number(row.get("price"))
        unc = to_number(row.get("uncustomized_price"))
        if not raw_date or price is None or unc is None or unc <= 0:
            continue
        try:
            when = date.fromisoformat(raw_date)
        except ValueError:
            continue
        out.append({
            "date": raw_date,
            "ce": price / unc,
            "dow": when.weekday(),            # 0 = Monday
            "days_out": (when - base).days,
            "month": raw_date[:7],
        })
    return out


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def group_ce(rows: list[dict], key: str) -> dict[str, dict]:
    """Aggregate ce by weekday, lead-time bucket, or month."""
    if key not in ("dow", "lead", "month"):
        raise ValueError(f"group key must be dow, lead or month, got {key!r}")
    buckets: dict[str, list[float]] = {}
    for row in rows:
        if key == "dow":
            label = str(row["dow"])
        elif key == "month":
            label = row["month"]
        else:
            label = _lead_bucket(row["days_out"])
        buckets.setdefault(label, []).append(row["ce"])
    return {k: {"n": len(v), "median_ce": _median(v), "min_ce": min(v), "max_ce": max(v)}
            for k, v in sorted(buckets.items())}


def _lead_bucket(days_out: int) -> str:
    for edge, label in ((0, "0"), (3, "1-3"), (7, "4-7"), (14, "8-14"),
                        (30, "15-30"), (60, "31-60"), (90, "61-90"), (180, "91-180")):
        if days_out <= edge:
            return label
    return "180+"


def rule_covers(rule: str, cfg: dict, row: dict) -> bool:
    """Does this rule's window include this date?

    A rule that is toggled OFF still covers its window. Switching a rule off does not
    mean "no adjustment": it hands the date back to the algorithm's market-driven
    default, which is still an effect that has to be explained.
    """
    if rule == "day_of_week_adjustment":
        value = to_number(cfg.get(DOW_KEYS[row["dow"]])) or 0.0
        return value != 0.0 or not cfg.get("dow_factor_on", False)
    if rule == "last_minute_prices":
        dfd = to_number(cfg.get("last_min_factor_dfd"))
        return row["days_out"] <= dfd if dfd is not None else True
    if rule == "far_out_premium":
        start = to_number(cfg.get("far_out_premium_start"))
        return row["days_out"] >= start if start is not None else True
    # seasonality, demand_factor and custom_seasonal_profile have no date window in
    # their config: they apply across the whole horizon.
    return True


def rule_direction(rule: str, cfg: dict, row: dict | None = None) -> str:
    """down, up, none, or unknown. A market-driven type is always unknown."""
    if rule == "day_of_week_adjustment":
        if not cfg.get("dow_factor_on", False):
            return "unknown"
        if row is None:
            return "unknown"
        value = to_number(cfg.get(DOW_KEYS[row["dow"]])) or 0.0
        return "down" if value < 0 else "up" if value > 0 else "none"
    if rule == "last_minute_prices":
        if not cfg.get("last_min_factor_on", False):
            return "unknown"
        kind = cfg.get("last_min_factor_type")
        if kind in MARKET_DRIVEN:
            return "unknown"
        if kind == "none":
            return "none"
        value = to_number(cfg.get("last_min_factor_value"))
        return "unknown" if value is None else "down" if value < 0 else "up" if value > 0 else "none"
    if rule == "far_out_premium":
        if not cfg.get("far_out_premium_on", False):
            return "unknown"
        kind = cfg.get("far_out_premium_type")
        if kind in MARKET_DRIVEN:
            return "unknown"
        if kind == "none":
            return "none"
        value = to_number(cfg.get("far_out_premium_value"))
        return "unknown" if value is None else "down" if value < 0 else "up" if value > 0 else "none"
    # seasonality / demand_factor / custom_seasonal_profile: the config carries a tone
    # or a season set, never a single readable sign for the whole horizon.
    return "unknown"


def classify(affected_dates: set, rows: list[dict], rules: dict) -> list[dict]:
    """The co-incidence test. One verdict per rule, never a per-rule percentage."""
    affected_rows = [r for r in rows if r["date"] in affected_dates]
    other_rows = [r for r in rows if r["date"] not in affected_dates]
    # Direction of the effect itself, from the affected dates.
    effect = "down" if affected_rows and _median([r["ce"] for r in affected_rows]) < 1.0 else "up"

    out = []
    for rule, cfg in rules.items():
        hit = [r for r in affected_rows if rule_covers(rule, cfg, r)]
        # An unaffected date only counts against a rule when the rule pushes that date
        # the SAME way as the effect being explained. A day-of-week rule that discounts
        # Mon/Tue and adds a premium on Fri/Sat is not made ambiguous by the Fri/Sat
        # dates: it moves them the other way, so they are not a competing explanation.
        miss = [r for r in other_rows
                if rule_covers(rule, cfg, r)
                and rule_direction(rule, cfg, r) in (effect, "unknown")]
        if not hit:
            out.append({"rule": rule, "verdict": "excluded", "direction": "n/a",
                        "covered_affected": 0, "covered_unaffected": len(miss),
                        "why": "covers none of the affected dates"})
            continue
        directions = {rule_direction(rule, cfg, r) for r in hit}
        direction = directions.pop() if len(directions) == 1 else "unknown"
        if direction == "unknown":
            out.append({"rule": rule, "verdict": "candidate", "direction": "unknown",
                        "covered_affected": len(hit), "covered_unaffected": len(miss),
                        "why": "market-driven or mixed: the config carries no readable sign"})
        elif direction != effect:
            out.append({"rule": rule, "verdict": "excluded", "direction": direction,
                        "covered_affected": len(hit), "covered_unaffected": len(miss),
                        "why": f"moves prices {direction}, the effect is {effect}"})
        elif len(hit) == len(affected_rows) and not miss:
            out.append({"rule": rule, "verdict": "confirmed", "direction": direction,
                        "covered_affected": len(hit), "covered_unaffected": 0,
                        "why": "covers every affected date and no unaffected date"})
        else:
            out.append({"rule": rule, "verdict": "candidate", "direction": direction,
                        "covered_affected": len(hit), "covered_unaffected": len(miss),
                        "why": f"also covers {len(miss)} unaffected dates, cannot be separated"})
    return out
