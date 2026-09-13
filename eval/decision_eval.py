#!/usr/bin/env python3
"""Decision-level eval: do the reducers change the decision?

For each property, the same model, the same runbook (SKILL.md + references) and the same
task are run under two conditions that differ ONLY in the Step 4 data block:

  full      the raw tool payloads, exactly as the MCP tools / REST calls returned them
            (prices with `reason`, the whole neighborhood payload, every reservation row,
            the raw PMS calendar, the raw AirROI comparables, listing_metrics)
  reduced   the stdout of the fetch/ reducers, exactly as the runbook consumes it

Both conditions are built from the SAME cached snapshot, so the only variable is the
reduction. Every rep is saved in full (trajectories/), infra failures go to errors.jsonl and
never into results.jsonl, and the report attributes each disagreement to noise (a condition
disagrees with itself) or to the reduction (both conditions are internally consistent and
disagree with each other).

Subcommands (run from the repo root):
  roster   build _private/eval/roster.json from the cached PriceLabs + Hospitable metadata
  build    run the reducers, fetch the raw payloads, write bundles/<id8>/{shared,reduced,full}.md
  count    count_tokens for every bundle and estimate the cost of a run
  run      call the model: --condition reduced|full --reps N [--listing id8 ...]
  report   compare, attribute, write report.md + summary.json

Nothing under _private/ is ever committed. Keys are read from --env-file paths listed in the
roster (never printed). The Anthropic key comes from ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILL_DIR = ROOT / "revenue-manager-plugin" / "skills" / "revenue-manager"
FETCH = SKILL_DIR / "fetch"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FETCH))

from compare import HARD, SOFT, attribute  # noqa: E402
from schema import DECISION_SCHEMA  # noqa: E402

MODEL = "claude-opus-5"
PRICE_PER_M = {"input": 5.0, "output": 25.0, "cache_write_5m": 6.25, "cache_write_1h": 10.0, "cache_read": 0.5}
REASON_DAYS = 90
REFERENCES = ["framework.md", "pms-fields.md", "pricing-tool-fields.md", "evidence.md", "enrichment.md"]
PY = sys.executable


# ----------------------------------------------------------------------------- helpers
def _cache_root() -> Path:
    from _cache import cache_dir  # noqa: WPS433
    return Path(cache_dir("pricelabs")).parent


def load_env_files(paths: list[str]) -> None:
    for p in paths:
        p = os.path.expanduser(p)
        if not os.path.isfile(p):
            continue
        for line in open(p):
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
            if m and not os.environ.get(m.group(1)):
                os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def jdump(obj) -> str:
    # Compact, lossless, key order as returned. The MCP wrappers pretty-print (indent=2), which
    # costs 35-70% more tokens for the same information and pushed three of eight FULL bundles
    # past the 1M window; measured on the largest market payload: 560k tokens pretty vs 369k compact.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def read_roster(path: str) -> dict:
    r = json.load(open(os.path.expanduser(path)))
    load_env_files(r.get("env_files", []))
    return r


def out_dir(args) -> Path:
    d = Path(os.path.expanduser(args.out))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ----------------------------------------------------------------------------- roster
def cmd_roster(args) -> int:
    meta = _cache_root() / "meta"
    pl = json.load(open(meta / "pricelabs_listings.json"))
    pl = pl.get("listings", pl) if isinstance(pl, dict) else pl
    ho = {p["id"]: p for p in json.load(open(meta / "hospitable_properties.json"))}
    listings = []
    for e in pl:
        p = ho.get(e["id"], {})
        cap = p.get("capacity") or {}
        coords = (p.get("address") or {}).get("coordinates") or {}
        airbnb = next((l.get("platform_id") for l in (p.get("listings") or []) if l.get("platform") == "airbnb"), None)
        listings.append({
            "id": e["id"], "name": e.get("name"), "pms": e.get("pms", "smartbnb"),
            "currency": p.get("currency") or e.get("currency"),
            "bedrooms": cap.get("bedrooms", e.get("no_of_bedrooms")),
            "baths": cap.get("bathrooms"), "guests": cap.get("max"),
            "lat": float(coords.get("latitude") or e.get("latitude")),
            "lng": float(coords.get("longitude") or e.get("longitude")),
            "airbnb_id": airbnb, "listed": p.get("listed"),
            "push_enabled": e.get("push_enabled"),
        })
    roster = {"generated": dt.date.today().isoformat(), "env_files": args.env_file or [], "listings": listings}
    Path(os.path.expanduser(args.roster)).parent.mkdir(parents=True, exist_ok=True)
    json.dump(roster, open(os.path.expanduser(args.roster), "w"), indent=1)
    print(f"roster: {len(listings)} listings -> {args.roster}")
    for l in listings:
        print(f"  {l['id'][:8]} {l['name']:<22} {l['currency']} {l['bedrooms']}bd/{l['baths']}ba/{l['guests']}g "
              f"airbnb={l['airbnb_id']} listed={l['listed']} push={l['push_enabled']}")
    return 0


# ----------------------------------------------------------------------------- build
def run_reducer(argv: list[str], env: dict) -> dict:
    t0 = time.time()
    p = subprocess.run([PY] + argv, cwd=str(FETCH), env=env, capture_output=True, text=True, timeout=900)
    return {"cmd": "python3 " + " ".join(argv), "exit": p.returncode, "secs": round(time.time() - t0, 1),
            "stdout": p.stdout, "stderr": p.stderr}


def bash_block(r: dict) -> str:
    body = r["stdout"].rstrip("\n")
    if r["stderr"].strip():
        body += "\n[stderr]\n" + r["stderr"].rstrip("\n")
    return f"### Bash tool result: `{r['cmd']}`  (exit {r['exit']})\n```\n{body}\n```\n"


def tool_block(name: str, call: dict, payload) -> str:
    return f"### MCP tool result: `{name}` called with `{json.dumps(call)}`\n```json\n{jdump(payload)}\n```\n"


def newest(pattern: str) -> Path | None:
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    return Path(files[-1]) if files else None


def build_one(l: dict, roster: dict, today: str, bdir: Path) -> dict:
    import reduce_comps  # noqa: WPS433  (cache_path)
    import reduce_prices  # noqa: WPS433  (call)

    lid, id8, pms, cur = l["id"], l["id"][:8], l["pms"], l["currency"]
    env = dict(os.environ)
    d_to = (dt.date.fromisoformat(today) + dt.timedelta(days=365)).isoformat()
    cmds = [
        ["reduce_prices.py", "--listings", f"{lid}:{pms}", "--days", "365"],
        ["reduce_reservations.py", "--listing", lid, "--pms", pms, "--currency", cur, "--today", today],
        ["reduce_neighborhood.py", "--listing", lid, "--bedrooms", str(l["bedrooms"]), "--pms", pms,
         "--lat", str(l["lat"]), "--lng", str(l["lng"]), "--currency", cur, "--today", today],
        ["reduce_comps.py", "--bedrooms", str(l["bedrooms"]), "--baths", str(float(l["baths"])), "--guests", str(l["guests"]),
         "--lat", str(l["lat"]), "--lng", str(l["lng"]), "--currency", cur,
         "--subject-id", str(l["airbnb_id"] or ""), "--subject-name", l["name"]],
        ["reconcile_pms.py", "--days", "365", "--listing", lid, "--pms", pms],
        ["reduce_overrides.py", "--listing", lid, "--pms", pms, "--today", today],
    ]
    results = [run_reducer(c, env) for c in cmds]
    reduced_md = "\n".join(bash_block(r) for r in results)

    # ---- FULL: the raw payloads behind those runs (same snapshot) + prices WITH reason
    croot = _cache_root()
    sources: dict[str, str] = {}
    full_parts: list[str] = []

    key = reduce_prices.load_key(None)
    reason_file = croot / "pricelabs" / f"{id8}_reason_365d_asof{today}.json"
    if not reason_file.is_file():
        for attempt in range(4):
            try:
                payload = reduce_prices.call("/v1/listing_prices", key, {"listings": [
                    {"id": lid, "pms": pms, "dateFrom": today, "dateTo": d_to, "reason": True}]})
                break
            except SystemExit as e:  # reduce_prices.die() on 429 / HTTP errors
                if attempt == 3:
                    raise RuntimeError(f"prices+reason fetch failed for {id8}: {e}")
                print(f"    prices+reason fetch for {id8} failed ({e}); waiting 70s", flush=True)
                time.sleep(70)
        reason_file.write_text(json.dumps(payload))
    prices_reason = json.loads(reason_file.read_text())
    sources["prices_reason"] = str(reason_file)
    # The complete 365d-with-reason payload is ~400k tokens on its own and pushes one property
    # past the model's 1M context (measured: 1,058,676 tokens for the whole FULL bundle). Keep
    # `reason` for the first REASON_DAYS dates, where overrides are actually decided, and the
    # plain row beyond that. Every price/status field is kept for all 365 dates.
    trimmed = []
    for item in (prices_reason if isinstance(prices_reason, list) else [prices_reason]):
        it = dict(item)
        rows = it.get("data") or []
        it["data"] = [(r if i < REASON_DAYS else {k: v for k, v in r.items() if k != "reason"})
                      for i, r in enumerate(rows)]
        trimmed.append(it)
    full_parts.append(tool_block(
        f"pricelabs_get_listing_prices (365 days; `reason` retained for the first {REASON_DAYS} dates only, "
        f"the complete reason payload does not fit the context window)",
        {"listing_id": lid, "pms": pms, "dateFrom": today, "dateTo": d_to, "reason": True},
        trimmed if isinstance(prices_reason, list) else trimmed[0]))

    plain = newest(str(croot / "pricelabs" / f"{id8}_plain_365d_*.json"))
    if plain:
        sources["prices_plain"] = str(plain)

    nb = croot / "neighborhood" / f"nb_loc_{round(l['lat'], 2)}_{round(l['lng'], 2)}_{pms}.json"
    if nb.is_file():
        blob = json.load(open(nb)); sources["neighborhood"] = str(nb)
        full_parts.append(tool_block("pricelabs_get_neighborhood_data", {"listing_id": lid, "pms": pms}, blob["data"]))
    else:
        full_parts.append(f"### MCP tool result: `pricelabs_get_neighborhood_data`\n(no payload: {results[2]['stderr'].strip()[:300]})\n")

    d_back = (dt.date.fromisoformat(today) - dt.timedelta(days=730)).isoformat()
    res = croot / "reservations" / f"res_{id8}_{pms}_{d_back}_{d_to}.json"
    if res.is_file():
        blob = json.load(open(res)); sources["reservations"] = str(res)
        full_parts.append(tool_block("pricelabs_list_reservations",
                                     {"listing_id": lid, "pms": pms, "start_date": d_back, "end_date": d_to},
                                     {"data": blob["data"], "note": "guest name/email/phone fields removed before caching"}))
    else:
        full_parts.append("### MCP tool result: `pricelabs_list_reservations`\n(no payload cached)\n")

    met = croot / "metrics" / f"metrics_{id8}_{pms}.json"
    if met.is_file():
        blob = json.load(open(met)); sources["metrics"] = str(met)
        full_parts.append(tool_block("pricelabs listing_metrics (REST /v1/listing_metrics)", {"listing_id": lid, "pms_name": pms}, blob["data"]))

    rec = newest(str(croot / "reconcile" / f"{id8}_*.json"))
    if rec:
        blob = json.load(open(rec)); sources["reconcile_bundle"] = str(rec)
        w = blob.get("window") or [None, None]
        full_parts.append(tool_block("hospitable_get_property_calendar",
                                     {"propertyId": lid, "start_date": w[0], "end_date": w[1]},
                                     {"data": {"start_date": w[0], "end_date": w[1], "days": blob["pms_days"]}}))
    else:
        full_parts.append("### MCP tool result: `hospitable_get_property_calendar`\n(no calendar bundle: the gate could not read this listing)\n")

    params = {"bedrooms": int(l["bedrooms"]), "baths": float(l["baths"]), "guests": int(l["guests"]), "radius": 0,
              "latitude": l["lat"], "longitude": l["lng"]}
    comps = Path(reduce_comps.cache_path(params))
    if comps.is_file():
        blob = json.load(open(comps)); sources["airroi"] = str(comps)
        full_parts.append(tool_block("mcp__airroi__get_comparables", blob.get("request", params), {"listings": blob["listings"]}))
    else:
        full_parts.append(f"### MCP tool result: `mcp__airroi__get_comparables`\n(no payload: {results[3]['stderr'].strip()[:300]})\n")

    # ---- SHARED: listing record + minimal PMS property projection (both conditions)
    meta = croot / "meta"
    pl = json.load(open(meta / "pricelabs_listings.json"))
    pl = pl.get("listings", pl) if isinstance(pl, dict) else pl
    rec_pl = next((e for e in pl if e.get("id") == lid), {})
    ho = next((p for p in json.load(open(meta / "hospitable_properties.json")) if p.get("id") == lid), {})
    ho_min = {k: ho.get(k) for k in ("id", "name", "currency", "capacity", "listed", "property_type", "room_type", "timezone")}
    ho_min["address"] = {k: (ho.get("address") or {}).get(k) for k in ("city", "state", "country", "coordinates")}
    ho_min["listings"] = [{"platform": x.get("platform"), "platform_id": x.get("platform_id")} for x in (ho.get("listings") or [])]
    # active overrides / DSOs: raw rows on the FULL side (what `pricelabs_list_overrides` returns),
    # the reducer's run table on the REDUCED side (already in reduced_md via the 6th reducer)
    ov_file = croot / "overrides" / f"ov_{id8}_{pms}.json"
    if ov_file.is_file():
        blob = json.load(open(ov_file)); sources["overrides"] = str(ov_file)
        full_parts.append(tool_block("pricelabs_list_overrides", {"listing_id": lid, "pms": pms}, blob["data"]))
    else:
        full_parts.append(f"### MCP tool result: `pricelabs_list_overrides`\n(no payload: {results[5]['stderr'].strip()[:300]})\n")
    shared_md = (tool_block("pricelabs_list_listings (this listing's record)", {"id": lid}, rec_pl)
                 + tool_block("hospitable_get_property (projection: no descriptions, rules or credentials)", {"propertyId": lid}, ho_min))

    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "shared.md").write_text(shared_md)
    (bdir / "reduced.md").write_text(reduced_md)
    (bdir / "full.md").write_text("\n".join(full_parts))
    meta_out = {"listing": l, "today": today, "built": dt.datetime.now().isoformat(timespec="seconds"),
                "reducers": [{k: v for k, v in r.items() if k not in ("stdout", "stderr")} for r in results],
                "sources": {k: {"path": v, "sha256_16": sha(Path(v))} for k, v in sources.items()},
                "bytes": {"shared": len(shared_md), "reduced": len(reduced_md), "full": len("\n".join(full_parts))}}
    # prices in both conditions must agree (the two pulls are minutes apart)
    try:
        rows_r = {}
        if plain:
            pp = json.loads(plain.read_text())
            for item in (pp if isinstance(pp, list) else [pp]):
                if item.get("id") == lid:
                    rows_r = {r["date"]: r.get("price") for r in item.get("data", [])}
        rows_f = {}
        for item in (prices_reason if isinstance(prices_reason, list) else [prices_reason]):
            if item.get("id") == lid:
                rows_f = {r["date"]: r.get("price") for r in item.get("data", [])}
        common = set(rows_r) & set(rows_f)
        meta_out["price_snapshot_agreement"] = {"common_dates": len(common),
                                                "mismatches": sum(1 for d in common if rows_r[d] != rows_f[d])}
    except Exception as e:  # noqa: BLE001
        meta_out["price_snapshot_agreement"] = {"error": str(e)[:200]}
    json.dump(meta_out, open(bdir / "meta.json", "w"), indent=1)
    return meta_out


def cmd_build(args) -> int:
    roster = read_roster(args.roster)
    od = out_dir(args)
    today = args.today or dt.date.today().isoformat()
    want = set(args.listing or [])
    for l in roster["listings"]:
        if want and l["id"][:8] not in want:
            continue
        bdir = od / "bundles" / l["id"][:8]
        if args.pause and not (bdir / "meta.json").is_file():
            time.sleep(args.pause)   # PriceLabs allows 60 calls/min; a listing costs ~8
        m = build_one(l, roster, today, bdir)
        ex = " ".join(f"{r['cmd'].split()[1]}={r['exit']}" for r in m["reducers"])
        print(f"{l['id'][:8]} {l['name']:<22} shared={m['bytes']['shared']:>6}B reduced={m['bytes']['reduced']:>7}B "
              f"full={m['bytes']['full']:>9}B | {ex} | prices agree: {m['price_snapshot_agreement']}")
    return 0


# ----------------------------------------------------------------------------- prompts
def system_text() -> str:
    body = (SKILL_DIR / "SKILL.md").read_text()
    body = re.sub(r"\A---\n.*?\n---\n", "", body, count=1, flags=re.S)
    parts = ["# SKILL.md (the runbook)\n", body]
    for ref in REFERENCES:
        parts.append(f"\n\n# references/{ref}\n\n" + (SKILL_DIR / "references" / ref).read_text())
    return "".join(parts)


EVAL_INSTRUCTIONS = """
# EVAL HARNESS MODE (read this last, it overrides the runbook's interactive steps)

