#!/usr/bin/env python3
"""Build and check a PriceLabs customization write. Never send one.

Every function here is a guard against a measured failure that returns HTTP 200:

  merge_dow           days omitted from a write default to 0, they do NOT keep their
                      previous value, so a Fri/Sat write wipes Mon-Thu. Also refuses to
                      guess: an absent toggle or an unrecognized `changes` key raises
                      rather than silently assuming or dropping it (fix round 1, D1/D3)
  validate            one invalid value rejects the whole request, so ranges are checked
                      before the payload is built, not after a partial mental model of it.
                      Checks run on whatever fields are PRESENT; the on/off toggle no
                      longer gates whether a check runs at all (fix round 1, A1-A4)
  snapshot_payload    the rollback. The exact object needed to re-POST the prior state.
                      Deep-copies `current` so a later mutation of the caller's dict can
                      never reach back into an already-taken snapshot (fix round 1, C1)
  write_snapshot      persists the snapshot atomically and never overwrites one, even
                      under a same-instant collision (fix round 1, C1/C2)
  echo_diff           the sign is accepted either way, because a premium is a legitimate
                      setting. Only the effective block proves which way it went. A
                      day-of-week block mixes signs across seven days in one string, so an
                      unscoped substring test is blind to a single day inverting -- pass
                      `intent["day"]` to scope the comparison. Without a day, a block that
                      mixes discount and premium is refused rather than guessed at
                      (fix round 1, B1/B2)
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

import copy
import json
import os
import re
from datetime import datetime, timezone

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from attribution import DOW_KEYS, MARKET_DRIVEN, to_setting  # noqa: E402
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
    """Return a FULL seven-day object. Never send a partial day-of-week write.

    Raises ValueError rather than guessing in two places (fix round 1, D1/D3):
      - `current` has no `dow_factor_on`: defaulting it (either way) would silently
        enable or disable a guest-facing rule with no evidence. The caller must read the
        real toggle state from PriceLabs first.
      - `changes` has a key outside DOW_KEYS: a typo'd key (`_monday` vs `_mon`) used to
        vanish silently -- not applied, not flagged, and invisible to validate() too, so
        the operator got a "successful" write that changed nothing on the day they meant
        to change.
    """
    if "dow_factor_on" not in current:
        raise ValueError(
            "merge_dow: current has no dow_factor_on -- the toggle state must come from "
            "a real PriceLabs read, never assumed. Defaulting it either way would "
            "silently enable or disable a guest-facing rule with no evidence.")
    unknown = sorted(set(changes) - set(DOW_KEYS))
    if unknown:
        raise ValueError(
            f"merge_dow: changes has unrecognized key(s) {unknown}; expected only "
            f"{DOW_KEYS}. A typo'd key is silently dropped otherwise -- not applied, not "
            "flagged, and invisible to validate() too.")
    out = {"dow_factor_on": bool(current["dow_factor_on"])}
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
    """Return every problem found. An empty list means the payload is safe to send.

    Fix round 1 (A1-A4): every check below now runs on whatever fields are PRESENT.
    The on/off toggle no longer gates whether a rule gets checked at all -- it only
    gates whether a value is REQUIRED. The original gating meant an operator who only
    restated the days/fields they were actually changing (the normal, minimal case) got
    zero validation, because the toggle key itself is exactly the field they had no
    reason to resend.
    """
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
            # A1: completeness no longer depends on dow_factor_on being restated.
            if present and len(present) != 7:
                errors.append("day_of_week_adjustment: all seven days must be sent; "
                              f"got {len(present)}. Omitted days reset to 0")
            for key in present:
                _in_range(cfg[key], RANGES["dow"], f"day_of_week_adjustment.{key}", errors)
            # A stray dow_factor_value_* key (a typo like `_monday` for `_mon`) is
            # invisible to `present` above -- it's simply not one of the seven canonical
            # names -- so it needs its own check. merge_dow (D3) refuses to build this
            # shape in the normal pipeline; this is the second layer, for anyone who
            # calls validate() directly on a hand-built or already-merged dict.
            stray = sorted(k for k in cfg
                           if k.startswith("dow_factor_value_") and k not in DOW_KEYS)
            if stray:
                errors.append(f"day_of_week_adjustment: unrecognized day key(s) {stray}; "
                              f"expected one of {DOW_KEYS}")

        elif rule == "last_minute_prices":
            kind = cfg.get("last_min_factor_type")
            touched = (kind is not None or "last_min_factor_value" in cfg
                      or "last_min_factor_dfd" in cfg)
            if touched:
                if kind == "fix":
                    # A4: the mirror of the far_out_premium enum trap below. Far-out
                    # uses `fix`, last-minute uses `fixed` -- they are NOT interchangeable
                    # and PriceLabs rejects the whole request on the wrong one.
                    errors.append("last_minute_prices: the enum is `fixed`, not `fix` "
                                  "(far_out_premium uses `fix`; they differ)")
                elif kind in MARKET_DRIVEN or kind == "none":
                    pass  # no readable numeric value to range-check for these types
                elif kind in ("linear", "linear_gradual", "fixed"):
                    if "last_min_factor_value" in cfg:
                        value = to_setting(cfg.get("last_min_factor_value"))
                        if value is None:
                            errors.append("last_minute_prices: last_min_factor_value is "
                                          f"not a number for type {kind}")
                        elif kind != "fixed":
                            bounds = (RANGES["last_min_discount"] if value < 0
                                     else RANGES["last_min_premium"])
                            _in_range(abs(value), bounds,
                                      "last_minute_prices.last_min_factor_value", errors)
                    elif cfg.get("last_min_factor_on"):
                        errors.append("last_minute_prices: last_min_factor_value is "
                                      f"required for type {kind}")
                    if "last_min_factor_dfd" in cfg:
                        _in_range(cfg.get("last_min_factor_dfd"), RANGES["last_min_dfd"],
                                  "last_minute_prices.last_min_factor_dfd", errors)
                elif kind is None:
                    # A3: a missing type used to silently skip every check, including
                    # the range checks on value/dfd that ARE present.
                    errors.append("last_minute_prices: last_min_factor_type is required "
                                  "when last_min_factor_value or last_min_factor_dfd "
                                  "is present")
                else:
                    # A3: an unrecognized type used to silently skip every check too.
                    errors.append("last_minute_prices: unknown last_min_factor_type "
                                  f"{kind!r}")

        elif rule == "far_out_premium":
            kind = cfg.get("far_out_premium_type")
            touched = (kind is not None or "far_out_premium_value" in cfg
                      or "far_out_premium_start" in cfg or "far_out_premium_step" in cfg)
            if touched:
                if kind == "fixed":
                    errors.append("far_out_premium: the enum is `fix`, not `fixed` "
                                  "(last_minute_prices uses `fixed`; they differ)")
                elif kind in MARKET_DRIVEN or kind == "none":
                    pass  # no readable numeric value to range-check for these types
                elif kind in ("linear", "fix"):
                    if "far_out_premium_value" in cfg:
                        _in_range(cfg.get("far_out_premium_value"), RANGES["far_out_value"],
                                  "far_out_premium.far_out_premium_value", errors)
                    if "far_out_premium_start" in cfg:
                        _in_range(cfg.get("far_out_premium_start"), RANGES["far_out_start"],
                                  "far_out_premium.far_out_premium_start", errors)
                    if kind == "linear" and "far_out_premium_step" in cfg:
                        _in_range(cfg.get("far_out_premium_step"), RANGES["far_out_step"],
                                  "far_out_premium.far_out_premium_step", errors)
                elif kind is None:
                    # A3: a missing type used to silently skip every check -- this is
                    # the exact case that let value=9999/start=-50 through.
                    errors.append("far_out_premium: far_out_premium_type is required "
                                  "when far_out_premium_value, _start or _step is present")
                else:
                    # A3: an unrecognized type used to silently skip every check too.
                    errors.append("far_out_premium: unknown far_out_premium_type "
                                  f"{kind!r}")
    return errors


def snapshot_payload(listing_id: str, pms: str, current: dict) -> dict:
    """The exact object that restores the prior state. This is the kill switch.

    Deep-copies `current` (fix round 1, C1): without this, the returned payload held a
    live reference, and mutating the caller's `current` dict AFTER snapshotting silently
    changed the snapshot too. A rollback built from that snapshot would then restore the
    mutated state, not the state that was actually live at snapshot time -- the exact
    failure this function exists to prevent, in the one place it can never be wrong.
    """
    return {"listing_id": listing_id, "pms_name": pms, "customizations": copy.deepcopy(current)}


def write_snapshot(payload: dict, out_dir: str) -> str:
    """Persist the rollback payload and return its path. Never overwrite a snapshot.

    Fix round 1 (C1), four changes, all in the kill switch so all treated as load-bearing:
      - microsecond-resolution timestamp, to make a same-instant collision rare instead
        of merely "within the same second"
      - write to a `.tmp` file and `os.replace()` it into place, so a `json.dump` that
        fails partway through can never leave a truncated file that LOOKS like a valid
        snapshot
      - the exclusivity check now covers the FINAL path explicitly (os.replace() would
        otherwise silently overwrite an existing destination -- unlike the old direct
        `open(path, "x")`, an atomic rename does not fail on a pre-existing target on its
        own), and a collision raises a clear, purpose-built FileExistsError rather than a
        bare OS error, so a caller cannot wrap this in a generic `except` and proceed to
        write with no rollback on record
      - `listing_id` is sanitized before it becomes part of a filename, so a crafted or
        malformed id (a stray "/" or "..") cannot alter which directory the file lands in
    """
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    listing_raw = str(payload.get("listing_id", "unknown"))
    listing = re.sub(r"[^A-Za-z0-9_-]+", "_", listing_raw)[:8] or "unknown"
    path = os.path.join(out_dir, f"snapshot_{listing}_{stamp}.json")
    tmp_path = path + ".tmp"
    try:
        if os.path.exists(path):
            raise FileExistsError(path)
        with open(tmp_path, "x") as handle:   # x: refuse to clobber a stray leftover .tmp
            json.dump(payload, handle, indent=2)
        os.replace(tmp_path, path)            # atomic; a failed dump above never reaches
                                               # this line, so `path` is never left
                                               # half-written
    except FileExistsError as exc:
        raise FileExistsError(
            f"a snapshot already exists for listing {listing!r} at this microsecond "
            f"({path!r}); the caller must not proceed without a confirmed snapshot, and "
            "must not catch this and write anyway"
        ) from exc
    return path


_EFFECTIVE_DAY_RE = re.compile(
    r"([A-Za-z]+)\s+([+-]?\d+(?:\.\d+)?)\s*%\s*(discount|premium)", re.IGNORECASE)


def echo_diff(intent: dict, after: dict) -> list[str]:
    """Compare what you meant against what the dashboard now renders.

    `intent` is {"direction": "down"|"up", "magnitude": <positive number>,
    "day": <optional, e.g. "Fri" or "fri">}. `after` is the rule object re-read after the
    write, carrying its `effective` block.

    Fix round 1 (B1/B2):
      - A day-of-week `effective` string lists all seven days in one block, mixing
        discounts and premiums (e.g. "Mon -10% discount, ..., Fri +15% premium, ...").
        Testing "discount"/"premium" as substrings of the WHOLE block is blind to a
        single day inverting: any block with at least one discount and one premium
        anywhere in it satisfied both possible intents at once, so the inversion check
        could never fire on a mixed block. Pass `intent["day"]` to scope the comparison
        to that day's own segment. Without a `day`, this falls back to whole-block
        matching for rules whose `effective` text is a single statement, not a per-day
        list (last_minute_prices, far_out_premium).
      - An `intent["direction"]` that is neither "down" nor "up" used to skip every
        check silently and return [] even against a literal inversion. Now rejected
        up front as its own problem.
    """
    direction = intent.get("direction")
    if direction not in ("down", "up"):
        return [f"unrecognized direction {direction!r}; expected 'down' or 'up'"]

    effective = (after or {}).get("effective")
    if not effective:
        return ["no effective block returned; the write cannot be confirmed"]
    text = str(effective)

    day = intent.get("day")
    if day:
        wanted = str(day).strip().lower()[:3]
        matches = [m for m in _EFFECTIVE_DAY_RE.finditer(text)
                  if m.group(1).lower()[:3] == wanted]
        if not matches:
            return [f"cannot find {day!r} in effective text {effective!r}; the write "
                    "cannot be confirmed for this day"]
        segment_text = " ".join(f"{m.group(2)}% {m.group(3)}" for m in matches).lower()
    else:
        segment_text = text.lower()
        # Without a day, "discount"/"premium" are substring tests over the WHOLE block.
        # That is fine for a single-statement rule (last_minute/far_out), which only ever
        # has one sign in it -- but a block that contains BOTH is exactly the day-of-week
        # shape this fix exists for, and guessing which one the caller meant is the same
        # mistake this whole fix removes elsewhere. Say so instead of guessing.
        if "discount" in segment_text and "premium" in segment_text:
            return [f"effective text mixes discount and premium ({effective!r}); pass "
                    "intent['day'] to confirm a specific day rather than guessing "
                    "which one applies"]

    saw_down = "discount" in segment_text
    saw_up = "premium" in segment_text
    problems = []
    if direction == "down" and not saw_down:
        problems.append(f"intended a discount, effective reads {effective!r}")
    if direction == "up" and not saw_up:
        problems.append(f"intended a premium, effective reads {effective!r}")
    if direction == "down" and saw_up and not saw_down:
        problems.append("SIGN INVERTED: a discount was written as a premium")
    magnitudes = [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", segment_text)]
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
