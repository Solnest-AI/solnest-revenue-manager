# Step 7.5 — Offer the spreadsheet (a multi-tab workbook deliverable)

> Reference for the revenue-manager skill. Loaded on demand from SKILL.md; not part of the runbook that loads on every run.

After presenting recommendations, **offer** a spreadsheet — don't auto-generate it:

> "Want a spreadsheet of this? Summary tab + one tab per property, full breakdown."

Only if they say yes, build it. This is **pure output** — it reads nothing new, pushes nothing, and writes nothing to Supabase. It reflects the current state: recommendations are marked `proposed`, or `applied` if the operator already approved and you executed them in Step 8.

**1. Assemble the data as JSON.** You already have everything from Steps 4–7. Build one JSON object matching the shape documented at the top of `report/build_workbook.py` (use `report/sample_data.json` as the working template): a `meta` block, a `portfolio_summary` roll-up, and a `properties[]` array where each property carries pricing (current vs recommended base/min/max), comps, ask-vs-cleared, KPIs, red flags, the recommendations table, any DSO/min-stay recs, and the safety-layer footer. Write it to a temp file **in the OS temp dir** (e.g. `/tmp/rm_report.json`), never inside the bundle.

**2. Ensure openpyxl (one-time, local, no system pollution).** The `report/` folder sits next to this SKILL.md. Create a local venv there once and install openpyxl:
```bash
cd <plugin>/skills/revenue-manager/report
python3 -m venv .report-venv 2>/dev/null
.report-venv/bin/python -m pip install -q openpyxl 2>/dev/null
```
`.report-venv/` is gitignored. If the venv or install fails, **don't stop** — the script auto-degrades to a folder of CSVs (one summary + one per property) so the operator still gets every number.

**3. Generate.** Prefer the venv python; fall back to system `python3` (which triggers the CSV path):
```bash
.report-venv/bin/python build_workbook.py /tmp/rm_report.json    # or:  python3 build_workbook.py /tmp/rm_report.json
```
With no output path the workbook lands on the operator's Desktop (or the current folder) as `Revenue-Report-<YYYY-MM-DD>.xlsx`.

**4. Report the path.** The script prints exactly one result line — `WORKBOOK_WRITTEN: <path>` (real xlsx) or `CSV_FALLBACK_WRITTEN: <dir>/` (openpyxl unavailable). Tell the operator the exact path and which format they got. If it was the CSV fallback, mention they can install openpyxl to get the single multi-tab workbook next time.
