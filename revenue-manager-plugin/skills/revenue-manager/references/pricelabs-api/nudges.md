# PriceLabs REST API: nudges

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/nudges/accept`

Accept a nudge

> Accepts a price nudge for a single listing, updating the listing's
> price to the nudge-recommended value and marking the nudge as
> accepted.
> 
> Requires write permission on the listing. Sub-users/team-users
> without write permission receive a 403 response.
> 
> The endpoint verifies the nudge is still the latest pending
> recommendation for that listing and nudge type; if a newer nudge
> exists, a 409 Conflict is returned.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `nudge_id` | Y | string | UUID of the nudge to accept; format uuid |
| `listing_id` | Y | string | Listing ID the nudge applies to |
| `pms` | Y | string | PMS name for the listing |
| `update_children` |  | boolean | When true, propagate the price change to child listings; default False |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `nudge_id` | string | format uuid |
| `listing_id` | string |  |
| `pms_name` | string |  |
| `nudge_type` | string | enum: `base_price`, `min_price` |
| `status` | string |  |
| `applied_value` | integer | The price value that was applied to the listing |
| `update_children` | boolean |  |

Errors: `400`, `403`, `404`, `409`, `500`


## `GET /v1/nudges/available`

List available nudges

> Returns pending, non-expired nudges for listings accessible to the
> authenticated user. Results can be filtered by nudge type,
> listing ID, and PMS name.

| param | in | req | type | notes |
|---|---|---|---|---|
| `nudge_type` | query |  | string | Filter by nudge type. Omit to return all types.; enum: `base_price`, `min_price` |
| `listing_id` | query |  | string | Filter by listing ID. Requires `pms` when provided. |
| `pms` | query |  | string | Filter by PMS name. Required when `listing_id` is provided. |
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `nudges` | array[object] |  |
| `nudges[].listing_id` | string |  |
| `nudges[].pms_name` | string |  |
| `nudges[].listing_name` | string |  |
| `nudges[].nudge_type` | string | enum: `base_price`, `min_price` |
| `nudges[].nudge_id` | string | format uuid |
| `nudges[].current_value` | integer | Current value of the price field on the listing |
| `nudges[].suggested_value` | integer | Nudge-recommended value |
| `nudges[].direction` | string | Whether the nudge suggests an increase or decrease |
| `nudges[].reason` | string | Explanation for the recommendation |
| `nudges[].expiration` | string | ISO 8601 timestamp after which the nudge expires; format date-time |
| `nudges[].status` | string |  |

Errors: `400`

