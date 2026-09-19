# Changelog

## 4.2.0-rc9 (unreleased)

- Reference pointers now fire from inside Step 4 and Step 8 instead of only from the appendix.
  The gotchas file told the reader to consult it "at Step 4 and again at Step 8", but that
  instruction lived after Step 9, so a run following the steps in order never saw it.
- `references/pricelabs-coverage.md` rewritten as the routing table for all 43 published
  operations: what each answers, which step owns it, which `pricelabs-api/` file documents it,
  and what a live probe returned.
- New `tools/pricelabs_endpoint_probe.py`: probes every published operation against one listing,
  writes raw bodies to the cache, prints a status table. State-changing operations are
  enumerated and never fired; one can be forced with `--only <key> --i-know-this-writes`.
- Gotchas: `get_actions` uses two different sign conventions in the same object
  (`current.discount_pct` signed, `recommended.discount_pct` a magnitude), so copying the
  recommendation into a customization write inverts a discount into a premium.
- Gotchas: `GET /v1/customizations/listing` hides every toggled-off rule unless
  `toggled_on=false` is passed, including dormant profiles holding real values.
- Design spec for the customization layer at
  `docs/superpowers/specs/2026-09-18-pricelabs-customization-layer-design.md`. Not implemented.

## 4.2.0-rc7

- **Complete PriceLabs surface, documented and checked in.** Researched the published OpenAPI 3.1
  specs, all 89 doc pages and the live MCP catalog, then measured what the skill actually uses.
  The reducers reach **6 of 41** Customer API operations; the live MCP exposes **47 tools**.
  New references:
  - `references/pricelabs-api/` (GENERATED, 18 files, 43 operations) with every parameter,
    request body, response field, enum and range. Built by `tools/pricelabs_spec_report.py`,
    which re-fetches the specs and rewrites the directory, so the reference cannot rot silently
    the way a hand-written one does. Raw specs archived in `docs/pricelabs/`.
  - `references/pricelabs-gotchas.md`: every measured trap in one place. Auth and the WAF 403,
    60/min and 1,000/hour, the 3-per-listing-per-24h refresh limit, $1/listing/month billing,
    offset pagination, `reservation_data` returning the whole account, decaying override history,
    custom comp-set payload shape, the sentinels, "off is not off" on customizations, and the
    signed write that succeeds while doing the opposite of what was meant.
  - `references/pricelabs-mcp.md`: all 47 MCP tools mapped to runbook steps, read vs write.
  - `references/pricelabs-coverage.md`: the gap, ordered by what it would change. Biggest items
    are `get_actions`, `get_listing_health_and_recommendations` and `diagnose_no_bookings`
    (PriceLabs already computes diagnostics Step 4 rebuilds by hand), the customization layer,
    and `get_user_logs` (an existing change history).
  The whole corpus is read-on-demand: SKILL.md grows 571 tokens for the pointers, nothing else
  loads unless a step asks for it.

## 4.2.0-rc6 (unreleased)

- **`reduce_reservations.py` paginated wrong.** PriceLabs pages `reservation_data` on `offset`;
  `next_page` is a bare boolean and a `page=N` parameter is silently ignored, so the loop fetched
  page 1 up to twenty times. For any listing with more than 100 reservations in the window every
  monthly total (nights, revenue, ADR) came out multiplied. The raw cache carried the same
  duplicates, so raw-vs-reduced agreement proved nothing; a row-count check in the decision eval
  caught it. Now offset-paginated, de-duplicated on `reservation_id`, stops on an empty or
  all-seen page, and exits 2 rather than truncating past the page cap. Two regression tests.
- **`reduce_neighborhood.py` did not understand custom comp sets.** A listing priced against a
  named PriceLabs comp set returns one category (the set's name), different series labels
  (`N_bookings`, `Future Bookings`), a nine-column base-price table and a daily series that starts
  six months in the past. The reducer crashed with a traceback (exit 1, neither "printed" nor
  "cannot produce"). Now: `--category` override, auto-select when the market has exactly one
  category (noted in the header), case-insensitive label resolution with `missing_series=` in
  the header for anything the payload does not carry (never filled from another series), base
  percentiles read by label, the daily block windowed from today (`window_start=`), an optional
  monthly block, and any unexpected exception exits 2. The fact harness gets the same logic
  (`--start`).
- **`eval/`: decision-level eval.** Full raw payloads vs reducer output, same model, same
  runbook, same snapshot, mechanical grading with noise attribution. See `eval/README.md`.
  First run (8 properties, 24 reduced reps + 16 full reps, `claude-opus-5`, effort xhigh):
  2 of 8 properties carried an attributable HARD divergence and both were judgment calls on
  identical facts, none from a dropped field; the reduced side's reported facts matched
  ground truth 89% of the time against 75% for the raw payloads. Three reduced-side blind
  spots it did expose (pacing, host blocks, orphan gaps) are fixed below.
- **`reconcile_pms.py` compared a cached PMS calendar against fresh PriceLabs prices**, so
  any PriceLabs refresh in between read as "drift" (0 drift dates at pull time, 5 three hours
  later on one listing). The cached pair is now used together; the calendar header carries
  `compared_at=`. The block also gains `### blocked` (runs of host/user blocks with source
  and note) and `### gaps` (1-2 open nights boxed in by non-available nights).
- **`reduce_prices.py` Tier A prints a `[pacing]` line**: occupancy now vs same time last
  year for the next 30/60/90 nights, blocked nights out of the denominator, `n/a` below 20%
  STLY coverage.
- **`reduce_overrides.py`** (new): PriceLabs per-date overrides collapsed into runs of
  consecutive dates with the same price, type, min-stay and reason (281 rows to 30 runs,
  21x). Past dates dropped; an empty list is a valid answer. Fact class with a per-run digest.
- **Runbook: the channel markup layer.** Most PMSs add a per-OTA markup after the calendar,
  so the pricing tool's price and the calendar are NET and every market number is guest-facing.
  New Step 3.2 discovers the markup by API where the PMS exposes it (Hospitable does not,
  verified), otherwise asks once at setup and stores it per channel. Step 5 names three price
  layers (NET / ASK per channel / CLEARED); market comparisons use ASK. The old "measure the
  markup as PMS ÷ PriceLabs" rule measured sync fidelity (1.0 everywhere) and biased every
  recommendation toward "below market, raise". `references/pms-fields.md` gains a per-PMS
  markup row; `references/audit-write.md` the `channel_markup_pct` settings shape.

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
