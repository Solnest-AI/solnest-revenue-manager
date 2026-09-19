# Every PriceLabs operation, what owns it, and whether it works here

43 published operations (41 Customer API + 2 Revenue Estimator). Probed live against
**one live 1-bedroom listing** (Hospitable, CAD) on **2026-09-18** with
`python3 tools/pricelabs_endpoint_probe.py`. Re-run it after any PriceLabs change:
it is the schema-drift alarm.

`Step` is the runbook step that owns the call. `Ref` is the file under
`references/pricelabs-api/` with the full parameter and response detail. Read the one
area you need, never the directory.

**Writes are never fired by the probe.** They are listed so the surface is complete.

## CATALOG AND BOUNDS

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/listings` | Every listing with base/min/max, currency, lat/lng, push_enabled. | 3 / 4 | [listings.md](pricelabs-api/listings.md) | 200 · listings=8 9,356B |
| `GET /v1/listings_minimal` | Id + name only. Use when you just need to resolve a name. | 0 | [listings.md](pricelabs-api/listings.md) | 200 · listings=8 5,082B |
| `GET /v1/listings/{id}` | One listing's full record. | 4 | [listings.md](pricelabs-api/listings.md) | 200 · listings=1 1,190B |
| `GET /v1/listing_metrics` | Occupancy curve forward AND trailing, MPI, RevPAR vs STLY, floor-pinned %. | 4 / 6 | [listings.md](pricelabs-api/listings.md) | 200 · data=2 keys 8,042B |
| `GET /v1/fetch_rate_plans` | Channel rate plans, where the PMS exposes them. | 4 | [prices.md](pricelabs-api/prices.md) | 200 · rate_plans=4 keys 112B |
| `POST /v1/listings` | WRITE base/min/max/tags AND push_enabled. | 8 | [listings.md](pricelabs-api/listings.md) | **WRITE, not fired** |
| `POST /v1/add_listing_data` | WRITE listing metadata held by PriceLabs. | 8 | [listings.md](pricelabs-api/listings.md) | **WRITE, not fired** |

## THE PRICE CURVE

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `POST /v1/listing_prices` | The forward ASK curve. Always through reduce_prices.py. | 4.0 | [prices.md](pricelabs-api/prices.md) | 200 · 1 11,323B |
| `GET /v1/listings/{id}/overrides` | Active per-date overrides. Through reduce_overrides.py. | 4 | [datespecificoverridesdso.md](pricelabs-api/datespecificoverridesdso.md) | 200 · overrides=166 28,950B |
| `POST /v1/listings/{id}/overrides` | WRITE per-date price/min-stay. Guest facing. | 8 | [datespecificoverridesdso.md](pricelabs-api/datespecificoverridesdso.md) | **WRITE, not fired** |
| `DELETE /v1/listings/{id}/overrides` | WRITE revert dates to algorithmic pricing. | 8 | [datespecificoverridesdso.md](pricelabs-api/datespecificoverridesdso.md) | **WRITE, not fired** |
| `POST /v1/refresh_listing` | WRITE recompute + re-push. 3/listing/24h. | 8 | [prices.md](pricelabs-api/prices.md) | **WRITE, not fired** |

## THE PRICING RULES (the customization stack)

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/customizations/listing` | The six rules. MUST pass toggled_on=false. | 4c | [customizations.md](pricelabs-api/customizations.md) | 200 · customizations=6 keys 1,154B |
| `GET /v1/customization_profiles` | Shared min-stay / pricing / CICO profiles, account-level objects. | 4c | [customizations.md](pricelabs-api/customizations.md) | 200 · profiles=3 keys 221B |
| `GET /v1/customizations/account` | Account-level defaults every listing inherits. | 4c | [customizations.md](pricelabs-api/customizations.md) | 200 · customizations=0 keys 21B |
| `GET /v1/customizations/group` | Group-level rules. | 4c | [customizations.md](pricelabs-api/customizations.md) | 200 · customizations=0 keys 21B |
| `POST /v1/customizations/listing` | WRITE the rules. Read-modify-write the FULL object. | 8 | [customizations.md](pricelabs-api/customizations.md) | **WRITE, not fired** |
| `POST /v1/customizations/group` | WRITE portfolio: every listing in the group. | 8 | [customizations.md](pricelabs-api/customizations.md) | **WRITE, not fired** |
| `POST /v1/customizations/account` | WRITE portfolio: the entire account. | 8 | [customizations.md](pricelabs-api/customizations.md) | **WRITE, not fired** |

