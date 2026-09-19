# PriceLabs REST API: dateSpecificOverridesDso

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `DELETE /v1/group_overrides`

Delete a group's date specific overrides

> Delete date specific overrides for a group by date.
> 
> **Notes**
> - Past dates cannot be deleted and are returned in `failed_dates`.
> - Dates with no existing DSO are returned in `failed_dates`.
> - Successfully deleted dates are returned in `deleted_dates`.
> - Team members need write permission on the group.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `id` | Y | integer | Numeric ID of the group |
| `overrides` | Y | array[object] | Override dates to delete |
| `overrides[].date` | Y | string | Override date to delete (YYYY-MM-DD); format date |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `id` | integer |  |
| `deleted_dates` | array[string] | Dates that were successfully deleted |
| `failed_dates` | array[object] | Dates that could not be deleted |
| `failed_dates[].date` | string |  |
| `failed_dates[].error` | string |  |

Errors: `400`, `403`


## `GET /v1/group_overrides`

Fetch a group's date specific overrides

> Returns date specific overrides (DSOs) for a group. Only overrides from today onwards are returned.
> 
> Use `GET /v1/groups` to obtain valid group IDs.

| param | in | req | type | notes |
|---|---|---|---|---|
| `id` | query | Y | integer | Numeric ID of the group |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `id` | integer | Group ID |
| `overrides` | array[object] |  |
| `overrides[].date` | string | format date |
| `overrides[].created_at` | string | format date-time |
| `overrides[].updated_at` | string | format date-time |
| `overrides[].price` | string | If `price_type` is `fixed`, the fixed price. If `price_type` is `percent` or `percent_base`, the percentage change (range -75 to 1000). |
| `overrides[].price_type` | string | Can be a fixed amount, a percentage on the recommended price, or a percentage on the base price. `percent_stacked` is not supported for group DSOs.; enum: `percent`, `fixed`, `percent_base` |
| `overrides[].currency` | string | Present when a fixed price/min price/max price is set. |
| `overrides[].base_price` | number | Base price for the override date; format double |
| `overrides[].min_stay` | number | Minimum stay (only returned when greater than 0); format double |
| `overrides[].min_price` | number | If `min_price_type` is `fixed`, the fixed minimum price. If `percent_base` or `percent_min`, a percentage change on the base or minimum price (range -75 to 1000).; format double |
| `overrides[].min_price_type` | string | enum: `fixed`, `percent_base`, `percent_min` |
| `overrides[].max_price` | number | If `max_price_type` is `fixed`, the fixed maximum price. If `percent_base` or `percent_max`, a percentage change on the base or maximum price (range -75 to 1000).; format double |
| `overrides[].max_price_type` | string | enum: `fixed`, `percent_base`, `percent_max` |
| `overrides[].check_in_check_out_enabled` | string | `0` if check-in/check-out is disabled for the DSO. `1` if enabled — when enabled, `check_in` and `check_out` values are also returned. |
| `overrides[].check_in` | string | A binary string of 7 characters, one per day of the week starting Monday through Sunday. `0` = not allowed, `1` = allowed. |
| `overrides[].check_out` | string | A binary string of 7 characters, one per day of the week starting Monday through Sunday. `0` = not allowed, `1` = allowed. |
| `overrides[].reason` | string |  |
| `message` | string | Present when no DSOs are found for the group |

Errors: `400`


## `POST /v1/group_overrides`

Add/Update a group's date specific overrides

