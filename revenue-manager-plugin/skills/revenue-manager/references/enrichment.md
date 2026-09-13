# Optional enrichment reference (detect-and-use; never a critical path)

> Reference for the revenue-manager skill. Loaded on demand from SKILL.md; not part of the runbook that loads on every run.

### RankBreeze (visibility/ranking spoke of the flywheel)
- Tools: `mcp__rankbreeze__list_properties`, `get_rankings`, `get_calendar_rankings`, `get_competitor_rates`, `get_metrics`, `analyze_property`, `health_check`.
- **Multi-property mapping:** all the data tools are single-listing and need a `listing_id`. Call `list_properties` FIRST to map each PMS property to its RankBreeze `listing_id` (Airbnb-listing-scoped, NOT the PMS property UUID), then loop the per-listing tools. No match for a property → manual ranking check for that one property; never block.
- Use for ranking position, page-view/visibility signal, and the "check ranking FIRST" troubleshooting step. If absent → ranking is a flagged manual check.

### Turno / Breezeway (ops signals)
- **Turno:** `turno_list_projects` / `turno_list_bookings` for cleaning/turnover cost. Flag turnover cost as a revenue leak when too many 1-night stays. (Call `turno_check_connection` first.)
- **Breezeway:** task costs. Rising maintenance explains margin drop even with strong occupancy.
- Append as an "Operational signals" section at the end of the report.

### AirROI (named-competitor comps — native local currency) — `mcp__airroi__*`
- **Pull through `fetch/reduce_comps.py` (Step 4.8), not the MCP tool directly.** The MCP path costs ~103k tokens per call and cannot assert currency or exclude the subject. The MCP is still what Step 0 detects; the reducer hits the same API.
- MCP tools: `get_comparables` (≤25 named comps w/ TTM revenue/ADR/occ/ratings), `get_estimate` (revenue projection + percentiles + comps), `get_listing` (full listing detail), `get_listing_metrics` (monthly occ/ADR/rev/RevPAR), `health_check`. If `mcp__airroi__*` isn't connected, **skip silently** — it only enriches PriceLabs, never required. (Setup: it's a bundled MCP at `mcp-servers/airroi/` — build the venv, add a free AirROI key, register, restart Claude Code.)
- Use for the **qualitative** named-competitor comp layer ON TOP of PriceLabs' aggregate neighborhood data.
- **Native currency:** call with `currency=native` so figures return in each market's local currency (normally matching your PMS/PriceLabs). Verify the echoed `currency` field; on a genuine mismatch convert (named live FX + timestamp, gate 2.4) or flag-and-exclude — never silently mix. Never contradict PriceLabs silently — if they disagree, surface and explain.
