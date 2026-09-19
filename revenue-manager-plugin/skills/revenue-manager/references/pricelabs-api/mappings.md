# PriceLabs REST API: mappings

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/mappings/map`

Map listings under a parent listing

> Maps (links) one or more child listings under a parent listing — parent-child mapping. Mapping groups the same physical property's listings across channels (for example its Airbnb and Vrbo listings) under one parent so they are managed and priced together.
> 
> By default this only links the listings: nothing is copied from the parent, and children keep their own prices and settings. Use the optional `copy` flags to copy the parent's prices or settings to the children at map time.
> 
> > **Warning:** `copy.customization` also deletes each child's future date-specific overrides and replaces them with the parent's.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `parent` | Y | object | The listing that will be the parent. Must not itself be mapped as a child. |
| `parent.listing_id` | Y | string |  |
| `parent.pms_name` | Y | string |  |
| `children` | Y | array[object] | Listings to map under the parent. Each must currently be unmapped (standalone); an already-mapped listing must be unmapped first. A child cannot be on the same PMS as the parent (unless same-PMS mapping is enabled for the account). |
| `children[].listing_id` | Y | string |  |
| `children[].pms_name` | Y | string |  |
| `copy` |  | object | What to copy from the parent to each child at map time. All default false. |
| `copy.min_max_base` |  | boolean | Copy the parent's min/base/max prices to each child.; default False |
| `copy.customization` |  | boolean | Copy the parent's pricing customizations to each child. Also deletes each child's future date-specific overrides and replaces them with the parent's.; default False |
| `copy.group` |  | boolean | Copy the parent's group/subgroup assignment.; default False |
| `copy.notes` |  | boolean | Copy the parent's notes and note reminders.; default False |
| `copy.tags` |  | boolean | Copy the parent's tags.; default False |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `status` | integer |  |
| `success` | string |  |

Errors: `400`, `403`


## `POST /v1/mappings/unmap`

Unmap listings from their parent

> Unmaps (detaches) listings from their parent-child mapping group. Each listing becomes standalone again and keeps its own prices and settings. Unmapping a parent listing detaches its whole group. Partial success is supported — the response lists which listings were unmapped and which failed.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `listings` | Y | array[object] | The listings to unmap. |
| `listings[].listing_id` | Y | string |  |
| `listings[].pms_name` | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `success` | array[object] | Listings that were unmapped |
| `success[].listing_id` | string |  |
| `success[].pms_name` | string |  |
| `success[].unique_id` | string |  |
| `success[].listing_name` | string |  |
| `failure` | array[object] | Listings that could not be unmapped |
| `failure[].listing_id` | string |  |
| `failure[].listing_name` | string |  |
| `failure[].type` | string | Failure type, e.g. not_available (unknown or not mapped) or no_access (no write permission) |
| `failure[].message` | string |  |

Errors: `400`, `403`

