# PriceLabs REST API: neighborhoodData

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/neighborhood_data`

Get neighborhood data for a listing

> Get neighborhood data for your listing with all stats shown on the Neighborhood Tab.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query | Y | string |  |
| `pms` | query | Y | string |  |
| `use_default_data` | query |  | string | When `true` uses default data source instead of source selected on the UI.; enum: `true`, `false`; default false |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | object | Neighborhood data payload from the pricing engine (`neighborhood_json`). |
| `data.Listings Used` | integer | Total number of listings considered in this neighborhood. |
| `data.currency` | string | Listing currency. |
| `data.lat` | number | Listing latitude.; format double |
| `data.lng` | number | Listing longitude.; format double |
| `data.source` | string | Data source — Airbnb or VRBO as indicated in the response (e.g. `airbnb`, `vrbo`). |
| `data.Neighborhood Data Source` | string | Source selected on the ND tab under "Select CompSets for comparison". Can be `Nearby Listings` or `Market Dashboard: <dashboard name>`. |
| `data.Future Percentile Prices` | object | Per bedroom category (key), percentile market prices for each stay date. Uses Category (key), X_values (dates), Y_values (one array per label), and Labels. |
| `data.Future Percentile Prices.Category` | object | Keyed by bedroom category — `"-1"` room, `"0"` studio, `"1"` 1BR, and so on — or compset name when using a Market Dashboard custom compset. |
| `data.Future Percentile Prices.Labels` | array[string] | 25th Percentile, 50th Percentile, 75th Percentile, Median Booked Price, 90th Percentile. |
| `data.Future Occ/New/Canc` | object | Per bedroom category, future occupancy/pickup plus same-time-last-year occupancy, pickup, and final occupancy. |
| `data.Future Occ/New/Canc.Category` | object | Keyed by bedroom category or compset name (same structure as Future Percentile Prices). |
| `data.Future Occ/New/Canc.Labels` | array[string] | Occupancy, New Bookings (last 7 days), Canceled Bookings (last 30 days), Occupancy_LY, Occupancy_STLY, New_Bookings_STLY. |
| `data.Summary Table Base Price` | object | Per bedroom category, percentile prices for the past 180 and future 180 days. |
| `data.Summary Table Base Price.Category` | object | Keyed by bedroom category or compset name. |
| `data.Summary Table Base Price.Labels` | array[string] | 25th/50th/75th/90th Percentile Price. For Market Dashboard sources, may also include Median Listed Price (USD), Median Booked Nightly Price (USD), Median Booked Weekly Price (USD), Median Booked Monthly Price (USD), Medi |
| `data.Market KPI` | object | Aggregated market KPIs at monthly level, plus last 365 and 730 days. Has Category (keyed by bedroom type) and Labels. |
| `data.Market KPI.Category` | object | Keyed by bedroom type; each entry has X_values (time periods) and Y_values (2D array with 5 KPI rows aligned to X_values). |
| `data.Market KPI.Labels` | array[string] | Total Available Days (days listings were available), Booking Window (median days between booking and first stay), LOS (nights per reservation), Revenue (total booking revenue), Total Booked Days (total booked days across |
| `status` | string |  |

Errors: `400`, `401`, `404`, `500`

