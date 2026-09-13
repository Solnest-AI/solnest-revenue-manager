"""Output schema for the decision eval. Passed as output_config.format so both conditions
return the same machine-comparable shape. Keep in sync with compare.py (fields, flags)."""

FLAGS = [
    "SYNC_DEFECT_INVISIBLE_NIGHTS", "PRICE_DRIFT", "MIN_STAY_MISMATCH", "LONG_TERM_RENTAL",
    "NOT_SYNCED", "MIN_BELOW_BASE", "FLOOR_PINNED", "CEILING_PINNED", "THIN_COMPS",
    "CURRENCY_MISMATCH", "STALE_DATA", "OCC_BELOW_MARKET", "OCC_ABOVE_MARKET",
    "ASK_BELOW_MARKET", "ASK_ABOVE_MARKET", "PACING_BEHIND", "PACING_AHEAD", "ORPHAN_GAPS",
    "LARGE_MOVE", "OUT_OF_BOUNDS", "OWNER_STAYS", "OFF_PLATFORM_BOOKINGS", "DATA_SOURCE_FAILED",
]

FIELDS = ["base_price", "min_price", "max_price", "min_stay", "date_override", "orphan_gap",
          "dow_adjustment", "last_minute_discount", "other"]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": props,
            "required": required if required is not None else list(props)}


def _num_or_null():
    return {"type": ["number", "null"]}


def _int_or_null():
    return {"type": ["integer", "null"]}


def _str_or_null():
    return {"type": ["string", "null"]}


CHANGE = _obj({
    "field": {"type": "string", "enum": FIELDS},
    "action": {"type": "string", "enum": ["raise", "lower", "hold", "set", "remove"]},
    "old": _num_or_null(),
    "new": _num_or_null(),
    "pct_move": _num_or_null(),
    "date_from": {"type": "string"},   # YYYY-MM-DD, "" for account-level fields
    "date_to": {"type": "string"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "framework_rule": {"type": "string"},
    "reason": {"type": "string"},
})

DECISION_SCHEMA = _obj({
    "listing_id": {"type": "string"},
    "property": {"type": "string"},
    "currency": {"type": "string"},
    "data_status": {"type": "string", "enum": ["complete", "partial", "unusable"]},
    "gate": _obj({
        "status": {"type": "string", "enum": ["pass", "blocked", "not_synced", "not_run"]},
        "invisible_nights": {"type": "integer"},      # -1 when the gate did not run
        "markup_median": _num_or_null(),
        "markup_spread_warning": {"type": "boolean"},
        "long_term_rental": {"type": "boolean"},
        "min_stay_mismatches": {"type": "integer"},   # -1 when the gate did not run
        "drift_dates": {"type": "integer"},           # -1 when the gate did not run
    }),
    "facts": _obj({
        "occupancy_next_90_pct": _num_or_null(),
        "market_occupancy_next_90_pct": _num_or_null(),
        "ask_median_next_90": _num_or_null(),
        "market_p50_median_next_90": _num_or_null(),
        "cleared_adr_trailing_365": _num_or_null(),
        "pct_dates_at_floor": _num_or_null(),
        "pct_dates_at_ceiling": _num_or_null(),
        "pacing_vs_stly": {"type": "string", "enum": ["ahead", "behind", "even", "unknown"]},
        "comp_count": _int_or_null(),
        "comp_median_adr": _num_or_null(),
        "subject_revenue_rank": {"type": "string"},   # "" when unknown, e.g. "24/25"
    }),
    "flags": {"type": "array", "items": {"type": "string", "enum": FLAGS}},
    "changes": {"type": "array", "items": CHANGE},
    "overall_direction": {"type": "string", "enum": ["raise", "lower", "hold", "mixed", "blocked"]},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "summary": {"type": "string"},
})