> Add or update date specific overrides for a group. Valid dates are from today through 2 years from today.
> 
> **Notes**
> - Successfully validated overrides are saved even if other dates in the same request fail. Failed dates are returned in `failed_dates`.
> - `price_type` values for group DSOs are `fixed`, `percent`, and `percent_base`. `percent_stacked` is not supported.
> - For fixed prices, the value must be greater than 10.
> - Team members need write permission on the group.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `id` | Y | integer | Numeric ID of the group |
| `overrides` | Y | array[object] | Date specific overrides to add or update |
| `overrides[].date` | Y | string | Override date (YYYY-MM-DD). Must be between today and 2 years from today.; format date |
| `overrides[].price` |  | string | If `price_type` is `fixed`, the fixed price (must be greater than 10). If `percent` or `percent_base`, the percentage change (range -75 to 1000). |
| `overrides[].price_type` |  | string | Required when `price` is provided. Must be `fixed`, `percent`, or `percent_base`.; enum: `percent`, `fixed`, `percent_base` |
| `overrides[].currency` |  | string | Required when `price_type` is `fixed`. |
| `overrides[].min_stay` |  | number | Minimum stay. Must be an integer greater than 0.; format double |
| `overrides[].min_price` |  | number | If `min_price_type` is `fixed`, the fixed minimum price. If `percent_base` or `percent_min`, a percentage change on the base or minimum price (range -75 to 1000).; format double |
| `overrides[].min_price_type` |  | string | enum: `fixed`, `percent_base`, `percent_min` |
| `overrides[].max_price` |  | number | If `max_price_type` is `fixed`, the fixed maximum price. If `percent_base` or `percent_max`, a percentage change on the base or maximum price (range -75 to 1000).; format double |
| `overrides[].max_price_type` |  | string | enum: `fixed`, `percent_base`, `percent_max` |
| `overrides[].base_price` |  | number | Base price for the override date; format double |
| `overrides[].check_in_check_out_enabled` |  | string | `0` if check-in/check-out is disabled. `1` if enabled — also send `check_in` and `check_out` when enabled. |
| `overrides[].check_in` |  | string | A binary string of 7 characters, one per day starting Monday through Sunday. `0` = not allowed, `1` = allowed. |
| `overrides[].check_out` |  | string | A binary string of 7 characters, one per day starting Monday through Sunday. `0` = not allowed, `1` = allowed. |
| `overrides[].reason` |  | string |  |
| `overrides[].lead_time_expiry` |  | number | The DSO expires within this many days of the stay date. Allowed values are 1 to 999.; format double |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `id` | integer |  |
| `overrides` | array[object] | Successfully saved overrides |
| `overrides[].date` | string | format date |
| `overrides[].price` | string |  |
| `overrides[].price_type` | string |  |
| `overrides[].currency` | string |  |
| `overrides[].base_price` | number | format double |
| `overrides[].min_stay` | number | Minimum stay set by this override for the date. An integer greater than 0; omitted when the override does not set a minimum stay.; format double |
| `overrides[].min_price` | number | format double |
| `overrides[].min_price_type` | string |  |
| `overrides[].max_price` | number | format double |
| `overrides[].max_price_type` | string |  |
| `overrides[].check_in_check_out_enabled` | string |  |
| `overrides[].check_in` | string |  |
| `overrides[].check_out` | string |  |
| `overrides[].reason` | string |  |
| `overrides[].lead_time_expiry` | number | format double |
| `failed_dates` | array[object] | Dates that failed validation or were out of range |
| `failed_dates[].date` | string |  |
| `failed_dates[].error` | string |  |

Errors: `400`, `403`


## `DELETE /v1/listings/{listing_id}/overrides`

Delete a listing's date specific override

> Use this API to delete date specific overrides for a listing.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | path | Y | string | Listing ID |
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `overrides` | Y | array[object] | Override dates to delete |
| `overrides[].date` | Y | string |  |
| `pms` | Y | string | PMS name of the listing |
| `update_children` |  | boolean | Must be a JSON boolean (`true` or `false`). If `true`, the DSO is also deleted for all child listings. If `false` or omitted, only the parent listing is deleted. |

Errors: `400`


## `GET /v1/listings/{listing_id}/overrides`

To fetch a listing's date specific overrides

> Use this API to get your listing's date specific overrides. By default, only overrides from today onwards are returned. Use the optional `start_date` and `end_date` query parameters to filter the date range.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | path | Y | string | Listing ID |
| `pms` | query | Y | string | PMS name of the listing |
| `start_date` | query |  | string | Filter overrides from this date onwards (YYYY-MM-DD). Defaults to today if omitted.; format date |
| `end_date` | query |  | string | Filter overrides up to and including this date (YYYY-MM-DD). If omitted, all overrides from `start_date` onwards are returned.; format date |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `overrides` | array[object] |  |
| `overrides[].date` | string |  |
| `overrides[].created_at` | string | format date-time |
| `overrides[].updated_at` | string | format date-time |
| `overrides[].price` | string | If price_type is fixed, then price represents the fixed price. If price_type is percent or percent_stacked, then price is the percentage change on the recommended price and should have a value ranging from -75 to 1000. |
| `overrides[].price_type` | string | Can be a fixed amount or a percentage applied on the recommended price. `percent_stacked` stacks on top of other percentage adjustments.; enum: `percent`, `fixed`, `percent_stacked` |
| `overrides[].currency` | string |  |
| `overrides[].base_price` | number | Base price for the override date; format double |
| `overrides[].min_stay` | number | Minimum stay set by this override for the date. An integer greater than 0; omitted when the override does not set a minimum stay.; format double |
| `overrides[].min_price` | number | If min_price_type is fixed, then min_price is the fixed price. If min_price_type is percent_base or percent_min, then min_price represents a percentage change on the base price or the minimum price, respectively, and sho |
| `overrides[].min_price_type` | string | Can be set as a fixed amount OR a percentage change on the minimum price or a percentage change on the base price; enum: `fixed`, `percent_base`, `percent_min` |
| `overrides[].max_price` | number | If max_price_type is fixed, then max_price is the fixed maximum price. If max_price_type is percent_base or percent_max, then max_price represents a percentage change on the listing base price or the maximum price, respe |
| `overrides[].max_price_type` | string | Can be set as a fixed amount OR a percentage change on the maximum price or a percentage change on the  base price; enum: `fixed`, `percent_base`, `percent_max` |
| `overrides[].check_in_check_out_enabled` | string | `0` if check-in/check-out is disabled for the DSO. `1` if check-in/check-out is enabled — when enabled, `check_in` and `check_out` values are also returned. |
| `overrides[].check_in` | string | A binary string of 7 characters, one per day of the week starting Monday through Sunday. `0` = not allowed, `1` = allowed. e.g. `1000001` means check-in is allowed only on Monday and Sunday. |
| `overrides[].check_out` | string | A binary string of 7 characters, one per day of the week starting Monday through Sunday. `0` = not allowed, `1` = allowed. e.g. `0010000` means check-out is allowed only on Wednesday. |
| `overrides[].reason` | string |  |
| `overrides[].lead_time_expiry` | number | The DSO expires within this many days of the stay date. Allowed values are 1 to 999.; format double |

