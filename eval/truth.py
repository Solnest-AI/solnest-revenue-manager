"""Ground-truth facts per bundle, computed mechanically from the raw caches the bundle was built
from (paths + hashes in meta.json). Used by the report to adjudicate a DIVERGE: when the two
conditions disagree, the one whose reported `facts` match these numbers is the one that read
the data right. The calculations reuse the shared reducer/harness functions, which the fact
harness already checks against the raw payloads."""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FETCH = HERE.parent / "revenue-manager-plugin" / "skills" / "revenue-manager" / "fetch"
sys.path.insert(0, str(FETCH))

import factcheck as fc  # noqa: E402
import reduce_comps as rc  # noqa: E402


def _load(meta: dict, key: str):
    p = (meta.get("sources") or {}).get(key, {}).get("path")
    return json.load(open(p)) if p and Path(p).is_file() else None


def truth_for(meta: dict) -> dict:
    l = meta["listing"]
    today = meta["today"]
    t: dict = {}
    d90 = (dt.date.fromisoformat(today) + dt.timedelta(days=90)).isoformat()

    rec = _load(meta, "reconcile_bundle")
    if rec:
        c = fc.calendar_rows(rec["pms_days"], rec["pl_rows"])
        t["invisible_nights"] = len(c["invisible"])
        t["markup_median"] = c.get("markup_median")
        t["min_stay_mismatches"] = c.get("min_stay_mismatch")
        t["drift_dates"] = len(c["drift"]) if isinstance(c.get("drift"), list) else c.get("drift")
        t["pms_min_mode"] = c.get("pms_min_mode")
        win = [d for d in rec["pms_days"] if today < d["date"] <= d90]
        if win:
            res = sum(1 for d in win if (d.get("status") or {}).get("reason") == "RESERVED")
            t["occupancy_next_90_pct_pms"] = round(100.0 * res / len(win), 1)
        pl = [r for k, r in rec["pl_rows"].items() if today < k <= d90]
        if pl:
            t["occupancy_next_90_pct_pricelabs"] = round(100.0 * sum(1 for r in pl if fc._cal_is_booked(r.get("booking_status"))) / len(pl), 1)

    met = _load(meta, "metrics")
    if met and isinstance(met.get("data"), dict):
        mp = met["data"].get("min_prices")
        if isinstance(mp, dict):
            v = mp.get("90")
            t["pct_dates_at_floor"] = None if v in (None, -1, -2, "-1", "-2") else float(v)

    nb = _load(meta, "neighborhood")
    if nb:
        d = nb["data"]
        cats = list(d.get("Future Percentile Prices", {}).get("Category", {}).keys())
        cat = str(l["bedrooms"]) if str(l["bedrooms"]) in cats else (cats[0] if len(cats) == 1 else None)
        if cat:
            daily = fc.neighborhood_daily_from_raw(nb, cat, 90, start=today)
            p50 = [r["p50"] for r in daily if r.get("p50") is not None]
            occ = [r["occ"] for r in daily if r.get("occ") is not None]
            t["market_p50_median_next_90"] = fc._median(p50, "nb_price") if p50 else None
            t["market_occupancy_next_90_pct"] = round(statistics.mean(occ), 1) if occ else None
            t["neighborhood_category"] = cat

    comps = _load(meta, "airroi")
    if comps:
        rows = [rc.flatten(c) for c in comps["listings"]]
        ranked = sorted(rows, key=lambda r: (-(float(r["ttm_revenue"] or 0)), r["listing_id"]))
        sid = str(l.get("airbnb_id") or "")
        rank = next((i for i, r in enumerate(ranked, 1) if r["listing_id"] == sid), None)
        others = [r for r in rows if r["listing_id"] != sid]
        t["comp_count"] = len(others)
        t["subject_revenue_rank"] = f"{rank}/{len(ranked)}" if rank else ""
        t["comp_median_adr"] = rc.median((r["ttm_adr"] for r in others), "adr") if others else None

    res = _load(meta, "reservations")
    if res:
        lo = (dt.date.fromisoformat(today) - dt.timedelta(days=365)).isoformat()
        live = [r for r in res["data"] if lo <= str(r.get("check_in", "")) < today
                and "cancel" not in str(r.get("booking_status", "")).lower() and not r.get("cancelled_on")]
        nights = sum(float(r.get("no_of_days") or 0) for r in live)
        rev = sum(float(r.get("rental_revenue") or 0) for r in live)
        t["cleared_adr_trailing_365"] = round(rev / nights, 1) if nights else None
        t["bookings_trailing_365"] = len(live)
    return t


TOL = {"invisible_nights": 0, "min_stay_mismatches": 1, "drift_dates": 2, "markup_median": 0.02,
       "pct_dates_at_floor": 1.5, "market_p50_median_next_90": 0.10, "market_occupancy_next_90_pct": 3.0,
       "comp_count": 1, "comp_median_adr": 0.10, "cleared_adr_trailing_365": 0.15}


def check_facts(decision: dict, truth: dict) -> dict[str, tuple]:
    """{fact: (reported, truth, ok)} for every fact both sides have a value for."""
    out = {}
    g, f = decision.get("gate") or {}, decision.get("facts") or {}
    rep = {**{k: g.get(k) for k in ("invisible_nights", "markup_median", "min_stay_mismatches", "drift_dates")},
           **{k: f.get(k) for k in ("pct_dates_at_floor", "market_p50_median_next_90", "market_occupancy_next_90_pct",
                                    "comp_count", "comp_median_adr", "cleared_adr_trailing_365", "subject_revenue_rank")}}
    for k, tv in truth.items():
        if k not in rep or tv is None or rep[k] in (None, -1, ""):
            continue
        rv = rep[k]
        if k == "subject_revenue_rank":
            ok = str(rv).strip() == str(tv).strip()
        else:
            tol = TOL.get(k, 0.1)
            diff = abs(float(rv) - float(tv))
            ok = diff <= (tol * abs(float(tv)) if tol < 1 and k in ("markup_median", "market_p50_median_next_90", "comp_median_adr", "cleared_adr_trailing_365") else tol)
        out[k] = (rv, tv, ok)
    return out
