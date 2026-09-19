# PriceLabs REST API: bookingsReport

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/bookings_report`

Get bookings report with filters and pagination

> Returns a paginated bookings/reservations report for the account. Supports date range filters
> (booked date or check-in date), listing-level filters, and various portfolio filters such as
> tags, groups, cities, bedroom count, and sync status.
> 
> At least one date filter group is recommended. If no date filters are provided, defaults to
> bookings from the last 90 days.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `date_filters` |  | object | Date range filters. Provide either booked date range or check-in date range (or both). |
| `date_filters.min_booked_date` |  | string | Start of booked date range (inclusive, `YYYY-MM-DD`).; format date |
| `date_filters.max_booked_date` |  | string | End of booked date range (inclusive, `YYYY-MM-DD`).; format date |
| `date_filters.min_check_in_date` |  | string | Start of check-in date range (inclusive, `YYYY-MM-DD`).; format date |
| `date_filters.max_check_in_date` |  | string | End of check-in date range (inclusive, `YYYY-MM-DD`).; format date |
| `filters` |  | object | Listing and booking filters. |
| `filters.pms` |  | string | Filter by PMS/channel name. |
| `filters.listings` |  | array[object] | Filter by specific listings. Each item must include `listing_id` and `pms_name`. |
| `filters.listings[].listing_id` | Y | string | The listing ID. |
| `filters.listings[].pms_name` | Y | string | PMS name for this listing. |
| `filters.tags` |  | string | Comma-separated list of tag names to filter by. |
| `filters.groups` |  | string | Comma-separated list of group IDs to filter by. |
| `filters.subgroups` |  | string | Comma-separated list of subgroup IDs to filter by. |
| `filters.cities` |  | string | Comma-separated list of city names to filter by. |
| `filters.brCount` |  | string | Comma-separated list of bedroom counts to filter by. |
| `filters.syncStatus` |  | string | Filter by price sync status. Use `true` for sync ON, `false` for sync OFF. |
| `filters.search_query` |  | string | Free-text search across listing names, IDs, and cities. |
| `filters.booking_status` |  | array[string] | Booking statuses to include. Valid values: `booked`, `cancelled`, `blocked`. Defaults to `["booked"]`. |
| `limit` |  | integer | Maximum number of rows to return (1-500). Defaults to 200.; min 1; max 500; default 200 |
| `offset` |  | integer | Number of rows to skip for pagination. Defaults to 0.; min 0; default 0 |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | object |  |
| `data.reservations` | array[object] | Array of reservation rows matching the filters. |
| `data.reservations[].listing_id` | string |  |
| `data.reservations[].listing_name` | string |  |
| `data.reservations[].pms_name` | string |  |
| `data.reservations[].reservation_id` | string |  |
| `data.reservations[].check_in` | string | format date |
| `data.reservations[].check_out` | string | format date |
| `data.reservations[].booked_date` | string |  |
| `data.reservations[].no_of_days` | integer |  |
| `data.reservations[].rental_revenue` | number | format double |
| `data.reservations[].total_cost` | number | format double |
| `data.reservations[].currency` | string |  |
| `data.reservations[].booking_status` | string |  |
| `data.reservations[].booking_channel` | string |  |
| `data.pagination` | object |  |
| `data.pagination.total` | integer | Total number of matching rows. |
| `data.pagination.offset` | integer | Current offset. |
| `data.pagination.limit` | integer | Rows per page. |
| `data.pagination.has_more` | boolean | Whether more pages exist. |

Errors: `400`, `502`

