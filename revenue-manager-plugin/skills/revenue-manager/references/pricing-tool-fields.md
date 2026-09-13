# Pricing-tool field reference

> Reference for the revenue-manager skill. Loaded on demand from SKILL.md; not part of the runbook that loads on every run.

### PriceLabs (primary — the comp engine + the recommendation source)
- Base URL: `https://api.pricelabs.co` · Auth: `X-API-Key`
- PMS name mapping for Hospitable: `smartbnb`
- Rate limits: 60/min, 1,000/hr. Timeout: 300s for neighborhood_data.

Key structures:
```python
# Neighborhood = the comp engine (~85 comps, percentiles by bedroom, native currency)
# Pull it through fetch/reduce_neighborhood.py (Step 4a), never via the raw MCP tool.
# Raw structure, for reference only:
data['data']['Summary Table Base Price']['Category']   # Comp by bedroom count
data['data']['Future Occ/New/Canc']['Category']        # Market occ + STLY + 7-day pickup (10 series, 540 days)
data['data']['Future Percentile Prices']['Category']    # 25/50/75/90 + median booked + N (6 series, 360 days)

# Per-date pricing (forward ASK curve = what PriceLabs pushes to the PMS)
listing['data']  # Array of date objects
#   date, price (ASK / recommended), uncustomized_price, min_stay, booking_status, ADR (CLEARED)
#   reason.listing_info: nhood_occ, minimum_price, maximum_price, base_price
#   reason.market_factors: seasonality, demand_factor
#   user_price ("user price (from PMS)"): freshness varies by listing — MEASURE it against the
#     live PMS calendar per property (Step 5); don't assume it's current. PMS calendar is ground truth.

# Reservations (CLEARED-rate inputs)
# listing_id, listing_name, check_in, check_out, booking_status,
# rental_revenue, no_of_days, booking_channel, guestName
```
Tools: `pricelabs_list_listings`, `pricelabs_get_listing`, `pricelabs_get_listing_prices`, `pricelabs_get_neighborhood_data`, `pricelabs_list_reservations`, `pricelabs_list_overrides`, `pricelabs_set_overrides`, `pricelabs_delete_overrides`, `pricelabs_update_listings`, `pricelabs_get_rate_plans`.

### Wheelhouse (optional / pluggable)
- Base URL: `https://api.usewheelhouse.com/ss_api/v1/` · Auth: `X-User-API-Key`
- Uses "custom rates" instead of "DSOs". Demand Signal endpoint = richer market data (separate `IntegrationApiKey`).

### Beyond (optional / pluggable — self-serve Partners API)
- A Beyond MCP is built from the **Partners API** (`developers.beyondpricing.com`, JSON:API, self-serve **Personal Access Token** `bpat_…`) — see `build-pricing-ops-mcp.md`. It exposes listings, the price + availability calendar, compsets, Beyond's recommendations, and per-listing customizations (base/min/max price, min/max stay, fees, time-based adjustments) — writes behind a confirm gate.
- Often the PMS calendar already contains Beyond's pushed prices, so you can also read from the PMS side.
