#!/usr/bin/env python3
"""Generate the PriceLabs API reference from the published OpenAPI 3.1 specs.

    python3 tools/pricelabs_spec_report.py --fetch      # re-download the specs, then generate
    python3 tools/pricelabs_spec_report.py              # generate from docs/pricelabs/*.json

Writes revenue-manager-plugin/skills/revenue-manager/references/pricelabs-api.md.

Why this is generated and not hand-written: PriceLabs renamed fields on /v1/listings between
2026-08-25 and 2026-09-03 (city -> city_name, lat/lon -> latitude/longitude, push -> push_enabled)
and an ETL reading the old names silently bucketed every listing as market "unknown". A reference
anyone edits by hand goes stale the same way. Re-run with --fetch and diff.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "pricelabs"
OUTDIR = ROOT / "revenue-manager-plugin" / "skills" / "revenue-manager" / "references" / "pricelabs-api"
SOURCES = {
    "customer-api": "https://developers.pricelabs.co/openapi/customer-api.json",
    "revenue-estimator-api": "https://developers.pricelabs.co/openapi/revenue-estimator-api.json",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
VERBS = ("get", "post", "put", "patch", "delete")


def fetch() -> None:
    SPECS.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        json.loads(body)          # fail loudly rather than write an HTML error page
        (SPECS / f"{name}.json").write_bytes(body)
        print(f"fetched {name} ({len(body):,}B)")


def deref(node, spec, seen=None):
    """Resolve $ref one level at a time, cycle-safe."""
    seen = seen or set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            return {"type": "(recursive)"}
        seen.add(ref)
        cur = spec
        for part in ref.lstrip("#/").split("/"):
            cur = cur.get(part, {}) if isinstance(cur, dict) else {}
        node = cur
    return node


def type_of(sch: dict) -> str:
    if not isinstance(sch, dict):
        return "?"
    t = sch.get("type")
    if isinstance(t, list):
        t = "|".join(t)
    if not t:
        for k in ("anyOf", "oneOf", "allOf"):
            if k in sch:
                return k
        t = "object" if "properties" in sch else "?"
    if t == "array":
        return f"array[{type_of(deref(sch.get('items', {}), SPEC))}]"
    return t


def constraints(sch: dict) -> str:
    bits = []
    if sch.get("enum"):
        vals = sch["enum"]
        shown = ", ".join(f"`{v}`" for v in vals[:12])
        bits.append(f"enum: {shown}" + (f" (+{len(vals)-12} more)" if len(vals) > 12 else ""))
    for a, label in (("minimum", "min"), ("maximum", "max"), ("minLength", "minLen"),
                     ("maxLength", "maxLen"), ("format", "format"), ("default", "default"),
                     ("pattern", "pattern")):
        if sch.get(a) is not None:
            bits.append(f"{label} {sch[a]}")
    return "; ".join(bits)


def flatten(sch: dict, spec: dict, prefix="", depth=0, out=None) -> list:
    out = out if out is not None else []
    if depth > 3:
        return out
    sch = deref(sch, spec)
    props = sch.get("properties") or {}
    required = set(sch.get("required") or [])
    for name, p in props.items():
        p = deref(p, spec)
        path = f"{prefix}{name}"
        out.append({"name": path, "type": type_of(p), "req": name in required,
                    "desc": (p.get("description") or "").strip().replace("\n", " "),
                    "cons": constraints(p)})
        if p.get("type") == "object" or "properties" in p:
            flatten(p, spec, path + ".", depth + 1, out)
        elif p.get("type") == "array":
            it = deref(p.get("items", {}), spec)
            if "properties" in it:
                flatten(it, spec, path + "[].", depth + 1, out)
    return out


SEEN: dict = {}


def render_tag(tag: str, ops: list, spec: dict) -> list[str]:
    global SPEC
    SPEC = spec
    L = [f"# PriceLabs REST API: {tag}", "",
         "> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.",
         "> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).",
         "> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.", ""]
    for method, path, op in sorted(ops, key=lambda x: (x[1], x[0])):
        L.append(f"\n## `{method} {path}`\n")
        if op.get("summary"):
            L.append(f"{op['summary']}\n")
        d = (op.get("description") or "").strip()
        if d:
            L.append("\n".join("> " + x for x in d.splitlines()) + "\n")
        params = [deref(x, spec) for x in (op.get("parameters") or [])]
        if params:
            L.append("| param | in | req | type | notes |")
            L.append("|---|---|---|---|---|")
            for pa in params:
                sch = deref(pa.get("schema", {}), spec)
                note = "; ".join(x for x in [(pa.get("description") or "").strip().replace("\n", " "),
                                             constraints(sch)] if x)
                L.append(f"| `{pa.get('name')}` | {pa.get('in')} | {'Y' if pa.get('required') else ''} "
                         f"| {type_of(sch)} | {note[:300]} |")
            L.append("")
        rb = op.get("requestBody")
        if rb:
            rb = deref(rb, spec)
            for ct, media in (rb.get("content") or {}).items():
                fields = flatten(media.get("schema", {}), spec)
                if not fields:
                    continue
                rows = [f"| `{f['name']}` | {'Y' if f['req'] else ''} | {f['type']} "
                        f"| {'; '.join(x for x in [f['desc'], f['cons']] if x)[:300]} |" for f in fields]
                key = ("body", tuple(rows))
                if key in SEEN and len(rows) > 8:
                    L.append(f"**Body** (`{ct}`): identical to `{SEEN[key]}`.\n"); continue
                SEEN[key] = f"{method} {path}"
                L.append(f"**Body** (`{ct}`{', required' if rb.get('required') else ''}):\n")
                L.append("| field | req | type | notes |"); L.append("|---|---|---|---|")
                L += rows; L.append("")
        ok = (op.get("responses") or {}).get("200") or (op.get("responses") or {}).get("201")
        if ok:
            ok = deref(ok, spec)
            for ct, media in (ok.get("content") or {}).items():
                fields = flatten(media.get("schema", {}), spec)
                if not fields:
                    continue
                rows = [f"| `{f['name']}` | {f['type']} "
                        f"| {'; '.join(x for x in [f['desc'], f['cons']] if x)[:220]} |" for f in fields[:45]]
                key = ("resp", tuple(rows))
                if key in SEEN and len(rows) > 8:
                    L.append(f"**Response 200**: identical to `{SEEN[key]}`.\n"); continue
                SEEN[key] = f"{method} {path}"
                L.append("**Response 200** (top fields):\n")
                L.append("| field | type | notes |"); L.append("|---|---|---|")
                L += rows
                if len(fields) > 45:
                    L.append(f"| ... | | {len(fields)-45} more, see `docs/pricelabs/*.json` |")
                L.append("")
        errs = [c for c in (op.get("responses") or {}) if str(c).startswith(("4", "5"))]
        if errs:
            L.append(f"Errors: {', '.join('`'+str(e)+'`' for e in sorted(errs))}\n")
    return L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()
    if a.fetch:
        fetch()
    files = sorted(SPECS.glob("*.json"))
    if not files:
        raise SystemExit(f"no specs in {SPECS}; run with --fetch")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for stale in OUTDIR.glob("*.md"):
        stale.unlink()
    index, total = [], 0
    for f in files:
        spec = json.loads(f.read_text())
        info = spec.get("info", {})
        by_tag: dict[str, list] = {}
        for path, item in spec.get("paths", {}).items():
            for m, op in item.items():
                if m.lower() in VERBS:
                    by_tag.setdefault((op.get("tags") or ["untagged"])[0], []).append((m.upper(), path, op))
        index.append(f"\n## {info.get('title')} v{info.get('version')}  "
                     f"(base `{(spec.get('servers') or [{}])[0].get('url','')}`)\n")
        for tag, ops in sorted(by_tag.items()):
            slug = "".join(c if c.isalnum() else "-" for c in tag).strip("-").lower()
            (OUTDIR / f"{slug}.md").write_text("\n".join(render_tag(tag, ops, spec)) + "\n")
            total += len(ops)
            index.append(f"- **[`{tag}`]({slug}.md)** ({len(ops)} ops): "
                         + ", ".join(f"`{m} {p}`" for m, p, _ in sorted(ops, key=lambda x: x[1])))
    head = ["# PriceLabs REST API reference (index)", "",
            "> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds every file here",
            f"> from the published OpenAPI 3.1 specs. Last generated {dt.date.today().isoformat()}.",
            f"> **{total} operations.** Raw specs archived in `docs/pricelabs/`.", "",
            "Auth on every call: `X-API-Key` header **and** a browser-like `User-Agent`.",
            "A bare client gets a WAF 403 that reads like an auth failure.", "",
            "**Read `../pricelabs-gotchas.md` before writing any client.** The spec does not carry",
            "the measured traps (offset pagination, decaying override history, per-account payload",
            "shapes), and every one of them has already cost real money.", ""]
    (OUTDIR / "README.md").write_text("\n".join(head + index) + "\n")
    print(f"wrote {total} operations across {len(list(OUTDIR.glob('*.md')))} files in {OUTDIR}")
    for f in sorted(OUTDIR.glob("*.md")):
        print(f"   {f.stat().st_size:>7,}B  {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
