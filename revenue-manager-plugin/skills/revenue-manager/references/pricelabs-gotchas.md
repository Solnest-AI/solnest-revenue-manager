# PriceLabs: the traps the spec does not carry

Every entry here was measured against the live API, not inferred from docs. Each one has
already produced a wrong number, a wrong recommendation, or a wrong bill. Read this before
writing any client. Endpoint field detail is in `pricelabs-api/`; tool list in `pricelabs-mcp.md`.

## Auth, limits, cost

| Fact | Value |
|---|---|
| Auth header | `X-API-Key` on every REST call |
| User-Agent | **Required.** A bare client gets a WAF `403` that reads like an auth failure. Send a browser-like UA. |
| Rate limit | **60 requests/minute, 1,000/hour** per key. Exceeding returns `429`. |
| `POST /v1/refresh_listing` | Much tighter: **3 calls per listing per 24h, 10 per account per minute.** Batch every change to a listing before refreshing it. |
| Client timeout | Set **300 s**. Neighborhood payloads alone run 0.35-0.55 MB and ~4 s. |
| Billing | **$1 per listing per month** for each listing that syncs prices that month. An account-level write that switches sync on for idle listings has a bill attached. |

## Reading data

- **`GET /v1/reservation_data` pages on `offset`, not `page`.** A `page=N` parameter is silently
  ignored and `next_page` is a bare boolean, so a page-incrementing loop refetches page 1 forever.
  Measured: 2,000 rows containing 100 distinct reservation ids, inflating every monthly total up
  to 20x. De-duplicate on `reservation_id` and stop on an empty or all-seen page. At an exact page
  boundary `next_page` is still `true` and the next page is empty.
- **`GET /v1/reservation_data` ignores `listing_id` and returns the whole account.** A single
  listing's pull came back carrying another property's rows, mixing CAD and USD silently.
  **Filter client-side, always**, and currency-gate before summing.
- **PriceLabs silently ignores past date ranges.** It returns `200` with a shorter window rather
  than an error. Always assert the window you got back is the window you asked for.
- **`booking_status` is `"Booked"` OR `"Booked (Check-In)"`.** Matching only `== "Booked"`
  undercounted 21 of 35 booked nights on one listing, a 40% miss. Available nights carry an
  **empty string**, not `"Available"`.
- **`-1` and `-2` are missing-value sentinels** (`-2` = no same-time-last-year data). Never let
  them reach arithmetic, and never compare them as real min-stay values.
- **An empty `booking_status_STLY` is ambiguous**: either "was available last year" or "the
  listing did not exist yet". Resolve per month. Zero populated STLY values in a month means no
  history, so report blank, never `0%`.
- **Direct-channel connections carry almost no booking status.** Channel-manager connections
  (smartbnb, OwnerRez, iGMS, Guesty, Hostaway) match listing-level occupancy within a few points;
  direct Airbnb/Vrbo/Booking.com connections run 16 to 77 points low. Use the listing-level
  `occupancy_next_*` fields, not calendar-derived occupancy, on those.
- **Numbers come back as strings.** `recommended_base_price` can be the string `"Unavailable"`;
  occupancy fields arrive as `"73 %"`. Coerce to a number or NULL, never leave a string.
- **`unbookable` is a separate axis from `booking_status`** and is unreliable on its own.

## Neighborhood data

- **`GET /v1/neighborhood_data` requires `push_enabled` ON.** Otherwise `400 "Listing sync is not
  toggled ON in PriceLabs"`. That is a configuration answer, not an outage.
