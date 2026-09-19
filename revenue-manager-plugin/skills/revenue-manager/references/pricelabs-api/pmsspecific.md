# PriceLabs REST API: pmsSpecific

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `POST /v1/add_listing_data`

Import newly added listings from PMS

> Use this API call to pull new listings that you have added in your PMS. Make sure the `listing_id` in the body is for an existing listing that was previously added to your PriceLabs account.
> 
> > **Note:** This API call works only for `bookingsync` and `redawning` PMS.

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `listing_id` | Y | string | Listing ID of an existing listing in your PriceLabs account |
| `pms_name` | Y | string | PMS name of the listing |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `success` | string | A success message (e.g. "Successfully connected with BookingSync") |
| `lat_lng_listings` | array[object] | An array of listing IDs with missing latitude or longitude. Update the latitude and longitude information in BookingSync and try this API call again to add these listing IDs in your PriceLabs account. |
| `listing_ids` | array[string] | An array of listing IDs that have been successfully added in the PriceLabs account. Head over to your PriceLabs account to review prices for these listings. |

Errors: `400`

