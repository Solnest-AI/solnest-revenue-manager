# PriceLabs MCP: all 47 tools, and which ones revenue management should use

Catalog verified live 2026-09-18 via `pricelabs_help`. REST equivalents and exact field
schemas: `pricelabs-api/`. Measured traps: `pricelabs-gotchas.md`.

**W** = write, needs OAuth write scope and an explicit human yes. Everything else is read-only.
**Step** = where it belongs in the runbook.
**(unused)** = no equivalent appears anywhere in the runbook or the reducers, measured 2026-09-18.

The runbook was written against the previous MCP server, whose tools carried a `pricelabs_`
prefix and different names (`pricelabs_list_listings`, `pricelabs_get_neighborhood_data`,
`pricelabs_set_overrides`, ...). Those map onto the tools below and are NOT marked unused.

## Identity and catalog

| Tool | W | Step | Use |
|---|---|---|---|
| `get_me` | | 0 | Which account the key is actually on. Run before anything that writes. |
| `get_listings` | | 0 | **The default lookup.** Returns `listing_id` + `pms_name` + `channel_listing_details` (the Airbnb/Vrbo/Booking ids). The Airbnb id here is the join key to any guest-facing source. |
| `get_listing_data` | | 4 | Detailed records: base/min/max, `push_enabled`, `occupancy_next_*`, `market_occupancy_next_*`, `recommended_base_price`. Never for search. |
| `get_groups` | | 0 | Resolve a real `group_id`. A listing's own `group_id` can point at a deleted group. **(unused)** |
| `get_group_listings` | | 0 | Listings in a group or subgroup. **(unused)** |
| `pricelabs_help` | | | The canonical tool catalog. |
| `get_knowledge` | | | Product questions against PriceLabs' knowledge base. Vendor answers are a lead, not proof. |
| `pricelabs_feedback` | W | | Only when the user literally writes `pricelabs_feedback: ...`. |

## Pricing: read

| Tool | W | Step | Use |
|---|---|---|---|
| `get_listing_prices` | | 4.0 | The forward curve. Carries `price`, `user_price`, **`uncustomized_price`** (pre-customization, the key to attributing the stack), `min_stay`, `booking_status`, `ADR`, STLY twins, `unbookable`, and `reason`. Use the reducer, never raw. |
| `get_listing_rate_plans` | | 4 | Rate plans on a listing. Empty on this portfolio. Named in the runbook as `pricelabs_get_rate_plans`. |
| `get_available_nudges` | | 4 | PriceLabs' own pending base/min suggestions, with `current_value`, `suggested_value`, `reason`, `expiration`. Vendor-validated and cheap. |

## Pricing: write

| Tool | W | Step | Use |
|---|---|---|---|
| `update_listing_data` | W | 8 | base / min / max / tags **and `push_enabled`**. Sync on/off lives here, and switching it on starts billing that listing. |
| `accept_nudge` | W | 8 | Apply one pending nudge. **The narrowest write in the whole API**: one listing, one field, vendor-generated value. Prefer it over a raw bound change when a matching nudge exists. |
| `refresh_listing_pricing` | W | 8 | Recompute the calendar after changes, optionally with the reason breakdown. **Hard limit 3 per listing per 24h, 10 per account per minute.** Batch every change before refreshing. **(unused)** |
| `map_listings` / `unmap_listings` | W | | Parent/child channel listings for one property. Unmapping a parent detaches the whole group. **(unused)** |

## Customizations: the six pricing rules

The layer that shapes the curve. Never read by the runbook before 2026-09-18.

| Tool | W | Step | Use |
|---|---|---|---|
| `get_customizations` | | 3.2 / 5 | Per listing, group or account. Pass `toggled_on=false` to see switched-off rules with their stored settings. **Always read the `effective` block**, not just the raw values. |
| `get_customization_schema` | | 8 | Field names, enums, ranges, what each type requires. Call for every key before any write. |
| `get_customization_profiles` | | 3.2 | Saved min-stay / pricing / check-in-out profiles and their ids. **Shared account objects: changing one changes every listing attached.** |
| `update_customizations` | W | 8 | Create or update rules at listing, group or account level. All-or-nothing per call. |

## Date-specific overrides (DSOs)

| Tool | W | Step | Use |
|---|---|---|---|
| `get_listing_date_overrides` | | 4 | Per-date price / min-stay rules. **Future dates only, and history decays.** Capture daily. |
| `update_listing_date_overrides` | W | 8 | Per-date price, min-stay, min/max bounds, check-in/out rules, reason. |
| `delete_listing_date_overrides` | W | 8 | Revert specific dates to standard pricing. |
| `get_group_date_overrides` | | 4 | Same, for a whole group. **(unused)** |
| `update_group_date_overrides` | W | 8 | Group-wide per-date rules. **Blast radius is every listing in the group.** **(unused)** |
| `delete_group_date_overrides` | W | 8 | **(unused)** |

