# PriceLabs REST API: logs

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/logs`

Retrieve activity logs

> Fetches paginated activity logs for the authenticated user. Supports
> filtering by log type, entity identifiers, actions, team members, and date range.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string | PriceLabs Customer API key (found in Account Settings > API Details). |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `log_type` | Y | string | Entity type to which the logs belong.; enum: `listing`, `group`, `account` |
| `actions` |  | array[string] | Action keys to filter by. Allowed values depend on `log_type`. |
| `listings` |  | array[object] | Listing identifiers to filter by. Each entry requires `listing_id` and `pms`. Only applicable when `log_type` is `listing`. |
| `listings[].listing_id` | Y | string | The listing identifier. |
| `listings[].pms` | Y | string | The PMS name for the listing. |
| `group_names` |  | array[string] | Group names to filter by. Only applicable when `log_type` is `group`. |
| `pms_names` |  | array[string] | PMS names to filter by. Only applicable when `log_type` is `account`. |
| `user_ids` |  | array[integer] | User IDs to filter logs by specific team members. |
| `start_date` |  | string | Start of date range filter (YYYY-MM-DD). Defaults to 30 days ago.; format date |
| `end_date` |  | string | End of date range filter (YYYY-MM-DD). Defaults to today.; format date |
| `offset` |  | integer | Number of records to skip. Defaults to 0, maximum 1000.; min 0; max 1000; default 0 |
| `limit` |  | integer | Number of records to return. Defaults to 50, maximum 200.; min 1; max 200; default 50 |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | array[object] |  |
| `data[].action` | string | Raw action key. One of the values listed under the `actions` filter parameter.; enum: `base_price`, `base_price_from_parent`, `base_price_from_parent_during_mapping`, `min_price`, `min_price_from_parent`, `min_price_from |
| `data[].action_label` | string | Human-readable label for the action. |
| `data[].log_type` | string | enum: `listing`, `group`, `account` |
| `data[].entity` | object | Entity shape varies by type: - `listing`: includes `listing_id`, `name`, `pms_name`, `pms_display_name` - `group`: includes `group_name` - `account`: includes `pms_name`, `pms_display_name`  If a listing has been deleted |
| `data[].entity.type` | string | enum: `listing`, `group`, `account` |
| `data[].entity.listing_id` | string | Listing identifier (only present for listing entities). |
| `data[].entity.name` | string|null | Display name of the listing. Returns "N/A" for deleted listings. |
| `data[].entity.group_name` | string | Group name (only present for group entities). Returns "GroupDeleted" for deleted groups. |
| `data[].entity.pms_name` | string | PMS identifier (present for listing and account entities). |
| `data[].entity.pms_display_name` | string | Human-readable PMS display name (present for listing and account entities). |
| `data[].user` | object |  |
| `data[].user.id` | integer |  |
| `data[].user.email` | string|null |  |
| `data[].changes` | oneOf | What changed. The fields returned depend on the action — see the schemas below. |
| `data[].metadata` | object |  |
| `data[].metadata.ip_address` | string|null |  |
| `data[].metadata.device_type` | string|null | Request context. Typically `web`, `mobile`, or `api`. |
| `data[].created_at` | string | Timestamp of when the action was performed.; format date-time |
| `pagination` | object |  |
| `pagination.offset` | integer | Number of records skipped. |
| `pagination.limit` | integer | Number of records returned per request. |
| `pagination.total` | integer | Total number of matching log entries. |

Errors: `400`, `401`, `403`, `500`, `503`

