# Changelog

## 1.1.1

- **`setup-keys.sh` / `setup-keys.ps1` no longer clobber each connector's `.env`.** They used to
  `cp` the root `.env` straight over `mcp-servers/<tool>/.env`, silently deleting any
  per-connector setting with no line in the root template. The clearest casualty was
  `TURNO_ENV`: anyone who followed SETUP.md and switched to `production` got reverted to
  `sandbox` and then read an empty sandbox account believing it was live data. Both scripts now
  merge — they write only the keys that connector's own `.env.example` declares, only when the
  root value is non-blank, and never remove a line. Side effect: the PriceLabs key no longer
  lands in Turno's `.env`, and vice versa.
- **`TURNO_ENV` added to `.env.template`**, blank by default so it keeps whatever the connector
  is already set to.
- **The one-step key path is documented.** `setup-keys.sh`, `KEYS.md` and `.env.template` existed
  but no markdown file in the repo mentioned them, so everyone was sent down the slower
  per-connector route. README's "Installing a pre-built connector" now leads with the one-step
  option, and SETUP.md tells Claude to check before `cp .env.example .env` so it does not
  overwrite a `.env` the operator already filled.
- **`KEYS.md` no longer marks optional keys as required.** `TURNO_API_TOKEN`, `TURNO_PARTNER_ID`
  and `AIRROI_API_KEY` were listed as Required=Yes, contradicting the README and the plugin
  manifest, which both call Turno, RankBreeze and AirROI optional enrichment. Turno is
  partner-gated, so that table was telling strangers they needed an account they cannot get.
- **`KEYS.md` and `.env.template` used `EXA_API_KEY` as the worked example**, a key this product
  never reads. Replaced with `PRICELABS_API_KEY`.
- **The Excel export's dependency is stated.** README Prerequisites now says the multi-tab
  workbook needs `openpyxl`, that the skill installs it into its own local venv on first use,
  and that it degrades to a folder of CSVs otherwise. Verified both paths against
  `report/build_workbook.py`.

## 1.1.0 — plugin 4.1.0

- **Fresh-Supabase fix.** The skill now bootstraps its own schema (Step 3.0). It checks for the
  four audit tables and applies migrations 001 + 002 itself when they're missing, so a brand-new,
  completely empty Supabase project works on the first run. Previously the pre-flight ran
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, which still errors with
  `relation "pricing_decisions" does not exist` when the table itself was never created.
- **Graceful degrade instead of a crash.** A read-only Supabase MCP, an `anon` key, or the wrong
  project no longer aborts the run. The skill warns once, disables audit logging, and delivers the
  full pricing analysis anyway.
- **Empty history is no longer treated as a failure.** A first run reports "no history yet, this
  run becomes your baseline" and continues instead of stopping.
- **Broader Supabase detection.** Any Supabase MCP flavour is recognised (`mcp__supabase__*`, a
  named server like `mcp__supabase-<name>__*`, or the connector flavour). A project-scoped server
  with no `list_projects` is correctly treated as working.
- **README:** real click-by-click Supabase account walkthrough, an explicit warning not to register
  the MCP with `--read-only`, `service_role` vs `anon` called out, and the manual SQL-Editor step
  removed as a requirement.

## 1.0.0

- First public release.