## Market and comps

| Tool | W | Step | Use |
|---|---|---|---|
| `get_neighbourhood_data` | | 4a | The comp engine. Percentiles, occupancy, STLY, pickup, KPIs. Heavy; opt in via `include_*`. Needs `push_enabled` ON. |
| `get_listing_neighborhood_market` | | 4a | Lighter integration-style neighborhood + base-price snapshot. **(unused)** |
| `get_neighborhood_data_sources` | | 4a | **Which comp set a listing is priced against**, the alternatives, and the current default. Explains a custom comp set before its payload shape surprises you. **(unused)** |
| `set_neighborhood_data_source` | W | 8 | Reassign the comp set. Changes every market comparison downstream. **(unused)** |
| `get_md_report_compsets` | | 4a | Market Dashboard compsets, to inspect before assigning. **(unused)** |
| `market_research` | | 4a | Natural-language market questions: overviews, geography comparisons, zipcode markets, revenue estimates, amenities. **(unused)** |
| `get_str_index` | | 4a | STR market index by country/state/month: occupancy, RevPAR, YoY. **(unused)** |

## Diagnostics: what PriceLabs already thinks is wrong

The whole group is unused, and it overlaps heavily with analysis the runbook does by hand.

| Tool | W | Step | Use |
|---|---|---|---|
| `get_actions` | | 4 | **Active issues PriceLabs raises per listing**: missing base price / location / bedrooms, occupancy adjustments off, min-stay or last-minute off market, too many blocked or unbookable dates, price recommendations. The cheapest "what needs attention" call in the API. **(unused)** |
| `get_listing_health_and_recommendations` | | 4 | Pulse, health status, recommendation section. Primary per-listing diagnostic. **(unused)** |
| `diagnose_no_bookings` | | 4 | Deep setup diagnosis for a listing with no recent bookings and low forward occupancy. Directly relevant to a floor-pinned, non-converting listing. **(unused)** |
| `get_listing_performance_metrics` | | 4 | Raw ADR, revenue, occupancy, RevPAR. |
| `get_account_review_report` | | 7 | Account-level review over a date range, optionally with listing-level actions. **(unused)** |

## Listing Optimizer (Airbnb only)

| Tool | W | Step | Use |
|---|---|---|---|
| `get_listing_optimizer_summary` | | 4 | Score and status for every Airbnb listing. Call first. **(unused)** |
| `get_listing_optimizer_report` | | 4 | Category letter grades, what drove each score, improvement tips, last-run grades. **(unused)** |
| `get_listing_optimizer_ranking` | | 4 | **Rank and page position, price by guest-count and LOS segment, neighborhood size, 90-day rank history.** Overlaps RankBreeze. **(unused)** |

## Reservations and reporting

| Tool | W | Step | Use |
|---|---|---|---|
| `get_pms_reservations` | | 4 | Reservations filtered by stay date **and/or booking-made date**, with `include_hidden`. The booked-date filter is what lead-time and pace analysis needs. |
| `get_bookings_report` | | 4 | Reservation table across all PMSs, filterable and paginated. Better than per-listing pulls for portfolio revenue. **(unused)** |
| `get_report_builder_templates` | | 7.5 | Saved and canned report templates. **(unused)** |
| `get_report_builder_data` | | 7.5 | Start a template run; returns a `request_id`. **(unused)** |
| `poll_report_builder_data` | | 7.5 | Poll until `report_data` appears. Could replace the hand-built workbook. **(unused)** |
| `get_user_logs` | | 3 | **Activity log: pricing changes, sync toggles, DSOs, by team member and date.** This is the audit trail PriceLabs already keeps, and it answers "who changed this and when" without Supabase. **(unused)** |

## What this portfolio is not using

Read-only and free to add: `get_actions`, `get_listing_health_and_recommendations`,
`diagnose_no_bookings`, `get_available_nudges`, `get_user_logs`,
`get_neighborhood_data_sources`, `get_listing_optimizer_*`, `get_bookings_report`,
`market_research`, `get_str_index`, `get_group*`.

The two with the most immediate value: **`get_actions`** (PriceLabs' own per-listing issue list,
which the runbook currently reconstructs by hand) and **`get_user_logs`** (a change history that
makes the PL changes check a read rather than a diff of saved snapshots).

The safest write is **`accept_nudge`**: one listing, one field, a value PriceLabs generated.
