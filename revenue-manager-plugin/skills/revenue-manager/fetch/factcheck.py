#!/usr/bin/env python3
"""Fact-class harness: proves a reducer preserved every fact a pricing decision reads.

WHY
---
In August a "cheaper" tier dropped four fields that looked like noise and inverted a
verdict on one listing. Token cuts are only safe when the facts the decision depends on
survive the cut, so every reducer in this directory must pass this harness before it
ships, and the smoke test runs it on every commit.

HOW
---
For each source there are two extractors that compute the SAME named facts:

  *_facts_full(raw)      reads the untouched API payload
  *_facts_reduced(text)  parses the reducer's printed output

They deliberately share no parsing code. If the reducer mangles a number, the two sides
disagree and the check fails. `compare()` lists every mismatch by name.

Precision is fixed here and the reducers import it, so "equal" means equal at the
precision the decision actually uses (an ADR of 538.94 vs 538.9 is not a lost fact).

USAGE
-----
    python3 factcheck.py airroi --full raw.json --reduced reduced.txt [--subject-id ID]
    exit 0 = every fact matches, exit 1 = mismatch (listed), exit 2 = could not check
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import sys

# One place for precision. Reducers round to these; extractors compare at these.
PRECISION = {
    "adr": 1, "occ": 3, "revenue": 0, "revpar": 1, "rating": 2, "min_nights": 0,
}


def _r(value, kind: str):
    if value is None or value == "":
        return None
    v = round(float(value), PRECISION[kind])
    return int(v) if PRECISION[kind] == 0 else v


def _median(values, kind):
    # Round each input to decision precision FIRST. A decision only ever sees rounded
    # values, so the fact is "the median of what it sees". Aggregating raw values and
    # rounding the result can differ by one unit in the last place (780.27 vs 780.25),
    # which is not a lost fact, it is double rounding. The harness caught this on its
    # first run; do not "fix" it by adding decimals to the CSV.
    vals = [_r(v, kind) for v in values if v not in (None, "")]
    return _r(statistics.median(vals), kind) if vals else None


def _quartile(values, q, kind):
    vals = sorted(_r(v, kind) for v in values if v not in (None, ""))
    if not vals:
        return None
    # nearest-rank quartile: deterministic, no interpolation to argue about
    idx = max(0, min(len(vals) - 1, round(q * (len(vals) - 1))))
    return _r(vals[idx], kind)


# ---------------------------------------------------------------- AirROI comparables

AIRROI_FACTS = [
    "comp_count", "currency", "adr_median", "adr_p25", "adr_p75", "occ_median",
    "revenue_median", "revpar_median", "rating_median", "min_nights_median",
    "top5_by_revenue", "subject_in_set", "subject_rank_revenue",
]

# The CSV columns the reducer must emit, in order. The harness parses by header name,
# so extra columns are tolerated; missing ones are a failure.
AIRROI_COLUMNS = [
    "listing_id", "name", "bedrooms", "baths", "guests", "ttm_revenue", "ttm_adr",
    "ttm_occ", "ttm_revpar", "rating", "reviews", "currency", "min_nights", "los",
]


def _comp_rows_from_raw(raw: dict) -> list[dict]:
    """Flatten the nested AirROI comp into the same shape the CSV carries."""
    out = []
    for c in raw.get("listings", []):
        li, pd, pm = c.get("listing_info", {}), c.get("property_details", {}), c.get("performance_metrics", {})
        rt, pi, bs = c.get("ratings", {}), c.get("pricing_info", {}), c.get("booking_settings", {})
        out.append({
            "listing_id": str(li.get("listing_id", "")),
            "name": li.get("listing_name", ""),
            "bedrooms": pd.get("bedrooms"), "baths": pd.get("baths"), "guests": pd.get("guests"),
            "ttm_revenue": pm.get("ttm_revenue"), "ttm_adr": pm.get("ttm_avg_rate"),
            "ttm_occ": pm.get("ttm_occupancy"), "ttm_revpar": pm.get("ttm_revpar"),
            "rating": rt.get("rating_overall"), "reviews": rt.get("num_reviews"),
            "currency": pi.get("currency"), "min_nights": bs.get("min_nights"),
            "los": pm.get("ttm_avg_length_of_stay"),
        })
    return out


def _facts_from_rows(rows: list[dict], subject_id: str | None, subject_rank: int | None,
                     subject_in_set: bool) -> dict:
    comps = [r for r in rows if not (subject_id and str(r["listing_id"]) == str(subject_id))]
    by_rev = sorted(comps, key=lambda r: (-(float(r["ttm_revenue"] or 0)), str(r["listing_id"])))
    currencies = sorted({str(r["currency"]) for r in comps if r.get("currency")})
    return {
        "comp_count": len(comps),
        "currency": currencies[0] if len(currencies) == 1 else f"MIXED:{','.join(currencies)}",
        "adr_median": _median((r["ttm_adr"] for r in comps), "adr"),
        "adr_p25": _quartile([r["ttm_adr"] for r in comps], 0.25, "adr"),
        "adr_p75": _quartile([r["ttm_adr"] for r in comps], 0.75, "adr"),
        "occ_median": _median((r["ttm_occ"] for r in comps), "occ"),
        "revenue_median": _median((r["ttm_revenue"] for r in comps), "revenue"),
        "revpar_median": _median((r["ttm_revpar"] for r in comps), "revpar"),
        "rating_median": _median((r["rating"] for r in comps), "rating"),
        "min_nights_median": _median((r["min_nights"] for r in comps), "min_nights"),
        "top5_by_revenue": [str(r["listing_id"]) for r in by_rev[:5]],
        "subject_in_set": subject_in_set,
        "subject_rank_revenue": subject_rank,
    }


def airroi_facts_full(raw: dict, subject_id: str | None = None) -> dict:
    rows = _comp_rows_from_raw(raw)
    rank, in_set = None, False
    if subject_id:
        ranked = sorted(rows, key=lambda r: (-(float(r["ttm_revenue"] or 0)), str(r["listing_id"])))
        for i, r in enumerate(ranked, 1):
            if str(r["listing_id"]) == str(subject_id):
                rank, in_set = i, True
    return _facts_from_rows(rows, subject_id, rank, in_set)


def airroi_facts_reduced(text: str) -> dict:
    """Parse the reducer's output: a '# key=value ...' header line, then a CSV block."""
    header, csv_lines = {}, []
    for line in text.splitlines():
        if line.startswith("# "):
            for kv in line[2:].split():
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    header[k] = v
        elif line.strip() and not line.startswith("#"):
            csv_lines.append(line)
    if not csv_lines:
        raise ValueError("no CSV block found in reduced output")
    rows = list(csv.DictReader(io.StringIO("\n".join(csv_lines))))
    missing = [c for c in AIRROI_COLUMNS if c not in (rows[0].keys() if rows else [])]
    if missing:
        raise ValueError(f"reduced CSV is missing columns: {missing}")
    subject_id = header.get("subject_id") or None
    in_set = header.get("subject_in_set", "false").lower() == "true"
    rank = int(header["subject_rank_revenue"]) if header.get("subject_rank_revenue", "none") != "none" else None
    # the reducer already excluded the subject from the CSV; pass no id so nothing is re-excluded
    facts = _facts_from_rows(rows, None, rank, in_set)
    return facts


