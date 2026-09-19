# PriceLabs REST API reference (index)

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds every file here
> from the published OpenAPI 3.1 specs. Last generated 2026-09-18.
> **43 operations.** Raw specs archived in `docs/pricelabs/`.

Auth on every call: `X-API-Key` header **and** a browser-like `User-Agent`.
A bare client gets a WAF 403 that reads like an auth failure.

**Read `../pricelabs-gotchas.md` before writing any client.** The spec does not carry
the measured traps (offset pagination, decaying override history, per-account payload
shapes), and every one of them has already cost real money.


## Customer API v1.0.0  (base `https://api.pricelabs.co`)

- **[`actions`](actions.md)** (1 ops): `GET /v1/actions`
- **[`bookingsReport`](bookingsreport.md)** (1 ops): `POST /v1/bookings_report`
- **[`customizations`](customizations.md)** (7 ops): `GET /v1/customization_profiles`, `GET /v1/customizations/account`, `POST /v1/customizations/account`, `GET /v1/customizations/group`, `POST /v1/customizations/group`, `GET /v1/customizations/listing`, `POST /v1/customizations/listing`
- **[`dateSpecificOverridesDso`](datespecificoverridesdso.md)** (6 ops): `GET /v1/group_overrides`, `POST /v1/group_overrides`, `DELETE /v1/group_overrides`, `GET /v1/listings/{listing_id}/overrides`, `POST /v1/listings/{listing_id}/overrides`, `DELETE /v1/listings/{listing_id}/overrides`
- **[`groups`](groups.md)** (3 ops): `GET /v1/group_listings`, `GET /v1/groups`, `POST /v1/groups`
- **[`listingOptimizer`](listingoptimizer.md)** (3 ops): `GET /v1/listing_optimizer/ranking`, `GET /v1/listing_optimizer/report`, `GET /v1/listing_optimizer/summary`
- **[`listings`](listings.md)** (5 ops): `GET /v1/listing_metrics`, `GET /v1/listings`, `POST /v1/listings`, `GET /v1/listings/{listing_id}`, `GET /v1/listings_minimal`
- **[`logs`](logs.md)** (1 ops): `POST /v1/logs`
- **[`mappings`](mappings.md)** (2 ops): `POST /v1/mappings/map`, `POST /v1/mappings/unmap`
- **[`neighborhoodData`](neighborhooddata.md)** (1 ops): `GET /v1/neighborhood_data`
- **[`nudges`](nudges.md)** (2 ops): `POST /v1/nudges/accept`, `GET /v1/nudges/available`
- **[`pmsSpecific`](pmsspecific.md)** (1 ops): `POST /v1/add_listing_data`
- **[`prices`](prices.md)** (3 ops): `GET /v1/fetch_rate_plans`, `POST /v1/listing_prices`, `POST /v1/refresh_listing`
- **[`reportBuilder`](reportbuilder.md)** (3 ops): `POST /v1/report_builder/data`, `POST /v1/report_builder/poll`, `GET /v1/report_builder/templates`
- **[`reservations`](reservations.md)** (2 ops): `POST /v1/create_reservations`, `GET /v1/reservation_data`

## Revenue Estimator API v1.0.0  (base `https://api.pricelabs.co`)

- **[`revenueEstimatorVersion1`](revenueestimatorversion1.md)** (1 ops): `GET /v1/revenue/estimator`
- **[`revenueEstimatorVersion2`](revenueestimatorversion2.md)** (1 ops): `GET /v2/revenue/estimator`