## THE VENDOR'S OWN DIAGNOSIS

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/actions` | PriceLabs' issue list per listing. Read BEFORE forming your own. | 4c / 6 | [actions.md](pricelabs-api/actions.md) | 200 · 5 2,352B |
| `GET /v1/nudges/available` | Pending base/min suggestions with reason and expiry. | 4c / 7 | [nudges.md](pricelabs-api/nudges.md) | 200 · nudges=0 13B |
| `POST /v1/nudges/accept` | WRITE the narrowest write in the API. | 8 | [nudges.md](pricelabs-api/nudges.md) | **WRITE, not fired** |
| `POST /v1/logs` | Change history incl. changes made outside this skill. log_type REQUIRED. | 3 / 7 | [logs.md](pricelabs-api/logs.md) | 200 · data=5 2,482B |

## MARKET AND COMPS

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/neighborhood_data` | The comp engine. Through reduce_neighborhood.py. | 4a | [neighborhooddata.md](pricelabs-api/neighborhooddata.md) | 200 · data=11 keys 172,749B |
| `GET /v1/revenue/estimator` | Revenue estimate by lat/lng + bedroom count. | 4.8 | [revenueestimatorversion1.md](pricelabs-api/revenueestimatorversion1.md) | **403** · {'code': 'API_KEY_UNAUTHORIZED', 'message': 'The api_key supplied is not authori |
| `GET /v2/revenue/estimator` | As v1, plus filters. | 4.8 | [revenueestimatorversion2.md](pricelabs-api/revenueestimatorversion2.md) | **403** · {'code': 'API_KEY_UNAUTHORIZED', 'message': 'The api_key supplied is not authori |

## DEMAND AND HISTORY

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/reservation_data` | Booking history. IGNORES listing_id: filter client-side. | 4 | [reservations.md](pricelabs-api/reservations.md) | 200 · data=5 2,440B |
| `POST /v1/bookings_report` | Portfolio reservations in one paginated call. | 4 | [bookingsreport.md](pricelabs-api/bookingsreport.md) | 200 · data=2 keys 4,377B |
| `POST /v1/create_reservations` | WRITE invents booking records. Never. | - | [reservations.md](pricelabs-api/reservations.md) | **WRITE, not fired** |

## RANKING AND VISIBILITY

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/listing_optimizer/summary` | Which listings have an optimizer report. | 4 | [listingoptimizer.md](pricelabs-api/listingoptimizer.md) | 200 · data=2 keys 53B |
| `GET /v1/listing_optimizer/report` | Rank, page position, price by guest-count/LOS. | 4 | [listingoptimizer.md](pricelabs-api/listingoptimizer.md) | **400** · optimizer ids are NUMERIC and come from lo_summary, not the PMS uuid | listing_i |
| `GET /v1/listing_optimizer/ranking` | 90-day rank history. | 4 | [listingoptimizer.md](pricelabs-api/listingoptimizer.md) | **400** · optimizer ids are NUMERIC and come from lo_summary, not the PMS uuid | listing_i |

## SCOPE: GROUPS AND MAPPINGS

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/groups` | Account groups. | 0 | [groups.md](pricelabs-api/groups.md) | 200 · groups=1 71B |
| `GET /v1/group_listings` | Members of a group. | 0 | [groups.md](pricelabs-api/groups.md) | 200 · listings=0 143B |
| `GET /v1/group_overrides` | Group-level per-date overrides. | 4 | [groups.md](pricelabs-api/groups.md) | 200 · overrides=0 71B |
| `POST /v1/groups` | WRITE creates an account-level group. | - | [groups.md](pricelabs-api/groups.md) | **WRITE, not fired** |
| `POST /v1/group_overrides` | WRITE portfolio. | 8 | [groups.md](pricelabs-api/groups.md) | **WRITE, not fired** |
| `DELETE /v1/group_overrides` | WRITE portfolio. | 8 | [groups.md](pricelabs-api/groups.md) | **WRITE, not fired** |
| `POST /v1/mappings/map` | WRITE re-parents channel listings. | - | [mappings.md](pricelabs-api/mappings.md) | **WRITE, not fired** |
| `POST /v1/mappings/unmap` | WRITE detaches a mapped group. | - | [mappings.md](pricelabs-api/mappings.md) | **WRITE, not fired** |

## REPORTING

| Operation | Answers | Step | Ref | Live |
|---|---|---|---|---|
| `GET /v1/report_builder/templates` | 16 prebuilt report templates. | 7.5 | [reportbuilder.md](pricelabs-api/reportbuilder.md) | 200 · templates=16 4,775B |
| `POST /v1/report_builder/data` | Queue a report. template_id is templateId from templates. | 7.5 | [reportbuilder.md](pricelabs-api/reportbuilder.md) | 200 · 132B |
| `POST /v1/report_builder/poll` | Collect the queued report. | 7.5 | [reportbuilder.md](pricelabs-api/reportbuilder.md) | 200 · data=2 keys 4,592B |
## What the probe found that changes how you call these

**25 of 29 reads returned 200.** The four that did not are account state, not bugs, and a
client on a different plan will see different answers. Re-probe per account at Step 0 rather
than assuming this list.

| Not available here | Status | Why |
|---|---|---|
| `GET /v1/revenue/estimator` (v1 and v2) | `403 API_KEY_UNAUTHORIZED` | Separately licensed product. The key is valid; the service is not on the plan. Do not treat a 403 here as an auth failure. |
| `GET /v1/listing_optimizer/report` | `400` | Downstream of the summary: `has_optimizer_report: false`, `listings: []`. |
| `GET /v1/listing_optimizer/ranking` | `400` | Same. |

**The Listing Optimizer uses a different id namespace.** Both endpoints reject the PriceLabs
uuid with `listing_id must be a non-empty digit string`. The numeric id comes from
`listing_optimizer/summary`, so always call summary first and take the id from it. Never pass
the PMS uuid.

**Correct-but-empty is not failure.** On this account `groups` returns one group
(one empty group), so `group_listings`, `group_overrides` and
`customizations/group` all return 200 with zero rows. A reducer must distinguish "no group
data" from "the group call failed", exactly as `reduce_overrides.py` distinguishes `dates=0`
from exit 2.

**`report_builder` ids are `templateId`, not `id`.** The templates list returns `templateId`,
the data call takes `template_id`. Sixteen prebuilt templates exist on this account, including
`Revenue On The Books` (118) and `Leaderboard` (119). Step 7.5 hand-builds a workbook today.

**`POST /v1/logs` requires `log_type`** (`listing` | `group` | `account`). An empty body is a
400. Filtering to one listing also needs `listings: [{listing_id, pms}]`.