Errors: `400`, `404`


## `POST /v1/listings/{listing_id}/overrides`

Add/Update a listing's date specific override

> Use this API to add or update date specific overrides for a listing.
> 
> **Notes**
> - If any override in the request fails validation, the entire request fails with 400 and no overrides are saved.
> - Price type option `percent_stacked` option is available only for users who have the feature enabled, if you want to use it, please reach out to support@pricelabs.co.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | path | Y | string | Listing ID |
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `overrides` | Y | array[object] | Date specific overrides to add or update |
| `overrides[].date` |  | string | Override date |
| `overrides[].price` |  | string | If `price_type` is `fixed`, the fixed price. If `price_type` is `percent` or `percent_stacked`, the percentage change on the recommended price (range -75 to 1000). |
| `overrides[].price_type` |  | string | Must be `fixed`, `percent`, or `percent_stacked`. Required when `price` is provided. If `fixed`, `currency` must exactly match your PMS or the update results in erroneous data. If `percent` or `percent_stacked`, the change is applied on the recommended base price.; enum: `percent`, `fixed`, `percent |
| `overrides[].currency` |  | string | Required when `price_type` is `fixed`. Must exactly match the currency in your PMS. |
| `overrides[].min_stay` |  | number | Minimum stay. Must be an integer greater than 0.; format double |
| `overrides[].min_price` |  | number | If `min_price_type` is `fixed`, the fixed minimum price. If `percent_base` or `percent_min`, a percentage change on the base or minimum price, respectively (range -75 to 1000).; format double |
| `overrides[].min_price_type` |  | string | Minimum price type. Use `fixed` for an absolute price — `currency` is required and must exactly match your PMS. Use `percent_base` or `percent_min` for percentage adjustments on the base or minimum price, respectively.; enum: `fixed`, `percent_base`, `percent_min` |
| `overrides[].max_price` |  | number | If `max_price_type` is `fixed`, the fixed maximum price. If `percent_base` or `percent_max`, a percentage change on the base or maximum price, respectively (range -75 to 1000).; format double |
| `overrides[].max_price_type` |  | string | enum: `fixed`, `percent_base`, `percent_max` |
| `overrides[].base_price` |  | number | Base price for the override date; format double |
| `overrides[].check_in_check_out_enabled` |  | string | `0` if check-in/check-out is disabled. `1` if enabled — also send `check_in` and `check_out` when enabled. |
| `overrides[].check_in` |  | string | A binary string of 7 characters, one per day starting Monday through Sunday. `0` = not allowed, `1` = allowed. e.g. `1000001` = check-in allowed only on Monday and Sunday. |
| `overrides[].check_out` |  | string | A binary string of 7 characters, one per day starting Monday through Sunday. `0` = not allowed, `1` = allowed. e.g. `0010000` = check-out allowed only on Wednesday. |
| `overrides[].reason` |  | string |  |
| `overrides[].lead_time_expiry` |  | number | The DSO expires within this many days of the stay date. Allowed values are 1 to 999.; format double |
| `pms` | Y | string | PMS name of the listing |
| `update_children` |  | boolean | Must be a JSON boolean (`true` or `false`). If `true`, the DSO is also updated for all child listings. If `false` or omitted, only the parent listing is updated. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `overrides` | array[object] | Successfully updated overrides for the request. |
| `overrides[].date` | string |  |
| `overrides[].price` | string |  |
| `overrides[].price_type` | string |  |
| `overrides[].currency` | string |  |
| `overrides[].base_price` | number | format double |
| `overrides[].min_stay` | number | Minimum stay set by this override for the date. An integer greater than 0; omitted when the override does not set a minimum stay.; format double |
| `overrides[].min_price` | number | format double |
| `overrides[].min_price_type` | string |  |
| `overrides[].max_price` | number | format double |
| `overrides[].max_price_type` | string |  |
| `overrides[].check_in_check_out_enabled` | string | `0` if check-in/check-out is disabled. `1` if enabled. |
| `overrides[].check_in` | string | Binary string of 7 characters for allowed check-in days (Monday–Sunday). |
| `overrides[].check_out` | string | Binary string of 7 characters for allowed check-out days (Monday–Sunday). |
| `overrides[].reason` | string |  |
| `overrides[].lead_time_expiry` | number | The DSO expires within this many days of the stay date. Allowed values are 1 to 999.; format double |
| `child_listings_update_info` | object | Included when `update_children` is `true`. Maps child listing IDs to their update status. Returns an empty object if the listing has no child listings. |

Errors: `400`

