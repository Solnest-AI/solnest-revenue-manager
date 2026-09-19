# PriceLabs REST API: revenueEstimatorVersion2

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v2/revenue/estimator`

Get Revenue, ADR, and Occupancy metrics for a location

> Either address or both lat and lng must be provided as location input.

| param | in | req | type | notes |
|---|---|---|---|---|
| `lat` | query |  | number | Latitude of the property location. Accepted range is -90 to +90. Required if address is not provided.; format double |
| `lng` | query |  | number | Longitude of the property location. Accepted range is -180 to +180. Required if address is not provided.; format double |
| `address` | query |  | string | Full address of the property. Either address or both lat and lng must be provided. |
| `currency` | query | Y | string | Currency code for the revenue estimates (e.g. USD, EUR, GBP, INR, AUD). |
| `bedroom_category` | query | Y | integer | Number of bedrooms for the property. Use 0 for studio. |
| `monthly` | query |  | boolean | When set to true, the response includes a MonthlyBreakup object with month-by-month KPIs. Defaults to false. |
| `filters` | query |  | string | A JSON string containing filter criteria to narrow comparable listings. Pass as a JSON string, not a JSON object. Supported keys: - **pool** (0 or 1) — Filter by pool availability - **hottub** (0 or 1) — Filter by hot tub availability - **ratings** ({"gt": n, "lt": n}) — Filter by listing ratings ra |
| `X-API-Key` | header | Y | string | Your Revenue Estimator API key. This is different from the Customer API key. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `KPIsByBedroomCategory` | object | KPI metrics for the requested bedroom category. Each key represents the bedroom count passed in the `bedroom_category` parameter. For bedroom categories >= 5, if there are not enough listings, data from +/-1 bedroom cate |

Errors: `400`, `401`, `429`, `500`, `502`

