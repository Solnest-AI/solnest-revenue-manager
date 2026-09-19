# What the revenue manager uses, and what it is leaving on the table

Measured 2026-09-18 against the live catalog (47 MCP tools) and the published OpenAPI 3.1 spec
(41 Customer API operations + 2 Revenue Estimator). Regenerate the endpoint detail with
`python3 tools/pricelabs_spec_report.py --fetch`.

## Today

The reducers reach **6 of 41** Customer API operations:

| Endpoint | Reducer |
|---|---|
| `GET /v1/listings` | catalog, bounds, occupancy |
| `POST /v1/listing_prices` | `reduce_prices.py` |
| `GET /v1/listing_metrics` | `reduce_prices.py` (metrics line) |
| `GET /v1/neighborhood_data` | `reduce_neighborhood.py` |
| `GET /v1/reservation_data` | `reduce_reservations.py` |
| `GET /v1/listings/{id}/overrides` | `reduce_overrides.py` |

Under the previous server's names the runbook also refers to listing reads, listing updates,
override writes and rate plans. Everything it knows about sits in those six areas.

## The gap, ordered by what it would change

### 1. PriceLabs already lists the problems, and we rebuild them by hand

- **`get_actions`** returns the issues PriceLabs raises per listing: missing base price, location
  or bedroom count, occupancy-based adjustments off, min-stay or last-minute off market, too many
  blocked or unbookable dates, and price recommendations. One call, whole account.
- **`get_listing_health_and_recommendations`** is the per-listing Pulse and recommendation set.
- **`diagnose_no_bookings`** is a deep setup diagnosis for a listing with no recent bookings and
  weak forward occupancy. That is the exact shape of a floor-pinned non-converting listing.

Step 4 currently derives red flags from raw data. These three give the vendor's own answer first,
and disagreeing with it is more informative than not knowing it.

### 2. The pricing rules, which shape every number we read

`get_customizations`, `get_customization_schema`, `get_customization_profiles`. Six rules per
listing plus shared min-stay profiles. Without them the skill reads a curve and cannot see the
rules that produced it. Measured consequence: seven of nine floor-pinned Sunburst dates fall on
the two weekdays carrying a -10% day-of-week rule, and the eval argued about the min price
instead. Details in `pricelabs-gotchas.md` under Customizations.

### 3. A change history we were about to rebuild ourselves

**`get_user_logs`**: pricing changes, sync toggles and DSOs, filterable by team member, listing,
group and date. PriceLabs already keeps the audit trail. The override endpoint's decay problem
(846 dates lost in 12 days) is about *override state*; the log is about *events*, and it does not
decay the same way. Check it before building snapshot diffing.

### 4. The safest write in the API

**`get_available_nudges`** and **`accept_nudge`**: PriceLabs' own pending base/min suggestions,
each with a current value, a suggested value, a reason and an expiry. One listing, one field, a
vendor-generated number. When a nudge exists that matches our recommendation, accepting it is
strictly safer than composing a raw bound change. Zero pending on this account on 2026-09-18, so
it supplements the write path rather than replacing it.

### 5. Comp-set provenance

**`get_neighborhood_data_sources`** says which comp set a listing is priced against and what the
alternatives are. That is the missing context behind the custom comp set whose payload shape
crashed the neighborhood reducer. Read it before parsing neighborhood data, not after.
**`set_neighborhood_data_source`** changes it, and changes every market comparison downstream.

### 6. Reporting we hand-build

`get_bookings_report` (portfolio reservations, filterable and paginated, instead of per-listing
pulls) and the `report_builder` trio (templates, generate, poll). Step 7.5 builds a workbook by
hand today.

### 7. Ranking and visibility, already paid for

`get_listing_optimizer_summary` / `_report` / `_ranking`. Rank and page position, price by
guest-count and length-of-stay segment, neighborhood size, 90-day rank history. Overlaps
RankBreeze; worth comparing before paying attention to either.

### 8. Scope and market tools not wired

`get_groups`, `get_group_listings`, and the group-level override and customization endpoints:
these matter the moment a client has more listings than a person wants to touch one at a time.
`market_research`, `get_str_index`, `get_listing_neighborhood_market`, `get_md_report_compsets`
for market work. `map_listings` / `unmap_listings` for multi-channel properties.
`refresh_listing_pricing` to force a recompute after a batch of changes, remembering the 3 per
listing per 24 hours limit.

## Rule for adding any of these

Every one above is read-only except `accept_nudge`, `set_neighborhood_data_source`,
`refresh_listing_pricing`, the group override writes and `map`/`unmap`. Reads can be added to
Step 4 freely, subject to the token budget and the 60/minute limit. Writes go through the Step 8
approval gate, and a group-level or profile-level write is a **portfolio** change: name every
listing it touches before asking for approval.
