# PriceLabs REST API: reportBuilder

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/report_builder/data`

Generate report data

> Triggers report generation using a previously saved template. Reports are processed asynchronously and require polling.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `template_id` | Y | integer | Template ID to generate data for. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `request_id` | string |  |
| `status` | string | enum: `IN_PROGRESS` |

Errors: `400`, `404`, `500`


## `POST /v1/report_builder/poll`

Poll report generation status

> Retrieves the status or generated report data for asynchronous report generation requests. Report generation sessions expire 30 minutes after creation.
> 
> **Polling behavior:**
> After calling the report generation endpoint, poll this endpoint periodically (recommended interval: 5–10 seconds) until you receive a terminal response.
> 
> Status values returned by the downstream service are **case-sensitive**.
> 
> **Continue polling when:**
> - `status: "IN_PROGRESS"` — The report is still being generated. Continue polling after a short delay.
> 
> **Stop polling when:**
> - The response contains `data.report_data` and **no `status` field** — The report is ready. Use `data.report_data` and `data.report_currency`.
> - `status: "STATUS_NOT_FOUND"` — The `request_id` is invalid or expired. This can happen if the session expired (30 minutes after creation) or the report data was already retrieved.
> - HTTP `400` — The `request_id` is missing, or no active session was found for the `request_id`.
> - HTTP `403` — Your API key does not have Report Builder access.
> - HTTP `500` — An internal error occurred. You may retry a few times, but if it persists, stop polling.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `request_id` | Y | string | Request identifier returned by the report generation endpoint |

Errors: `403`, `500`


## `GET /v1/report_builder/templates`

Fetch available report templates

> Returns all Report Builder templates accessible to the authenticated user (including default/canned templates provided by PriceLabs and custom templates created by the user). The response structure varies depending on the filters and columns applied to each template.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `templates` | array[object] | List of accessible template objects. |
| `templates[].templateId` | number | Unique identifier for the template.; format double |
| `templates[].name` | string | Template display name. |
| `templates[].description` | string | Brief explanation of the report scope. |
| `templates[].createdByDisplayName` | string | Creator identifier ("PriceLabs" for system defaults). |
| `templates[].lastGeneratedDate` | string | Timestamp of the last generation runtime. |
| `templates[].userId` | number | Owner's user ID (0 for system-wide templates).; format double |

