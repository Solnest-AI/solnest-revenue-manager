# PriceLabs REST API: actions

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/actions`

List actions for your listings

> Returns the Action Center alerts and recommendations for your listings: missing listing
> information, configuration issues, availability alerts, and pricing recommendations.
> 
> Grouped per listing, most important first. Listings with nothing flagged are omitted,
> so the array can be empty.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query |  | string | Restrict to this listing. Must be provided together with `pms`. |
| `pms` | query |  | string | PMS name of the listing. Must be provided together with `listing_id`. Omit both to return actions for every accessible listing. |
| `mode` | query |  | string | How the account's action visibility preferences are applied. `visible` (default) returns only actions that are not hidden, `all` ignores preferences, and `hidden` returns only the actions that have been hidden.; enum: `visible`, `all`, `hidden`; default visible |
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

Errors: `400`, `404`

