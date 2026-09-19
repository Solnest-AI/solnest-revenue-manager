# PriceLabs REST API: prices

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/fetch_rate_plans`

Fetch rate plan adjustments for your listings

> If your listings have rate plan adjustments, you can use this API call to fetch those adjustments. You can fetch the prices for the default rate plan using the [POST /v1/listing_prices](api:capi:POST/v1/listing_prices) call and use the adjustments returned in this call to derive the prices of the non-default rate plans for your system.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query | Y | string |  |
| `pms_name` | query | Y | string |  |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `rate_plans` | object |  |
| `rate_plans.id` | string | Listing ID |
| `rate_plans.pms` | string | PMS name |
| `rate_plans.name` | string | Listing name |
| `rate_plans.rateplans` | object | Rate plans keyed by rate plan ID |

Errors: `403`


## `POST /v1/listing_prices`

Get prices for listings

> Get prices for listings in your PriceLabs account. Returns the last-refreshed price information for each listing.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `listings` | Y | array[object] | Listings to fetch prices for. Each listing and its PMS must already exist in your PriceLabs account. |
| `listings[].id` | Y | string | Unique listing ID. The listing must exist in your PriceLabs account. |
| `listings[].pms` | Y | string | PMS name for the listing. Must match the PMS the listing is connected under in PriceLabs. |
| `listings[].dateFrom` |  | string | Optional start of date range (`YYYY-MM-DD`). Used only if it falls within the listing's available pricing calendar; otherwise the calendar start is used.; format date |
| `listings[].dateTo` |  | string | Optional end of date range (`YYYY-MM-DD`). Used only if it falls within the listing's available pricing calendar; otherwise the calendar end is used.; format date |
| `listings[].reason` |  | boolean | If truthy, each date entry in the response includes a pricing reason breakdown (`listing_info`, `market_factors`, `pricing_customizations`, etc.). |

Errors: `400`


## `POST /v1/refresh_listing`

Refresh a listing

> Recalculates prices for a listing on demand — the API equivalent of "Save & Refresh" in the PriceLabs app.
> 
> Writes such as [date-specific overrides](api:capi:POST/v1/listings/{listing_id}/overrides) are stored immediately but do not trigger a recalculation on their own: the prices returned by [POST /v1/listing_prices](api:capi:POST/v1/listing_prices) update at the next scheduled refresh (roughly every 24 hours). Call this endpoint after making your changes to apply them right away. The call is synchronous and returns the freshly computed pricing calendar in the response, so you can verify your changes in the same round trip.
> 
> > **Rate limits:** 3 calls per listing per 24 hours, and 10 calls per account per minute. Batch all changes for a listing before refreshing it.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `listing_id` | Y | string | Unique listing ID. The listing must exist in your PriceLabs account. |
| `pms` | Y | string | PMS name for the listing. Must match the PMS the listing is connected under in PriceLabs. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `pricing_array` | array[object] | One entry per date of the listing's pricing calendar, computed by this refresh. Values are returned as strings; `-1` denotes "not set". Additional internal fields may also be present. |
| `pricing_array[].date` | string | format date |
| `pricing_array[].price` | string | Final recommended price for the date, after all customizations, overrides, and min/max limits. |
| `pricing_array[].user_price` | string | Price after user adjustments for the date. |
| `pricing_array[].uncustomized_price` | string | Price before your customizations and overrides are applied. |
| `pricing_array[].min_price` | string | Minimum price in effect for the date. |
| `pricing_array[].max_price` | string | Maximum price in effect for the date. |
| `pricing_array[].min_stay` | string | Minimum stay in effect for the date. |
| `pricing_array[].dso_flag` | string | `1` if a date-specific override is applied on this date at any level, `0` otherwise. |
| `pricing_array[].listing_dso_flag` | string | `1` if a listing-level date-specific override is applied on this date. |
| `pricing_array[].group_dso_flag` | string | `1` if a group-level date-specific override is applied on this date. |
| `pricing_array[].sub_group_dso_flag` | string | `1` if a subgroup-level date-specific override is applied on this date. |
| `pricing_array[].acc_dso_flag` | string | `1` if an account-level date-specific override is applied on this date. |
| `pricing_array[].num_bookings` | string | Number of bookings on the date. |
| `pricing_array[].unbookable` | string | `1` if the date is blocked or otherwise unbookable. |
| `pricing_array[].demand` | string | Demand indicator for the date. |
| `pricing_array[].reasons_json` | string | JSON-encoded breakdown of how the price was computed (`listing_info`, `market_factors`, `pricing_customizations`, `thresholds`, etc.). |

Errors: `400`, `429`