You are running Steps 5, 6 and 7 of the runbook above for ONE property, offline.
- Every Step 4 pull has already been executed. Its output is pasted in the user message exactly as the tool or script returned it. Tools are not available; do not ask for more data. If a source is missing or a reducer exited 2, apply the runbook's rule for that case (do not use that source this run; say so via DATA_SOURCE_FAILED and data_status).
- Step 0 detection result: PMS = Hospitable (MCP `hospitable`), pricing tool = PriceLabs (MCP `pricelabs`), enrichment: AirROI present, RankBreeze and Turno absent.
- Step 3: the Supabase audit tables exist and are empty for this property (no prior recommendations, no change log, no stored markup).
- Today's date is given in the user message. The PMS calendar is ground truth for availability; PriceLabs is ground truth for price and market.
- Produce the Step 7 recommendation set as JSON matching the output schema. One `changes` entry per recommended change, with `pct_move` relative to the current value (negative = lower). If you recommend no change, return an empty `changes` array and overall_direction "hold". If the gate blocks pricing, say so in `gate.status` and overall_direction "blocked".
- Every number in `facts` must come from the data provided; use null when the data does not support it. Do not invent comps, markups or occupancy.
- Schema conventions: gate counters (`invisible_nights`, `min_stay_mismatches`, `drift_dates`) are -1 when the gate did not run; `subject_revenue_rank` is "" when unknown (else e.g. "24/25"); `date_from`/`date_to` are "" for account-level fields (base/min/max/min_stay) and YYYY-MM-DD for dated changes.
"""


def task_text(meta: dict) -> str:
    l = meta["listing"]
    return (f"Today is {meta['today']}. Run Steps 5-7 for **{l['name']}** (listing `{l['id']}`, PMS `{l['pms']}`, "
            f"currency {l['currency']}). Return the recommendation set as JSON per the schema.")


def build_request(bdir: Path, condition: str) -> tuple[list[dict], list[dict], dict]:
    meta = json.load(open(bdir / "meta.json"))
    system = [{"type": "text", "text": system_text() + EVAL_INSTRUCTIONS,
               "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    data = (bdir / f"{condition}.md").read_text()
    user = [
        {"type": "text", "text": "# Step 4 pulls, shared (both agents)\n\n" + (bdir / "shared.md").read_text()},
        {"type": "text", "text": f"# Step 4 pulls, condition={condition}\n\n" + data},
        # 1h TTL: a rep runs 6-10 minutes, longer than the 5m TTL, so with 5m the next rep
        # re-wrote the whole data block (measured: cw identical on rep 1 and rep 2).
        {"type": "text", "text": task_text(meta), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
    ]
    return system, [{"role": "user", "content": user}], meta


def client():
    import anthropic  # noqa: WPS433
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(max_retries=0, timeout=anthropic.Timeout(3600.0, connect=30.0))


# ----------------------------------------------------------------------------- count
def cmd_count(args) -> int:
    roster = read_roster(args.roster)
    od = out_dir(args)
    c = client()
    rows = []
    for l in roster["listings"]:
        bdir = od / "bundles" / l["id"][:8]
        if not (bdir / "meta.json").is_file():
            continue
        for cond in ("reduced", "full"):
            system, messages, _ = build_request(bdir, cond)
            n = c.messages.count_tokens(model=MODEL, system=system, messages=messages).input_tokens
            rows.append({"listing": l["id"][:8], "name": l["name"], "condition": cond, "input_tokens": n})
            print(f"{l['id'][:8]} {l['name']:<22} {cond:<8} {n:>9,} tokens")
    json.dump(rows, open(od / "counts.json", "w"), indent=1)
    sys_tokens = c.messages.count_tokens(model=MODEL, system=[{"type": "text", "text": system_text() + EVAL_INSTRUCTIONS}],
                                         messages=[{"role": "user", "content": "x"}]).input_tokens
    tot = {"reduced": 0, "full": 0}
    for r in rows:
        tot[r["condition"]] += r["input_tokens"]
    print(f"\nsystem prompt (runbook + references + eval instructions): {sys_tokens:,} tokens, cached once per hour")
    for cond, reps in (("reduced", args.reps_reduced), ("full", args.reps_full)):
        first = tot[cond] * PRICE_PER_M["cache_write_5m"] / 1e6
        later = tot[cond] * PRICE_PER_M["cache_read"] / 1e6 * max(reps - 1, 0)
        print(f"{cond:<8} {tot[cond]:>10,} input tokens/rep x {reps} reps: ~${first + later:,.2f} input "
              f"(rep 1 written to cache, later reps read it) + output/thinking")
    return 0


# ----------------------------------------------------------------------------- run
_lock = threading.Lock()


def append_jsonl(path: Path, row: dict) -> None:
    with _lock:
        with open(path, "a") as fh:
            fh.write(json.dumps(row) + "\n")


def usage_dict(u) -> dict:
    d = {"input_tokens": getattr(u, "input_tokens", 0) or 0, "output_tokens": getattr(u, "output_tokens", 0) or 0,
         "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
         "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0}
    cc = getattr(u, "cache_creation", None)
    if cc is not None:
        d["cache_creation_5m"] = getattr(cc, "ephemeral_5m_input_tokens", 0) or 0
        d["cache_creation_1h"] = getattr(cc, "ephemeral_1h_input_tokens", 0) or 0
    return d


def cost_usd(u: dict) -> float:
    w5 = u.get("cache_creation_5m")
    w1 = u.get("cache_creation_1h")
    if w5 is None and w1 is None:
        w5, w1 = u.get("cache_creation_input_tokens", 0), 0
    return (u["input_tokens"] * PRICE_PER_M["input"] + u["output_tokens"] * PRICE_PER_M["output"]
            + u["cache_read_input_tokens"] * PRICE_PER_M["cache_read"]
            + (w5 or 0) * PRICE_PER_M["cache_write_5m"] + (w1 or 0) * PRICE_PER_M["cache_write_1h"]) / 1e6


def call_once(c, system, messages, effort: str, max_tokens: int):
    import anthropic  # noqa: WPS433
    attempts, last_err = 0, None
    while attempts < 4:
        attempts += 1
        t0 = time.time()
        try:
            with c.messages.stream(
                model=MODEL, max_tokens=max_tokens, system=system, messages=messages,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
            ) as stream:
                final = stream.get_final_message()
            return final, attempts, round(time.time() - t0, 1), None
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError,
                anthropic.APITimeoutError) as e:
            last_err = e
            status = getattr(e, "status_code", None)
            if isinstance(e, anthropic.APIStatusError) and status not in (429, 500, 502, 503, 529):
                break
            delay = min(30 * 2 ** (attempts - 1), 300) + random.uniform(0, 10)
            print(f"    retry {attempts}: {type(e).__name__} {status or ''}; sleeping {delay:.0f}s", flush=True)
            time.sleep(delay)
        except anthropic.APIStatusError as e:  # 4xx: not retryable
            last_err = e
            break
    return None, attempts, None, last_err


def run_case(c, od: Path, bdir: Path, cond: str, rep: int, effort: str, max_tokens: int) -> str:
    system, messages, meta = build_request(bdir, cond)
    id8 = meta["listing"]["id"][:8]
    tag = f"{id8}_{cond}_r{rep}"
    final, attempts, secs, err = call_once(c, system, messages, effort, max_tokens)
    if final is None:
        append_jsonl(od / "errors.jsonl", {"listing": id8, "condition": cond, "rep": rep, "attempts": attempts,
                                          "error_class": type(err).__name__, "message": str(err)[:500],
                                          "at": dt.datetime.now().isoformat(timespec="seconds")})
        return f"{tag}: ERROR {type(err).__name__} after {attempts} attempts"
    content = []
    text = ""
    for b in final.content:
        if b.type == "thinking":
            content.append({"type": "thinking", "summary": getattr(b, "thinking", "")})
        elif b.type == "text":
            content.append({"type": "text", "text": b.text}); text += b.text
        else:
            content.append({"type": b.type})
    usage = usage_dict(final.usage)
    traj = {"tag": tag, "listing": id8, "condition": cond, "rep": rep, "model": final.model, "stop_reason": final.stop_reason,
            "request_id": getattr(final, "_request_id", None), "usage": usage, "cost_usd": round(cost_usd(usage), 4),
            "latency_s": secs, "attempts": attempts, "effort": effort, "bundle_meta": meta, "content": content,
            "at": dt.datetime.now().isoformat(timespec="seconds")}
    (od / "trajectories").mkdir(exist_ok=True)
    json.dump(traj, open(od / "trajectories" / f"{tag}.json", "w"), indent=1)
    if not final.model.startswith(MODEL):
        append_jsonl(od / "errors.jsonl", {"listing": id8, "condition": cond, "rep": rep, "error_class": "served_model_mismatch",
                                          "message": final.model, "attempts": attempts})
        return f"{tag}: ERROR served by {final.model}"
    status = "ok"
    decision = None
    if final.stop_reason == "max_tokens":
        status = "truncated"
    elif final.stop_reason == "refusal":
        status = "refusal"
    else:
        try:
            decision = json.loads(text)
        except json.JSONDecodeError as e:
            append_jsonl(od / "errors.jsonl", {"listing": id8, "condition": cond, "rep": rep, "error_class": "parse_error",
                                              "message": str(e)[:300], "attempts": attempts})
            return f"{tag}: ERROR unparseable output"
    append_jsonl(od / "results.jsonl", {"listing": id8, "condition": cond, "rep": rep, "status": status,
                                       "stop_reason": final.stop_reason, "model": final.model, "usage": usage,
                                       "cost_usd": round(cost_usd(usage), 4), "latency_s": secs, "attempts": attempts,
                                       "decision": decision, "at": traj["at"]})
    d = decision or {}
    return (f"{tag}: {status} {secs}s in={usage['input_tokens']:,} cr={usage['cache_read_input_tokens']:,} "
            f"cw={usage['cache_creation_input_tokens']:,} out={usage['output_tokens']:,} ${cost_usd(usage):.2f} "
            f"| dir={d.get('overall_direction')} gate={(d.get('gate') or {}).get('status')} changes={len(d.get('changes') or [])} flags={d.get('flags')}")


def cmd_run(args) -> int:
    roster = read_roster(args.roster)
    od = out_dir(args)
    c = client()
    want = set(args.listing or [])
    done = set()
    if (od / "results.jsonl").is_file() and not args.redo:
        for line in open(od / "results.jsonl"):
            r = json.loads(line)
            if r.get("status") == "ok":       # a truncated/refused rep is re-run, not skipped
                done.add((r["listing"], r["condition"], r["rep"]))
    jobs = []
    for l in roster["listings"]:
        id8 = l["id"][:8]
        if want and id8 not in want:
            continue
        bdir = od / "bundles" / id8
        if not (bdir / "meta.json").is_file():
            print(f"{id8}: no bundle, skipped"); continue
        reps = [r for r in range(1, args.reps + 1) if (id8, args.condition, r) not in done]
        if reps:
            jobs.append((bdir, reps))

    def worker(job):
        bdir, reps = job
        lines = []
        for r in reps:  # reps back to back so the data block is served from cache
            line = run_case(c, od, bdir, args.condition, r, args.effort, args.max_tokens)
            print("  " + line, flush=True)
            lines.append(line)
        return lines

    print(f"condition={args.condition} reps={args.reps} effort={args.effort} jobs={len(jobs)} workers={args.workers}")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(worker, jobs))
    return 0


# ----------------------------------------------------------------------------- report
def cmd_report(args) -> int:
    roster = read_roster(args.roster)
    od = out_dir(args)
    rows = [json.loads(x) for x in open(od / "results.jsonl")] if (od / "results.jsonl").is_file() else []
    errs = [json.loads(x) for x in open(od / "errors.jsonl")] if (od / "errors.jsonl").is_file() else []
    by = {}
    for r in rows:
        if r["status"] == "ok" and r["decision"]:
            by.setdefault(r["listing"], {"reduced": [], "full": []})[r["condition"]].append(r)
    names = {l["id"][:8]: l["name"] for l in roster["listings"]}
    lines = [f"# Decision eval report  ({dt.datetime.now().isoformat(timespec='minutes')})\n",
             f"Model `{MODEL}`. Rows scored: {sum(1 for r in rows if r['status']=='ok')} ok, "
             f"{sum(1 for r in rows if r['status']!='ok')} truncated/refused, {len(errs)} infra errors (errors.jsonl).\n"]
    summary = {"listings": {}, "diverging_listings": [], "noise_keys": {}, "cost_usd": {}}
    for cond in ("reduced", "full"):
        cs = [r for r in rows if r["condition"] == cond]
        if cs:
            summary["cost_usd"][cond] = round(sum(r["cost_usd"] for r in cs), 2)
            summary.setdefault("tokens", {})[cond] = {
                "reps": len(cs),
                "input_median": sorted(r["usage"]["input_tokens"] + r["usage"]["cache_read_input_tokens"] + r["usage"]["cache_creation_input_tokens"] for r in cs)[len(cs)//2],
                "output_median": sorted(r["usage"]["output_tokens"] for r in cs)[len(cs)//2],
                "latency_median_s": sorted(r["latency_s"] for r in cs)[len(cs)//2]}
    lines.append("## Cost and size per condition\n")
    for cond, t in summary.get("tokens", {}).items():
        lines.append(f"- **{cond}**: {t['reps']} reps, median input {t['input_median']:,} tokens, median output "
                     f"{t['output_median']:,}, median latency {t['latency_median_s']}s, total ${summary['cost_usd'][cond]}")
    lines.append("")
    hard_div = 0
    for id8 in sorted(by, key=lambda k: names.get(k, k)):
        red, ful = by[id8]["reduced"], by[id8]["full"]
        lines.append(f"## {names.get(id8, id8)} (`{id8}`): reduced x{len(red)}, full x{len(ful)}\n")
        if not red or not ful:
            lines.append("_one condition has no scored reps yet_\n"); continue
        att = attribute([r["decision"] for r in red], [r["decision"] for r in ful])
        div = {k: v for k, v in att.items() if v["status"] == "DIVERGE"}
        noise = {k: v for k, v in att.items() if v["status"] == "NOISE"}
        hard = {k: v for k, v in div.items() if v["severity"] == HARD}
        soft = {k: v for k, v in div.items() if v["severity"] == SOFT}
        summary["listings"][id8] = {"name": names.get(id8), "hard_diverge": sorted(hard), "soft_diverge": sorted(soft),
                                    "noise": sorted(noise), "agree": sorted(k for k, v in att.items() if v["status"] == "AGREE")}
        if hard:
            hard_div += 1; summary["diverging_listings"].append(id8)
        for k in sorted(noise):
            summary["noise_keys"][k] = summary["noise_keys"].get(k, 0) + 1
        lines.append(f"**HARD diverge: {len(hard)}  SOFT diverge: {len(soft)}  noise: {len(noise)}  agree: "
                     f"{sum(1 for v in att.values() if v['status']=='AGREE')}**\n")
        lines.append("| key | status | sev | reduced reps | full reps |\n|---|---|---|---|---|")
        for k, v in att.items():
            if v["status"] == "AGREE" and not k.startswith(("gate", "direction", "global:")):
                continue
            lines.append(f"| `{k}` | {v['status']} | {v['severity'] or ''} | {v['reduced']} | {v['full']} |")
        lines.append("")
        # facts vs ground truth computed from the raw caches (adjudication by numbers)
        try:
            from truth import check_facts, truth_for  # noqa: WPS433
            tr = truth_for(json.load(open(od / "bundles" / id8 / "meta.json")))
        except Exception as e:  # noqa: BLE001
            tr = {}; lines.append(f"_truth unavailable: {e}_\n")
        if tr:
            lines.append("**Reported facts vs ground truth** (computed from the raw caches; ok = within tolerance)\n")
            lines.append("| rep | " + " | ".join(k for k in tr if k in ("invisible_nights", "markup_median", "min_stay_mismatches", "pct_dates_at_floor", "market_p50_median_next_90", "market_occupancy_next_90_pct", "comp_count", "subject_revenue_rank", "comp_median_adr", "cleared_adr_trailing_365")) + " | score |")
            keys = [k for k in tr if k in ("invisible_nights", "markup_median", "min_stay_mismatches", "pct_dates_at_floor", "market_p50_median_next_90", "market_occupancy_next_90_pct", "comp_count", "subject_revenue_rank", "comp_median_adr", "cleared_adr_trailing_365")]
            lines.append("|---|" + "---|" * (len(keys) + 1))
            lines.append("| truth | " + " | ".join(str(tr[k]) for k in keys) + " | |")
            fact_scores = {"reduced": [], "full": []}
            for cond, reps in (("reduced", red), ("full", ful)):
                for r in reps:
                    cf = check_facts(r["decision"], tr)
                    cells = []
                    for k in keys:
                        if k in cf:
                            rv, tv, ok = cf[k]; cells.append(f"{rv}{'' if ok else ' **X**'}")
                        else:
                            cells.append("")
                    n_ok = sum(1 for v in cf.values() if v[2]); n = len(cf)
                    fact_scores[cond].append((n_ok, n))
                    lines.append(f"| {cond} r{r['rep']} | " + " | ".join(cells) + f" | {n_ok}/{n} |")
            summary["listings"][id8]["fact_scores"] = fact_scores
            lines.append("")
        lines.append("<details><summary>facts per rep (for adjudication)</summary>\n")
        for cond, reps in (("reduced", red), ("full", ful)):
            for r in reps:
                d = r["decision"]
                lines.append(f"- {cond} r{r['rep']}: gate={d['gate']} facts={d['facts']} flags={d['flags']}")
                for ch in d["changes"]:
                    lines.append(f"    - {ch['field']} {ch['action']} {ch.get('old')}->{ch.get('new')} ({ch.get('pct_move')}%) "
                                 f"{ch.get('date_from') or ''}..{ch.get('date_to') or ''} [{ch['confidence']}] {ch['reason'][:160]}")
                lines.append(f"    summary: {d['summary'][:400]}")
        lines.append("\n</details>\n")
    lines.insert(2, f"**Listings with an attributable HARD divergence: {hard_div}/{len(by)}.** "
                    f"(A divergence is attributable only when both conditions are internally consistent across reps.)\n")
    (od / "report.md").write_text("\n".join(lines))
    json.dump(summary, open(od / "summary.json", "w"), indent=1)
    print("\n".join(lines[:12]))
    print(f"... full report: {od / 'report.md'}")
    return 0


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default="_private/eval/roster.json")
    ap.add_argument("--out", default=None, help="evidence dir (default _private/evidence/eval-<today>)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("roster"); s.add_argument("--env-file", action="append")
    s = sub.add_parser("build"); s.add_argument("--today"); s.add_argument("--listing", action="append")
    s.add_argument("--pause", type=float, default=12.0, help="seconds between listings that need live pulls")
    s = sub.add_parser("count"); s.add_argument("--reps-reduced", type=int, default=3); s.add_argument("--reps-full", type=int, default=2)
    s = sub.add_parser("run"); s.add_argument("--condition", choices=["reduced", "full"], required=True)
    s.add_argument("--reps", type=int, default=1); s.add_argument("--listing", action="append")
    s.add_argument("--effort", default="xhigh"); s.add_argument("--max-tokens", type=int, default=64000)
    s.add_argument("--workers", type=int, default=1); s.add_argument("--redo", action="store_true")
    sub.add_parser("report")
    args = ap.parse_args()
    if args.out is None:
        args.out = f"_private/evidence/eval-{dt.date.today().isoformat()}"
    return {"roster": cmd_roster, "build": cmd_build, "count": cmd_count, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
