# PriceLabs REST API: groups

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/group_listings`

Get listings assigned to a group or subgroup

> Returns listings assigned to the provided `group_id` or `subgroup_id`. At least one of `group_id` or `subgroup_id` is required. If both are provided, listings must match both filters.

| param | in | req | type | notes |
|---|---|---|---|---|
| `group_id` | query |  | integer | Numeric ID of the group |
| `subgroup_id` | query |  | integer | Numeric ID of the subgroup |
| `page_size` | query |  | integer | Number of listings to return per page. Defaults to 50.; default 50 |
| `page_number` | query |  | integer | Page number to fetch. Defaults to 1.; default 1 |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `group_id` | integer|null | Group ID used to filter listings |
| `subgroup_id` | integer|null | Subgroup ID used to filter listings |
| `listings` | array[object] |  |
| `listings[].listing_id` | string | Unique listing ID |
| `listings[].listing_name` | string | Name of the listing |
| `listings[].pms` | string | PMS that this listing belongs to |
| `pagination` | object |  |
| `pagination.page_number` | integer |  |
| `pagination.page_size` | integer |  |
| `pagination.total_records` | integer |  |
| `pagination.total_pages` | integer |  |
| `message` | string | Present when no listings are found |

Errors: `400`


## `GET /v1/groups`

Get all groups in an account

> Returns all groups available in the customer's account. Each group includes whether it currently has listings assigned to it.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `groups` | array[object] |  |
| `groups[].id` | integer | Numeric ID of the group |
| `groups[].name` | string | Name of the group |
| `groups[].has_listings` | boolean | Whether this group has listings assigned to it |


## `POST /v1/groups`

Create a new group

> Creates a new group and returns the group ID.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `group_name` | Y | string | Name of the group |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `id` | integer | Numeric ID of the new group |

Errors: `400`

