# PriceLabs REST API: reservations

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/create_reservations`

Create or update reservations

> Creates or updates reservations in PriceLabs for listings in your account.
> 
> Use this when you need to add bookings that are not synced from a PMS — for example
> direct bookings, offline stays, or booked times corrections. Each request accepts a `reservations`
> array of **1–100** reservation objects. The API validates and processes objects
> independently, so one invalid reservation does not block the rest of the batch.
> 
> **All 19 fields required.** Every reservation object must include all fields below (use
> `null` for inapplicable values). Extra unknown fields are rejected for that row.
> 
> | Field | Type | Notes |
> |-------|------|-------|
> | `listing_id` | string | Must exist for user's account |
> | `pms_name` | string | Must be a portfolio-analytics-enabled PMS |
> | `reservation_id` | string/null | Auto-generated as `{listing_id}_{start_date}_{end_date}` if null. Has to be unique for a PMS |
> | `start_date` | string | YYYY-MM-DD |
> | `end_date` | string | YYYY-MM-DD, must be after `start_date` |
> | `no_of_days` | number/null | Auto-computed from dates if null |
> | `total_cost` | number/null | Required (>0) when `pl_status=booked` |
> | `currency` | string | e.g. USD, EUR |
> | `booked_time` | string/null | Required when `pl_status=booked`, must be ≤ `start_date` |
> | `pl_status` | string | `booked`, `cancelled`, `blocked`, or `available` |
> | `cancelled_time` | string/null | Required when `pl_status=cancelled` |
> | `total_fees` | number/null | |
> | `total_taxes` | number/null | |
> | `rental_revenue` | number/null | |
> | `ota_commission` | number/null | |
> | `host_payout` | number/null | |
> | `booking_source` | string/null | `airbnb`, `vrbo`, `bcom`, `manual`, `others` |
> | `guest_count` | number/null | |
> | `guest_zipcode` | string/null | |
> 
> **Updates.** A unique reservation is identified by `reservation_id` + `pms_name`.
> - Reservations previously created or updated via this API (or CSV upload) can be updated.
> - Reservations already synced from a PMS fetch cannot be overwritten (`reservation already fetched via …`).
> - Reservation IDs must be unique for a PMS.
> 
> Reservations can only be added for PMS/channels that support Portfolio Analytics.
> The listing must belong to the authenticated account. Team-member API keys need
> **write** permission on every listing in the payload.
> 
> Created reservations are available from `GET /v1/reservation_data`.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `reservations` | Y | array[object] | Reservation rows to create or update. Maximum 100 per request. |
| `reservations[].listing_id` | Y | string | PriceLabs listing ID. Must exist on the account for `pms_name`. |
| `reservations[].pms_name` | Y | string | PMS or channel name for the listing (case-insensitive). Must support Portfolio Analytics. |
| `reservations[].reservation_id` | Y | string|null | Unique reservation ID for this PMS. If blank, PriceLabs generates `{listing_id}_{start_date}_{end_date}`. |
| `reservations[].start_date` | Y | string | Check-in date (`YYYY-MM-DD`). Must be before `end_date`.; format date |
| `reservations[].end_date` | Y | string | Check-out date (`YYYY-MM-DD`). Exclusive of the stay end in length-of-stay calculations (`end_date - start_date` nights).; format date |
| `reservations[].no_of_days` | Y | integer|null | Length of stay in nights. If omitted or it does not match `end_date - start_date`, the API uses the date difference. |
| `reservations[].total_cost` | Y | number|null | Total booking amount. Required and must be greater than `0` when `pl_status` is `booked`. Minimum `0` for other statuses.; format double |
| `reservations[].currency` | Y | string | ISO currency code (required). Stored uppercase (for example `USD`). |
| `reservations[].booked_time` | Y | string|null | Date the booking was made (`YYYY-MM-DD` or datetime). Required when `pl_status` is `booked`. Must be on or before `start_date`.; format date |
| `reservations[].pl_status` | Y | string | Reservation status. Values are normalized (lowercase, spaces removed).; enum: `booked`, `cancelled`, `blocked`, `available` |
| `reservations[].cancelled_time` | Y | string|null | Cancellation date. Required when `pl_status` is `cancelled`. Ignored for other statuses.; format date |
| `reservations[].total_fees` | Y | number|null | Total fees. Must be greater than or equal to `0` when provided.; format double |
| `reservations[].total_taxes` | Y | number|null | Total taxes. Must be greater than or equal to `0` when provided.; format double |
| `reservations[].rental_revenue` | Y | number|null | Rental revenue. Must be greater than `0` when provided on a `booked` reservation.; format double |
| `reservations[].ota_commission` | Y | number|null | OTA commission. Must be greater than or equal to `0` when provided.; format double |
| `reservations[].host_payout` | Y | number|null | Host payout. Must be greater than or equal to `0` when provided.; format double |
| `reservations[].booking_source` | Y | string|null | Booking channel. Mapped to `airbnb`, `vrbo`, `bcom`, `manual`, or `others` (unrecognized values become `others`). Stored on the reservation's booking info. |
| `reservations[].guest_count` | Y | integer|null | Number of guests. Must be greater than or equal to `0` when provided. |
| `reservations[].guest_zipcode` | Y | string|null | Guest zip or postal code. Stored on the reservation's booking info. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `success` | boolean | `true` when at least one reservation succeeded. `false` when every row failed. |
| `total` | integer | Number of reservation objects in the request. |
| `success_count` | integer | Number of rows that were created or updated. |
| `failure_count` | integer | Number of rows that failed validation or could not be saved. |
| `reservations` | array[object] | Per-row results in the same order as the request. |
| `reservations[].reservation` | object | The reservation payload that was processed (may include a generated `reservation_id`). |
| `reservations[].success` | boolean |  |
| `reservations[].error` | string | Present when `success` is `false`. |

Errors: `400`, `401`, `403`, `500`


## `GET /v1/reservation_data`

Get Reservations received from your PMS along with rental revenue information.

> Returns reservations in the PriceLabs account for the requested PMS. Includes reservations
> synced from the connected PMS and reservations created or updated through
> `POST /v1/create_reservations`.
> 
> The request must include at least one of the following date filter groups:
> - `start_date` and `end_date` (both required together)
> - `booked_start_date` and/or `booked_end_date` (either one is sufficient)

| param | in | req | type | notes |
|---|---|---|---|---|
| `pms` | query | Y | string | PMS to fetch reservations from. If the PMS does not provide reservations, no rows are returned. |
| `start_date` | query |  | string | Inclusive check-in filter start (`YYYY-MM-DD`). Filters reservations in `[start_date, end_date). If provided, also requires `end_date`.`.; format date |
| `end_date` | query |  | string | Exclusive check-in filter end (`YYYY-MM-DD`). Filters reservations in `[start_date, end_date)`. If provided, also requires `start_date`.; format date |
| `listing_id` | query |  | string | Optional filter to a single listing. |
| `include_hidden` | query |  | string | When `"false"`, hidden listings are excluded.; enum: `true`, `false`; default true |
| `booked_start_date` | query |  | string | Optional filter on booking date (inclusive, `YYYY-MM-DD`).; format date |
| `booked_end_date` | query |  | string | Optional filter on booking date (inclusive day, `YYYY-MM-DD`).; format date |
| `include` | query |  | string | When the value contains `available`, `available` reservations are included. |
| `limit` | query |  | integer | Results per page (default `100`).; default 100 |
| `offset` | query |  | integer | Pagination offset (default `0`). Increment while `next_page` is `true`.; default 0 |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `pms_name` | string | Lowercased PMS name from the request. |
| `next_page` | boolean | `true` when the number of returned rows equals `limit` (more pages may exist). Keep requesting until `false`. |
| `data` | array[object] | Reservation rows for the request. Empty when the PMS does not provide reservations. |
| `data[].listing_id` | string |  |
| `data[].listing_name` | string |  |
| `data[].unit_id` | string | Present for unit-level reservations; omitted for listing-level rows. |
| `data[].reservation_id` | string |  |
| `data[].check_in` | string | format date |
| `data[].check_out` | string | format date |
| `data[].booking_status` | string | Typically `booked` or `cancelled`. For `yourrentals_prod`, `blocked` may also appear. `available` when `include=available`.; enum: `booked`, `cancelled`, `blocked`, `available` |
| `data[].booked_date` | string|null | format date-time |
| `data[].rental_revenue` | oneOf | Numeric for supported PMSs; otherwise `"NA"`. |
| `data[].total_cost` | number|null | format double |
| `data[].no_of_days` | integer |  |
| `data[].currency` | string|null |  |
| `data[].cancelled_on` | string|null | format date-time |
| `data[].guestName` | string | Always returned as `Hidden`. |
| `data[].cleaning_fees` | number | Present only when provided by the PMS in booking info.; format double |
| `data[].booking_channel` | string | Present only when provided in booking info (`pl_source`). |
| `data[].channelConfirmationCode` | string | Present only when provided in booking info. |
| `data[].guest_count` | integer | Present only when provided by the PMS in booking info. |
| `data[].ota_commission` | number | Present only when provided by the PMS.; format double |

Errors: `400`, `401`, `403`