def compare(full: dict, reduced: dict, names: list[str]) -> list[str]:
    bad = []
    for n in names:
        a, b = full.get(n), reduced.get(n)
        if a != b:
            bad.append(f"{n}: full={a!r} reduced={b!r}")
    return bad


SOURCES = {
    "airroi": (AIRROI_FACTS, airroi_facts_full, airroi_facts_reduced),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--full", required=True, help="raw API payload (JSON)")
    ap.add_argument("--reduced", required=True, help="reducer output (text)")
    ap.add_argument("--subject-id", default=None)
    args = ap.parse_args()

    names, f_full, f_red = SOURCES[args.source]
    try:
        raw_text = open(args.full, encoding="utf-8").read()
        raw = json.loads(raw_text[raw_text.find("{"):])
        full = f_full(raw, args.subject_id) if args.source == "airroi" else f_full(raw)
        reduced = f_red(open(args.reduced, encoding="utf-8").read())
    except Exception as e:  # noqa: BLE001
        print(f"COULD NOT CHECK: {e}", file=sys.stderr)
        return 2

    bad = compare(full, reduced, names)
    for n in names:
        mark = "ok  " if n not in [b.split(":")[0] for b in bad] else "FAIL"
        print(f"  {mark}  {n:22s} {full.get(n)!r}")
    if bad:
        print(f"\n{len(bad)} fact class(es) changed by the reducer:")
        for b in bad:
            print("  -", b)
        return 1
    print(f"\nall {len(names)} fact classes preserved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
