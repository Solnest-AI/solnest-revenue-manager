# PriceLabs REST API: listings

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/listing_metrics`

Get listing performance metrics

> Returns numerical KPI data for a single listing, including listing-level metrics
> and market-level comparison data. Metrics include occupancy, revenue, ADR, RevPAR,
> adjusted occupancy, base price ratio, min prices (Days at Minimum Price), and last booked date.
> 
> **Response Structure:**
> - **listing_level**: Raw metric values from the listing's own historical data. DFD (Days From Date, i.e. days relative to today)-based metrics have nested objects keyed by DFD string. Non-DFD metrics (`bp_ratio`, `last_booked_date`) are scalar values. STLY (Same Time Last Year) comparisons are stored as `stly_<metric_name>` keys.
> - **market_level**: Raw market comparison values from portfolio/market engine data. Only includes metrics with market comparison (occupancy, adjusted_occupancy, adr).
> 
> **Useful Comparisons:**
> - **Listing vs Market:** Compare `listing_level[metric][dfd]` with `market_level[metric][dfd]` at the same DFD (Days From Date) for occupancy/ADR to gauge pricing position.
> - **Listing vs STLY:** Compare `listing_level.revenue[dfd]` with `listing_level.stly_revenue[dfd]` for year-over-year growth.
> - **bp_ratio:** > 1 means priced above recommendation, < 1 means below.
> - **min_prices:** Percentage of days at minimum price per future window. High values suggest a base price review.
> 
> **DFD (Days From Date) Keys:**
> 
> Negative = past, Positive = future. Keys are strings.
> 
> Default set: `-999, -90, -60, -45, -30, -21, -15, -7, 1, 2, 3, 7, 10, 15, 21, 30, 45, 60, 90, 120, 180, 240, 300, 360`.
> Current-month metrics also include `-997`. `min_prices` uses only: `7, 15, 21, 30, 45, 60, 90`.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query | Y | string | Unique listing ID (same as PriceLabs dashboard). |
| `pms_name` | query | Y | string | PMS name the listing belongs to. |
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | object |  |
| `data.listing_level` | object | Raw numerical listing-level metric data. DFD-based metrics have nested objects keyed by DFD string. Non-DFD metrics are scalar values. STLY comparisons are stored as `stly_<metric_name>` keys. |
| `data.listing_level.occupancy` | object | Occupancy percentage per DFD window. |
| `data.listing_level.revenue` | object | Revenue per DFD window. |
| `data.listing_level.adr` | object | Average Daily Rate per DFD window. |
| `data.listing_level.revpar` | object | Revenue Per Available Room per DFD window. |
| `data.listing_level.adjusted_occupancy` | object | Adjusted occupancy percentage per DFD window. |
| `data.listing_level.min_prices` | object | Percentage of days at minimum price per future DFD window (keys 7, 15, 21, 30, 45, 60, 90). |
| `data.listing_level.bp_ratio` | number | Base price ratio. > 1 means above recommendation, < 1 means below.; format double |
| `data.listing_level.last_booked_date` | string|null | ISO date of the last booking. Null if no bookings. |
| `data.listing_level.stly_occupancy` | object | Same-time-last-year occupancy per DFD window. |
| `data.listing_level.stly_revenue` | object | Same-time-last-year revenue per DFD window. |
| `data.listing_level.stly_adr` | object | Same-time-last-year ADR per DFD window. |
| `data.listing_level.stly_revpar` | object | Same-time-last-year RevPAR per DFD window. |
| `data.listing_level.currency` | string|null | Currency used for monetary listing-level metrics, sourced from the stored listing metric set. |
| `data.market_level` | object | Raw numerical market comparison data. Only includes metrics with market comparison (occupancy, adjusted_occupancy, adr). |
| `data.market_level.occupancy` | object | Market occupancy percentage per DFD window. |
| `data.market_level.adjusted_occupancy` | object | Market adjusted occupancy per DFD window. |
| `data.market_level.adr` | object | Market ADR per DFD window. |
| `data.market_level.currency` | string|null | Currency used for monetary market-level metrics, sourced from the stored market metric set. |

Errors: `400`, `401`, `404`, `422`


## `GET /v1/listings`

Get all listings in an account

> This API call will return all the listings in a customer's account across all PMSs, with their minimum price, base price, recommended base price and maximum price along with other Performance Metrics available on the Pricing Dashboard and Multi-Calendar pages. You can find performance metrics after clicking "Add Metrics" button on the Pricing Dashboard or Multi Calendar.

| param | in | req | type | notes |
|---|---|---|---|---|
| `skip_hidden` | query |  | boolean | This param can be used to filter hidden listings. Default is false, which returns all listings including hidden ones. Set to true to exclude hidden listings.; default False |
| `only_syncing_listings` | query |  | boolean | This param can be used to filter listings based on their sync status. Default is false, which returns all listings in the PriceLabs user account. If set to true, only listings with sync turned ON are returned.; default False |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `listings` | array[object] |  |
| `listings[].id` | string | Unique listing ID |
| `listings[].pms` | string | PMS that this listing belongs to. |
| `listings[].name` | string | Name of the listing |
| `listings[].latitude` | string |  |
| `listings[].longitude` | string |  |
| `listings[].country` | string |  |
| `listings[].city_name` | string |  |
| `listings[].state` | string |  |
| `listings[].currency` | string|null | Current pricing currency for the listing. |
| `listings[].no_of_bedrooms` | number | Number of bedrooms in the listing. For Studio/Hotel room, it will be 0. If null, then bedroom count is not provided by the PMS via API. In such cases, bedroom count must be updated via PriceLabs account.; format double |
| `listings[].cleaning_fees` | number | Cleaning fee for the listing; format double |
| `listings[].channel_listing_details` | array[object] | List of channel-specific listing identifiers |
| `listings[].channel_listing_details[].channel_name` | string | Name of the OTA/channel (e.g., airbnb, bookingcom, vrbo, expedia) |
| `listings[].channel_listing_details[].channel_listing_id` | string | Listing ID on the respective channel |
| `listings[].min` | number | minimum price for the listing; format double |
| `listings[].base` | number | base price for the listing; format double |
| `listings[].max` | number | maximum price for the listing; format double |
| `listings[].group` | string | Listing Group |
| `listings[].group_id` | integer | Numeric ID of the listing group |
| `listings[].subgroup` | string | Listing Sub group |
| `listings[].subgroup_id` | integer | Numeric ID of the listing subgroup |
| `listings[].tags` | string | PriceLabs tags for the listing |
| `listings[].notes` | string | Notes added for the listing |
| `listings[].isHidden` | boolean | If the listing is hidden or not on the PriceLabs Pricing dashboard |
| `listings[].push_enabled` | boolean | If Sync is turned ON for the listing or not |
| `listings[].last_date_pushed` | string | Last synced time |
| `listings[].last_refreshed_at` | string | Last time the prices were refreshed |


## `POST /v1/listings`

Update one or more listings in an account

> Update pricing, tags, sync status, and group/subgroup assignment for one or more listings in a PriceLabs account.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `listings` | Y | array[object] | Listings to update |
| `listings[].id` | Y | string | Unique listing ID |
| `listings[].pms` | Y | string | PMS that this listing belongs to. |
| `listings[].base` |  | number | Base price for the listing; format double |
| `listings[].min` |  | number | Minimum price for the listing; format double |
| `listings[].max` |  | number | Maximum price for the listing; format double |
| `listings[].tags` |  | array[string] | Tags for the listing. Maximum of 10 tags per listing. |
| `listings[].push_enabled` |  | string | Toggle price sync ON ("true") or OFF ("false") for the listing. Must be passed as a string, not a boolean. |
| `listings[].group_id` |  | integer | Numeric ID of the Group |
| `listings[].subgroup_id` |  | integer | Numeric ID of the Subgroup |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `listings` | array[object] | Updated listings with their new pricing values |
| `listings[].base` | number | Base price for the listing; format double |
| `listings[].id` | string | Unique listing ID |
| `listings[].max` | number | Maximum price for the listing; format double |
| `listings[].min` | number | Minimum price for the listing; format double |
| `listings[].push_enabled` | boolean | Current sync status after update |
| `listings[].group_id` | integer | Numeric ID of the Group |
| `listings[].subgroup_id` | integer | Numeric ID of the Subgroup |
| `listings[].errors` | array[string] | Present when tag or sync or group/subgroup updates failed for this listing |

Errors: `400`


## `GET /v1/listings/{listing_id}`

Get a specific listing in an account

> This API call will return a specific listing in a customer's account, with their minimum price, base price, recommended base price and maximum price along with other Performance Metrics available on the Pricing Dashboard and Multi-Calendar pages. You can find performance metrics after clicking "Add Metrics" button on the Pricing Dashboard or Multi Calendar.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | path | Y | string |  |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `listings` | array[object] |  |
| `listings[].id` | string | Unique listing ID |
| `listings[].pms` | string | PMS that this listing belongs to. |
| `listings[].name` | string | Name of the listing |
| `listings[].latitude` | string |  |
| `listings[].longitude` | string |  |
| `listings[].country` | string |  |
| `listings[].city_name` | string |  |
| `listings[].state` | string |  |
| `listings[].currency` | string|null | Current pricing currency for the listing. |
| `listings[].no_of_bedrooms` | number | Number of bedrooms in the listing. For Studio/Hotel room, it will be 0. If null, then bedroom count is not provided by the PMS via API. In such cases, bedroom count must be updated via PriceLabs account.; format double |
| `listings[].cleaning_fees` | number | Cleaning fee for the listing; format double |
| `listings[].min` | number | minimum price for the listing; format double |
| `listings[].base` | number | base price for the listing; format double |
| `listings[].max` | number | maximum price for the listing; format double |
| `listings[].group` | string | Listing Group |
| `listings[].group_id` | integer | Numeric ID of the listing group |
| `listings[].subgroup` | string | Listing Sub group |
| `listings[].subgroup_id` | integer | Numeric ID of the listing subgroup |
| `listings[].tags` | string | Tags for the listing |
| `listings[].notes` | string | Notes added for the listing |
| `listings[].isHidden` | boolean | If the listing is hidden or not on the PriceLabs Pricing dashboard |
| `listings[].push_enabled` | boolean | If Sync is turned ON for the listing or not |
| `listings[].last_date_pushed` | string | Last synced time |
| `listings[].last_refreshed_at` | string | Last time the prices were refreshed |
| `listings[].channel_listing_details` | array[object] | List of channel-specific listing identifiers |
| `listings[].channel_listing_details[].channel_name` | string | Name of the OTA/channel (e.g., airbnb, bookingcom, vrbo, expedia) |
| `listings[].channel_listing_details[].channel_listing_id` | string | Listing ID on the respective channel |


## `GET /v1/listings_minimal`

Get a minimal list of listings

> Returns a minimal, lightweight list of every listing in the account — just the core identifying fields (`listing_id`, `pms_name`, `listing_name`, `property_name`, `parent_key`, `group_id`) plus each listing's IDs on the booking channels/OTAs it is published on (`channel_listing_details` — Airbnb, Vrbo, Booking.com, Expedia, etc.). Unlike `GET /v1/listings`, this call returns no performance metrics or pricing, so it stays fast for large accounts that just need a quick listing directory or to map their PriceLabs listings to the corresponding channel listing IDs.

| param | in | req | type | notes |
|---|---|---|---|---|
| `search_query` | query |  | string | Partial match on listing name, ID fragment, city, tags, or groups. |
| `listing_name` | query |  | string | Partial match on listing name only (not for numeric IDs or UUIDs). |
| `listings` | query |  | string | Comma-separated exact listing IDs or UUIDs to return. |
| `pms` | query |  | string | Comma-separated PMS names to filter by (e.g. airbnb,hostaway). |
| `cities` | query |  | string | Comma-separated city names to filter by. |
| `groups` | query |  | string | Comma-separated group names to filter by. |
| `subgroups` | query |  | string | Comma-separated sub-group names to filter by. |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `listings` | array[object] |  |
| `listings[].listing_id` | string | Unique listing ID |
| `listings[].pms_name` | string | PMS that this listing belongs to |
| `listings[].listing_name` | string | Name of the listing |
| `listings[].property_name` | string | Name of the property the listing belongs to |
| `listings[].parent_key` | integer | Parent listing key for multi-unit / linked listings |
| `listings[].group_id` | integer|null | ID of the group the listing is assigned to (null if unassigned) |
| `listings[].channel_listing_details` | array[object] | The listing's IDs on each booking channel/OTA it is published on. Empty array when no channel IDs are known. |
| `listings[].channel_listing_details[].channel_name` | string | Name of the OTA/channel (e.g., airbnb, bookingcom, vrbo, expedia) |
| `listings[].channel_listing_details[].channel_listing_id` | string | Listing ID on the respective channel |
| `total_listings` | integer | Total number of listings returned |

Errors: `403`

