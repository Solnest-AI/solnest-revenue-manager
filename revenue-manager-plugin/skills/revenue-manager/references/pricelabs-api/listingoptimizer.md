# PriceLabs REST API: listingOptimizer

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/listing_optimizer/ranking`

Get Listing Optimizer ranking for a listing

> Returns competitive ranking data for a single Airbnb listing: current search-result rankings by guest count and length-of-stay segments, the number of competing listings in the neighborhood, and up to 90 days of ranking history.
> 
> Requires `listing_id` as a query parameter. `pms_name`, `guest_count`, `los`, and `history_start_date` remain optional query parameters.
> 
> Use `guest_count` and `los` to narrow results to a specific segment. Use `history_start_date` to control how far back the ranking history goes (defaults to 90 days ago; cannot be set earlier than 90 days ago).

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query | Y | string | Listing ID of the Airbnb listing. |
| `pms_name` | query |  | string | PMS name. Defaults to `airbnb`. |
| `guest_count` | query |  | integer | Filter ranking segments to this guest count only. |
| `los` | query |  | string | Filter ranking segments to this length of stay only. |
| `history_start_date` | query |  | string | Start date for ranking history (YYYY-MM-DD). Cannot be earlier than 90 days ago. Defaults to 90 days ago.; format date |
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | object | Listing Optimizer ranking data for the listing. |
| `data.listing_id` | string | Unique listing ID. |
| `data.pms_name` | string | PMS the listing belongs to. |
| `data.neighborhood_count` | integer|null | Number of competing listings in the listing's neighborhood. `null` if unavailable. |
| `data.current_rankings` | oneOf | Current search-result ranking data broken into guest-count × LOS segments. `null` if ranking data is unavailable. |
| `data.ranking_history` | array|null | Historical ranking data by (guest_count, LOS) segment. `null` if history is unavailable. |

Errors: `400`, `401`, `404`


## `GET /v1/listing_optimizer/report`

Get Listing Optimizer report for a listing

> Returns full Listing Optimizer details for a single Airbnb listing: category letter grades, score breakdowns, improvement tips, and previous-run grades for comparison.
> 
> Requires `listing_id` as a query parameter. Optionally accepts `pms_name` as a query parameter (defaults to `airbnb`). If the account has not paid for Optimizer access for this listing, `payment_restricted: true` is returned and score data is omitted.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query | Y | string | Listing ID of the Airbnb listing. |
| `pms_name` | query |  | string | PMS name. Defaults to `airbnb`. |
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | object | Listing Optimizer report for the listing. |
| `data.listing_id` | string | Unique listing ID. |
| `data.pms_name` | string | PMS the listing belongs to. |
| `data.overall_score` | number|null | Overall Listing Optimizer score (0–10, two decimal places). `null` if not yet scored.; format double |
| `data.payment_restricted` | boolean | Present and `true` when the account does not have paid Optimizer access for this listing. When `true`, `scores` and `previous_scores` are omitted. |
| `data.scores` | object | Category-level scores, keyed by category: `overall_score` (the underlying 0–100 score) and one `OptimizerCategoryScore` per category — `listing_title`, `listing_description`, `image_score`, `amenities`, `review_count`, ` |
| `data.scores.overall_score` | number | Underlying 0–100 score behind the top-level `overall_score` letter-grade breakdown.; format double |
| `data.scores.listing_title` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.listing_title.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.listing_title.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.listing_title.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.listing_description` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.listing_description.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.listing_description.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.listing_description.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.image_score` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.image_score.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.image_score.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.image_score.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.amenities` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.amenities.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.amenities.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.amenities.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.review_count` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.review_count.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.review_count.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.review_count.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.review_summary` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.review_summary.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.review_summary.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.review_summary.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.star_rating` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.star_rating.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.star_rating.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.star_rating.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.guest_favorite` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.guest_favorite.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.guest_favorite.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.guest_favorite.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.scores.consistency_score` | object | Score and guidance for a single Listing Optimizer category from the latest analysis run. |
| `data.scores.consistency_score.score` | string | Letter grade for this category (e.g. `A`, `B`, `C`). |
| `data.scores.consistency_score.improvements` | string | Actionable tip to improve this category's score. Categories surface either this or `description`, not both. |
| `data.scores.consistency_score.description` | string | Explanatory note about this category's score, for categories that don't have an actionable tip. Categories surface either this or `improvements`, not both. |
| `data.previous_scores` | oneOf | Scores from the previous analysis run, for comparison. `null` if no prior run exists. Present only when `payment_restricted` is absent or `false`. |

Errors: `400`, `401`, `404`, `422`


## `GET /v1/listing_optimizer/summary`

Get Listing Optimizer summary

> Returns Listing Optimizer scores for all active Airbnb listings in the account. Each entry includes the overall score, status, and basic listing info. If the account does not have an optimizer report, `has_optimizer_report` will be `false` and `listings` will be empty.
> 
> Use this endpoint first to get a portfolio-wide overview, then call `/v1/listing_optimizer/report` for a detailed breakdown of individual listings.
> 
> Supports optional `subscribed`, `status`, and `listing_ids` query parameters to filter the returned listings.

| param | in | req | type | notes |
|---|---|---|---|---|
| `subscribed` | query |  | boolean | Filter to listings with (`true`) or without (`false`) an active PriceLabs subscription. |
| `status` | query |  | string | Filter to listings with this optimizer status. One of `pending`, `processing`, `completed`, `error`, `delisted`, `archived`, `deleted`.; enum: `pending`, `processing`, `completed`, `error`, `delisted`, `archived`, `deleted` |
| `listing_ids` | query |  | array[integer] | Filter to specific listing IDs. Pass as repeated bracketed params, e.g. `listing_ids[]=1&listing_ids[]=2`. |
| `X-API-Key` | header | Y | string | API key for Customer API authentication. |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `data` | object |  |
| `data.has_optimizer_report` | boolean | Whether an Optimizer report exists for this account. |
| `data.listings` | array[object] | Optimizer summary row for each active listing. |
| `data.listings[].listing_id` | string | Unique listing ID. |
| `data.listings[].pms_name` | string | PMS the listing belongs to. |
| `data.listings[].listing_name` | string | Listing title, or listing_id if no title is set. |
| `data.listings[].status` | string | Current optimizer status. One of `pending`, `processing`, `completed`, `error`, `delisted`, `archived`, `deleted`. |
| `data.listings[].analyzed_at` | string|null | ISO 8601 timestamp of the last analysis run. `null` if not yet analyzed. |
| `data.listings[].overall_score` | number|null | Overall Listing Optimizer score (0–10, two decimal places). `null` if not yet scored.; format double |
| `data.listings[].city` | string|null | City where the listing is located. |
| `data.listings[].state` | string|null | State or region where the listing is located. |
| `data.listings[].subscribed` | boolean | Whether the listing has an active PriceLabs subscription. |
| `data.listings[].subscription_end` | string|null | Date (YYYY-MM-DD) when the subscription ends. `null` if not applicable. |
| `data.listings[].can_rerun` | boolean | Whether the listing can be re-analyzed now. |
| `data.listings[].manual_reruns_remaining` | integer|null | Number of manual re-runs remaining this month. |

Errors: `401`