- **A custom comp set returns a different payload shape.** A listing priced against a named set
  gets ONE category (the set's name, no bedroom categories), different series labels
  (`N_bookings` not `N_Bookings`, `Future Bookings` not `Future Booked Days`, no
  `Total_Available_Listings`), a nine-column base-price table with the percentiles at positions
  5-8, no monthly percentiles block, and a daily series that **starts six months in the past**.
  Resolve every label by name, window the daily rows on the calendar, and never treat "the first
  N rows" as forward-looking.
- **Cache neighborhood by rounded location, but know the resolution.** Rounding lat/lng to 2 dp
  makes listings ~1 km apart share an entry. Two properties 400 m apart at -119.91 and -119.90
  are *different* cache keys, not a shared one.

## Overrides (DSOs)

- **Override history DECAYS. The endpoint returns FUTURE dates only.** An override covering a date
  disappears from the API once that date passes. Measured across 269 listings: **846 override-dates
  existed only because they had been saved twelve days earlier.** Anyone reconstructing how an
  operator prices must **capture daily**; weekly leaves holes and the record is otherwise a
  sliding zero-day window.
- **`404 Listing not found` on the overrides endpoint means removed from the account**, not an
  auth problem.
- **The customization stack is invisible to the overrides API.** Per-date overrides and the six
  customizations are different layers. A change-detector watching only overrides sees none of the
  rules that shape the curve.

## Customizations (the six pricing rules)

- **Switching a toggle OFF is not "no adjustment."** The algorithm's own market-driven behaviour
  takes over. Measured live: a listing with last-minute OFF was running a **40% same-day discount**;
  another with far-out OFF was running a **+20% premium from 60 days**. To actually suppress a
  rule, send its type `none` (or `no demand factor`) with the toggle **ON**.
- **Always read the `effective` block**, which is the dashboard's own rendering of what a setting
  currently does. The raw values alone cannot tell you which level a value came from, what a
  market-driven type currently works out to, or whether a number is a discount or a premium.
- **Day-of-week: days omitted from a write default to 0.** They do NOT keep their previous value.
  Writing only Fri/Sat wipes a Mon-Thu adjustment. Always send all seven days.
- **The value is SIGNED and a wrong sign is accepted, not rejected**, because a premium is a
  legitimate setting. It becomes a live guest-facing price change that returns success. Check the
  `effective` echo after every write: "15% discount" and "15% premium" are both valid responses to
  the same number.
- **An invalid value (out of range, wrong enum) rejects the WHOLE request.** Nothing in
  the call applies, not even the keys you got right.
- **A valid-but-wrong value is the opposite, more dangerous failure: the request
  SUCCEEDS.** A key that passes range/type checks but carries a stale or unintended value
  (for example, an old day carried forward unchanged through a full-object merge) applies
  right alongside the keys you actually meant to change. Passing validation is not the
  same as being correct.
- **Toggling off RESETS the stored config** for `last_minute_prices` (to type `linear`, value 0)
  and `far_out_premium` (to value 0 / start 999). Re-enabling needs the full configuration again.
  Seasonality and day-of-week keep their stored values.
- **A `custom_seasonal_profile` write REPLACES the entire stored configuration.** Always send the
  full season set, never a delta.
- **The enums are inconsistent between rules.** Last-minute uses `fixed`; far-out uses `fix` and
  has no `linear_gradual`. Last-minute and far-out use `none`; demand factor uses the
  space-separated `no demand factor`. A `fix` far-out is stored as `linear` with step 1 and reads
  back that way.
- **Account level is more restricted than listing level**: `price_type` must be `percentage`,
  profile ids cannot be set, `inherit_*` flags are rejected, and `fixed` last-minute is
  listing-only.
- **Feature-gated fields fail the whole write** with `ERR-FEATURE-NOT-ENABLED`: hotel compset and
  weights, non-repeating seasons, `inherit_*`, pricing profiles.
- **Min-stay profiles are shared account-level objects**, referenced by id from seasons. Changing
  a profile changes every listing attached to it. A profile change is a portfolio change.

## Decomposing a price

- **`uncustomized_price` is the price before the customization stack.** Verified: a listing with
  every customization off returns `price / uncustomized_price == 1.000` on all seven weekdays.
- **The ratio does NOT decompose into individual rules.** Several rules overlap on the same date,
  far-out premium covers most of a 365-day window, and open nights skew far-out because near-term
  weekends are already booked. Use the total effect as fact; use the rule list as context. Never
  claim a specific rule contributed a specific percentage.

## Markup and comparisons

- **PriceLabs does not know your PMS's per-channel markup.** It is applied downstream, after the
  push. PriceLabs' own Markup/Markdown control is a chart-only visualisation you type in by hand.
- **`PMS price / PriceLabs price` measures SYNC FIDELITY, not markup.** It returns 1.0 whenever the
  push works. Neither number is what a guest sees.
- **Measure the markup from outside.** A guest-facing scrape (RankBreeze) divided by the PriceLabs
  net price over the same available dates is a real measurement. Measured +16.8% against a stated
  +18.34% on 44 shared dates. Use the **mean over shared dates**, never the median of per-date
  ratios: the scrape behaves like a stay-level rate and per-date ratios ranged 1.063 to 1.390 on
  the same listing. Require a minimum shared-date count and treat anything outside 0.80-2.50 as a
  data problem, not a pricing strategy.
- **Scraped-source currency labels can be wrong.** One CAD listing was labelled `USD`. FX-converting
  on that label inverts the answer.

## Cross-source discipline

- **Both sides of a reconciliation must come from one pull.** Serving a cached PMS calendar against
  a fresh PriceLabs pull manufactures drift: 0 drift dates at pull time became 5 three hours later
  on the same listing, with ratios up to 1.31 that were nothing but the stale copy.
- **The schema drifts.** Between 2026-08-25 and 2026-09-03, `/v1/listings` renamed `city` to
  `city_name`, `lat`/`lon` to `latitude`/`longitude`, `push` to `push_enabled`, and added ~50
  fields. An ETL reading the old names silently bucketed every listing as market "unknown".
  Nine days. **Key-check every pull** and regenerate `pricelabs-api/` with
  `python3 tools/pricelabs_spec_report.py --fetch`.

## `get_actions` and the two sign conventions (measured 2026-09-18)

`GET /v1/actions` returns PriceLabs' own issue list per listing. On the probe listing:

```
action_type: last_minute_conservative_vs_market
current:     { discount_pct: -12.0, days_from_date: 7 }
recommended: { discount_pct:  40.0, days_from_date: 10 }
```

The listing's stored rule is `last_min_factor_value: -12.0`, so **`current.discount_pct` is the
stored SIGNED value** (negative = discount) echoed verbatim. **`recommended.discount_pct` is a
positive magnitude**: the action type means "you discount less than the market", so 40 is a 40%
discount, not a 40% premium.

**The two fields in the same object do not share a convention.** Copying
`recommended.discount_pct` into `last_min_factor_value` writes **+40, a 40% premium**, on a live
guest-facing calendar, and the API returns success because a premium is a legitimate setting.
Negate it, and re-read the `effective` block to confirm the direction before trusting any write.

This is inferred from the stored value matching `current` exactly plus the meaning of the action
type. It is **not confirmed by a write.** Confirm it with PriceLabs, or with one controlled write
on a listing that is not taking bookings, before any automated apply.

## Reading a rule that is switched off

`GET /v1/customizations/listing` **omits every toggled-off rule by default.** On the probe listing the
default call returns 4 rules and `toggled_on=false` returns 6. The two hidden ones were
`seasonality` and `custom_seasonal_profile`, and the seasonal profile was **not empty**: it held
two stored seasons, at -5% and +5%, waiting for someone to flip the toggle.

A dormant config with real values in it is invisible to the default call. Always pass
`toggled_on=false`.
