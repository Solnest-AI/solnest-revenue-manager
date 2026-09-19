# PriceLabs REST API: customizations

> GENERATED. `python3 tools/pricelabs_spec_report.py --fetch` rebuilds it.
> Auth: header `X-API-Key`, plus a browser-like `User-Agent` (bare clients get a WAF 403).
> Measured traps the spec does not carry: `../pricelabs-gotchas.md`.


## `GET /v1/customization_profiles`

List customization profiles (discovery)

> Read-only discovery endpoint for the account's customization profiles. Use it to look up
> the exact `minstay_profile_id` / `pricing_profile_id` / `checkincheckout_profile_id`
> values that `custom_seasonal_profile` season writes accept — the ids returned here are
> exactly the set a write will validate against (same account-ownership rule).
> 
> Returns all three profile types grouped by type; filter with `profile_type`, `archived`,
> or look up a single profile by exact `name` (requires `profile_type`; at most one match —
> profile names are unique per account and type). A name with no match returns
> `404 ERR-PROFILE-NOT-FOUND`; the response is identical for nonexistent and not-owned
> names. Entries expose only `id`, `name` and `archived` — not the profile's contents.

| param | in | req | type | notes |
|---|---|---|---|---|
| `profile_type` | query |  | string | Return only this profile type; omit for all three.; enum: `minstay`, `pricing`, `checkincheckout` |
| `archived` | query |  | boolean | Filter by archived state. `false` also includes legacy profiles that never set the flag. Omit to return both archived and unarchived profiles. |
| `name` | query |  | string | Exact-match name lookup. Requires `profile_type`. Returns at most one profile; no match returns 404 ERR-PROFILE-NOT-FOUND. |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `profiles` | object | Profiles grouped by type. Types filtered out by `profile_type` are omitted; a type with no profiles is an empty array. |
| `profiles.minstay` | array[object] |  |
| `profiles.minstay[].id` | integer | The profile id to use in `custom_seasonal_profile` season writes. |
| `profiles.minstay[].name` | string | Display name (unique per account and profile type). |
| `profiles.minstay[].archived` | boolean | Whether the profile is archived (legacy `NULL` reads as `false`). |
| `profiles.pricing` | array[object] |  |
| `profiles.pricing[].id` | integer | The profile id to use in `custom_seasonal_profile` season writes. |
| `profiles.pricing[].name` | string | Display name (unique per account and profile type). |
| `profiles.pricing[].archived` | boolean | Whether the profile is archived (legacy `NULL` reads as `false`). |
| `profiles.checkincheckout` | array[object] |  |
| `profiles.checkincheckout[].id` | integer | The profile id to use in `custom_seasonal_profile` season writes. |
| `profiles.checkincheckout[].name` | string | Display name (unique per account and profile type). |
| `profiles.checkincheckout[].archived` | boolean | Whether the profile is archived (legacy `NULL` reads as `false`). |

Errors: `400`, `401`, `404`


## `GET /v1/customizations/account`

Read account-level (pms) customizations

> Returns the account/pms's OWN-level customization values (write-body-shaped). By default
> only toggled-ON customizations are returned; pass `toggled_on=false` to also include
> toggled-off ones. `?customizations=` filters. 404 only if the account/pms itself is not
> found; an account with no customizations set returns 200 with an empty `customizations` map.

| param | in | req | type | notes |
|---|---|---|---|---|
| `pms_name` | query | Y | string | PMS name (account-level). |
| `customizations` | query |  | string | Comma-separated spec keys to return; omit to return all supported. |
| `toggled_on` | query |  | boolean | When true (default), only customizations whose toggle is ON are returned. Pass false to also include toggled-off customizations with their full data packs.; default True |
| `X-API-Key` | header | Y | string |  |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `customizations` | object | Map of customization name → its settings. Include any one or more of the customizations below in a single request. Unknown or unsupported customization names are rejected. |
| `customizations.seasonality` | object | `seasonality` customization — how strongly prices follow the market's seasonal demand curve. (Spec key: `seasonality`.) Turning the toggle off keeps the stored value (only the toggle flips). |
| `customizations.seasonality.seasonality_customization_on` | boolean |  |
| `customizations.seasonality.seasonality_type` | string | Required when the toggle is on. UI label in brackets. Each value follows the market's seasonal demand curve more closely than the one above it. - `no_seasonality` (No Seasonality) — flattens the seasonal curve entirely.  |
| `customizations.last_minute_prices` | object | `last_minute_prices` customization — adjust prices as check-in approaches. (Spec key: `last_minute_prices`.) Field requirements depend on `last_min_factor_type`: - `none`, `recommended`, `conservative`, `aggressive`: onl |
| `customizations.last_minute_prices.last_min_factor_on` | boolean |  |
| `customizations.last_minute_prices.last_min_factor_type` | string | Required when the toggle is on. UI label in brackets. - `none` (No last minute adjustment) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — discount derived from  |
| `customizations.last_minute_prices.last_min_factor_value` | number | Signed adjustment. linear/linear_gradual: percentage, discount magnitude 0-75 / premium magnitude 0-500. fixed: flat price. Required for linear/linear_gradual/fixed.; format double |
| `customizations.last_minute_prices.last_min_factor_dfd` | integer | Days from check-in the adjustment starts (1-90). Required for linear/linear_gradual/fixed.; min 1; max 90 |
| `customizations.day_of_week_adjustment` | object | `day_of_week_adjustment` customization — a signed percentage adjustment per weekday (negative = discount, positive = premium; each between -75 and 1000). Days omitted from the request default to 0 (no adjustment that day |
| `customizations.day_of_week_adjustment.dow_factor_on` | boolean |  |
| `customizations.day_of_week_adjustment.dow_factor_value_mon` | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_tue` | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_wed` | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_thu` | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_fri` | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sat` | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sun` | integer |  |
| `customizations.far_out_premium` | object | `far_out_premium` customization — adjust prices for far-out dates. Field requirements depend on `far_out_premium_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — other fields are   auto-fille |
| `customizations.far_out_premium.far_out_premium_on` | boolean |  |
| `customizations.far_out_premium.far_out_premium_type` | string | Required when the toggle is on. UI label in brackets. Note this enum uses `fix`, not `fixed` as `last_min_factor_type` does, and has no `linear_gradual`. - `none` (No Far Out Premium) — suppresses the adjustment, unlike  |
| `customizations.far_out_premium.far_out_premium_value` | integer | Signed percentage (-30..500). Required for linear/fix. |
| `customizations.far_out_premium.far_out_premium_start` | integer | Days from today where the adjustment reaches its maximum (1-999). Required for linear/fix.; min 1; max 999 |
| `customizations.far_out_premium.far_out_premium_step` | integer | Step size in days (1-999). Required for linear; ignored for fix (always 1).; min 1; max 999 |
| `customizations.demand_factor` | object | `demand_factor` customization — how strongly prices react to market demand. `hotel_compset_type` and `hotel_wt` require the hotel compset & weights feature (admin-granted): without it, writes including them are rejected  |
| `customizations.demand_factor.tone_demand_factor_on` | boolean |  |
| `customizations.demand_factor.tone_demand_factor` | string | Required when the toggle is on. UI label in brackets. Each value moves prices further in response to a change in demand than the one above it. Note the "off" member here is the space-separated `no demand factor`, not `no |
| `customizations.demand_factor.hotel_compset_type` | string | Hotel compset mode (feature-gated). UI label in brackets. - `recommended` (PriceLabs Default) — PriceLabs picks the hotel comp set. - `custom` (Selected in Hotel Data tab) — uses the comp set chosen there. fully_hotel +  |
| `customizations.demand_factor.hotel_wt` | string | Hotel vs short-term-rental weighting (feature-gated). UI label in brackets. Each value weights the comp set further toward hotels and away from short-term rentals than the one above it. - `fully_str` (Fully Short-Term Re |
| `customizations.custom_seasonal_profile` | object | `custom_seasonal_profile` customization — define seasons with their own price settings and (optionally) min-stay / pricing / check-in-check-out profiles. (Spec key: `custom_seasonal_profile`.)  Structure: a toggle plus a |
| `customizations.custom_seasonal_profile.custom_seasonal_profile_on` | boolean |  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile` | object | Required when the toggle is on. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type` | string | How repeating-season prices are interpreted. Required when `seasons` is non-empty. - `percentage` — the season's prices are a signed adjustment to the base price. - `fixed` — the season's prices are absolute currency amo |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.seasons` | array[object] | Seasons that repeat every year. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type_non_repeating` | string | Required when `non_repeating_seasons` is non-empty.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.non_repeating_seasons` | array[object] | One-off seasons for specific calendar dates (feature-gated). |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_baseprice` | string | Inherit season base prices from the group/account level (feature-gated; listing/group level only). Writes accept `"1"`/`"0"` or `true`/`false`; reads return `"1"`/`"0"`.; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_minstay` | string | Inherit season min-stay profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_cico` | string | Inherit season check-in/check-out profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_priceprofile` | string | Inherit season pricing profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |

Errors: `400`, `401`, `403`, `404`


## `POST /v1/customizations/account`

Create / update account-level (pms) customizations

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `pms_name` | Y | string |  |
| `customizations` | Y | object | Map of customization name → its settings. Include any one or more of the customizations below in a single request. Unknown or unsupported customization names are rejected. |
| `customizations.seasonality` |  | object | `seasonality` customization — how strongly prices follow the market's seasonal demand curve. (Spec key: `seasonality`.) Turning the toggle off keeps the stored value (only the toggle flips). |
| `customizations.seasonality.seasonality_customization_on` | Y | boolean |  |
| `customizations.seasonality.seasonality_type` |  | string | Required when the toggle is on. UI label in brackets. Each value follows the market's seasonal demand curve more closely than the one above it. - `no_seasonality` (No Seasonality) — flattens the seasonal curve entirely. - `conservative` (Conservative) - `moderately_conservative` (Moderately Conserva |
| `customizations.last_minute_prices` |  | object | `last_minute_prices` customization — adjust prices as check-in approaches. (Spec key: `last_minute_prices`.) Field requirements depend on `last_min_factor_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — value/dfd are   auto-filled (anything sent with them is ignored). - |
| `customizations.last_minute_prices.last_min_factor_on` | Y | boolean |  |
| `customizations.last_minute_prices.last_min_factor_type` |  | string | Required when the toggle is on. UI label in brackets. - `none` (No last minute adjustment) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — discount derived from live market data, tapering to 0% by the end of the window. - `conservative` (Mar |
| `customizations.last_minute_prices.last_min_factor_value` |  | number | Signed adjustment. linear/linear_gradual: percentage, discount magnitude 0-75 / premium magnitude 0-500. fixed: flat price. Required for linear/linear_gradual/fixed.; format double |
| `customizations.last_minute_prices.last_min_factor_dfd` |  | integer | Days from check-in the adjustment starts (1-90). Required for linear/linear_gradual/fixed.; min 1; max 90 |
| `customizations.day_of_week_adjustment` |  | object | `day_of_week_adjustment` customization — a signed percentage adjustment per weekday (negative = discount, positive = premium; each between -75 and 1000). Days omitted from the request default to 0 (no adjustment that day); at least one day must be non-empty. Turning the toggle off keeps the stored d |
| `customizations.day_of_week_adjustment.dow_factor_on` | Y | boolean |  |
| `customizations.day_of_week_adjustment.dow_factor_value_mon` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_tue` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_wed` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_thu` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_fri` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sat` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sun` |  | integer |  |
| `customizations.far_out_premium` |  | object | `far_out_premium` customization — adjust prices for far-out dates. Field requirements depend on `far_out_premium_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — other fields are   auto-filled (anything sent with them is ignored). - `linear`: `far_out_premium_value`, `fa |
| `customizations.far_out_premium.far_out_premium_on` | Y | boolean |  |
| `customizations.far_out_premium.far_out_premium_type` |  | string | Required when the toggle is on. UI label in brackets. Note this enum uses `fix`, not `fixed` as `last_min_factor_type` does, and has no `linear_gradual`. - `none` (No Far Out Premium) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — premium d |
| `customizations.far_out_premium.far_out_premium_value` |  | integer | Signed percentage (-30..500). Required for linear/fix. |
| `customizations.far_out_premium.far_out_premium_start` |  | integer | Days from today where the adjustment reaches its maximum (1-999). Required for linear/fix.; min 1; max 999 |
| `customizations.far_out_premium.far_out_premium_step` |  | integer | Step size in days (1-999). Required for linear; ignored for fix (always 1).; min 1; max 999 |
| `customizations.demand_factor` |  | object | `demand_factor` customization — how strongly prices react to market demand. `hotel_compset_type` and `hotel_wt` require the hotel compset & weights feature (admin-granted): without it, writes including them are rejected (`ERR-FEATURE-NOT-ENABLED`) and reads omit them. With the feature, send the hote |
| `customizations.demand_factor.tone_demand_factor_on` | Y | boolean |  |
| `customizations.demand_factor.tone_demand_factor` |  | string | Required when the toggle is on. UI label in brackets. Each value moves prices further in response to a change in demand than the one above it. Note the "off" member here is the space-separated `no demand factor`, not `none` as the last-minute and far-out enums use. - `no demand factor` (No demand fa |
| `customizations.demand_factor.hotel_compset_type` |  | string | Hotel compset mode (feature-gated). UI label in brackets. - `recommended` (PriceLabs Default) — PriceLabs picks the hotel comp set. - `custom` (Selected in Hotel Data tab) — uses the comp set chosen there. fully_hotel + recommended is not a valid combination.; enum: `recommended`, `custom` |
| `customizations.demand_factor.hotel_wt` |  | string | Hotel vs short-term-rental weighting (feature-gated). UI label in brackets. Each value weights the comp set further toward hotels and away from short-term rentals than the one above it. - `fully_str` (Fully Short-Term Rental) - `mostly_str` (Mostly Short-Term Rental) - `balance` (Balance) - `mostly_ |
| `customizations.custom_seasonal_profile` |  | object | `custom_seasonal_profile` customization — define seasons with their own price settings and (optionally) min-stay / pricing / check-in-check-out profiles. (Spec key: `custom_seasonal_profile`.)  Structure: a toggle plus a `custom_seasonal_profile` object holding two season arrays — `seasons` (repeat  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile_on` | Y | boolean |  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile` |  | object | Required when the toggle is on. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type` |  | string | How repeating-season prices are interpreted. Required when `seasons` is non-empty. - `percentage` — the season's prices are a signed adjustment to the base price. - `fixed` — the season's prices are absolute currency amounts.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.seasons` |  | array[object] | Seasons that repeat every year. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type_non_repeating` |  | string | Required when `non_repeating_seasons` is non-empty.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.non_repeating_seasons` |  | array[object] | One-off seasons for specific calendar dates (feature-gated). |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_baseprice` |  | string | Inherit season base prices from the group/account level (feature-gated; listing/group level only). Writes accept `"1"`/`"0"` or `true`/`false`; reads return `"1"`/`"0"`.; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_minstay` |  | string | Inherit season min-stay profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_cico` |  | string | Inherit season check-in/check-out profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_priceprofile` |  | string | Inherit season pricing profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `status` | string |  |
| `applied` | array[string] | Spec keys that were written (optional). |

Errors: `400`, `401`, `403`, `404`


## `GET /v1/customizations/group`

Read group-level customizations

> Returns the group's OWN-level customization values (write-body-shaped). By default only
> toggled-ON customizations are returned; pass `toggled_on=false` to also include toggled-off
> ones. `?customizations=` filters. 404 only if the group itself is not found.

| param | in | req | type | notes |
|---|---|---|---|---|
| `group_id` | query | Y | integer | Group id. |
| `customizations` | query |  | string | Comma-separated spec keys to return; omit to return all supported. |
| `toggled_on` | query |  | boolean | When true (default), only customizations whose toggle is ON are returned. Pass false to also include toggled-off customizations with their full data packs.; default True |
| `X-API-Key` | header | Y | string |  |

**Response 200**: identical to `GET /v1/customizations/account`.

Errors: `400`, `401`, `403`, `404`


## `POST /v1/customizations/group`

Create / update group-level customizations

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `group_id` | Y | integer |  |
| `customizations` | Y | object | Map of customization name → its settings. Include any one or more of the customizations below in a single request. Unknown or unsupported customization names are rejected. |
| `customizations.seasonality` |  | object | `seasonality` customization — how strongly prices follow the market's seasonal demand curve. (Spec key: `seasonality`.) Turning the toggle off keeps the stored value (only the toggle flips). |
| `customizations.seasonality.seasonality_customization_on` | Y | boolean |  |
| `customizations.seasonality.seasonality_type` |  | string | Required when the toggle is on. UI label in brackets. Each value follows the market's seasonal demand curve more closely than the one above it. - `no_seasonality` (No Seasonality) — flattens the seasonal curve entirely. - `conservative` (Conservative) - `moderately_conservative` (Moderately Conserva |
| `customizations.last_minute_prices` |  | object | `last_minute_prices` customization — adjust prices as check-in approaches. (Spec key: `last_minute_prices`.) Field requirements depend on `last_min_factor_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — value/dfd are   auto-filled (anything sent with them is ignored). - |
| `customizations.last_minute_prices.last_min_factor_on` | Y | boolean |  |
| `customizations.last_minute_prices.last_min_factor_type` |  | string | Required when the toggle is on. UI label in brackets. - `none` (No last minute adjustment) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — discount derived from live market data, tapering to 0% by the end of the window. - `conservative` (Mar |
| `customizations.last_minute_prices.last_min_factor_value` |  | number | Signed adjustment. linear/linear_gradual: percentage, discount magnitude 0-75 / premium magnitude 0-500. fixed: flat price. Required for linear/linear_gradual/fixed.; format double |
| `customizations.last_minute_prices.last_min_factor_dfd` |  | integer | Days from check-in the adjustment starts (1-90). Required for linear/linear_gradual/fixed.; min 1; max 90 |
| `customizations.day_of_week_adjustment` |  | object | `day_of_week_adjustment` customization — a signed percentage adjustment per weekday (negative = discount, positive = premium; each between -75 and 1000). Days omitted from the request default to 0 (no adjustment that day); at least one day must be non-empty. Turning the toggle off keeps the stored d |
| `customizations.day_of_week_adjustment.dow_factor_on` | Y | boolean |  |
| `customizations.day_of_week_adjustment.dow_factor_value_mon` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_tue` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_wed` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_thu` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_fri` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sat` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sun` |  | integer |  |
| `customizations.far_out_premium` |  | object | `far_out_premium` customization — adjust prices for far-out dates. Field requirements depend on `far_out_premium_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — other fields are   auto-filled (anything sent with them is ignored). - `linear`: `far_out_premium_value`, `fa |
| `customizations.far_out_premium.far_out_premium_on` | Y | boolean |  |
| `customizations.far_out_premium.far_out_premium_type` |  | string | Required when the toggle is on. UI label in brackets. Note this enum uses `fix`, not `fixed` as `last_min_factor_type` does, and has no `linear_gradual`. - `none` (No Far Out Premium) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — premium d |
| `customizations.far_out_premium.far_out_premium_value` |  | integer | Signed percentage (-30..500). Required for linear/fix. |
| `customizations.far_out_premium.far_out_premium_start` |  | integer | Days from today where the adjustment reaches its maximum (1-999). Required for linear/fix.; min 1; max 999 |
| `customizations.far_out_premium.far_out_premium_step` |  | integer | Step size in days (1-999). Required for linear; ignored for fix (always 1).; min 1; max 999 |
| `customizations.demand_factor` |  | object | `demand_factor` customization — how strongly prices react to market demand. `hotel_compset_type` and `hotel_wt` require the hotel compset & weights feature (admin-granted): without it, writes including them are rejected (`ERR-FEATURE-NOT-ENABLED`) and reads omit them. With the feature, send the hote |
| `customizations.demand_factor.tone_demand_factor_on` | Y | boolean |  |
| `customizations.demand_factor.tone_demand_factor` |  | string | Required when the toggle is on. UI label in brackets. Each value moves prices further in response to a change in demand than the one above it. Note the "off" member here is the space-separated `no demand factor`, not `none` as the last-minute and far-out enums use. - `no demand factor` (No demand fa |
| `customizations.demand_factor.hotel_compset_type` |  | string | Hotel compset mode (feature-gated). UI label in brackets. - `recommended` (PriceLabs Default) — PriceLabs picks the hotel comp set. - `custom` (Selected in Hotel Data tab) — uses the comp set chosen there. fully_hotel + recommended is not a valid combination.; enum: `recommended`, `custom` |
| `customizations.demand_factor.hotel_wt` |  | string | Hotel vs short-term-rental weighting (feature-gated). UI label in brackets. Each value weights the comp set further toward hotels and away from short-term rentals than the one above it. - `fully_str` (Fully Short-Term Rental) - `mostly_str` (Mostly Short-Term Rental) - `balance` (Balance) - `mostly_ |
| `customizations.custom_seasonal_profile` |  | object | `custom_seasonal_profile` customization — define seasons with their own price settings and (optionally) min-stay / pricing / check-in-check-out profiles. (Spec key: `custom_seasonal_profile`.)  Structure: a toggle plus a `custom_seasonal_profile` object holding two season arrays — `seasons` (repeat  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile_on` | Y | boolean |  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile` |  | object | Required when the toggle is on. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type` |  | string | How repeating-season prices are interpreted. Required when `seasons` is non-empty. - `percentage` — the season's prices are a signed adjustment to the base price. - `fixed` — the season's prices are absolute currency amounts.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.seasons` |  | array[object] | Seasons that repeat every year. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type_non_repeating` |  | string | Required when `non_repeating_seasons` is non-empty.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.non_repeating_seasons` |  | array[object] | One-off seasons for specific calendar dates (feature-gated). |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_baseprice` |  | string | Inherit season base prices from the group/account level (feature-gated; listing/group level only). Writes accept `"1"`/`"0"` or `true`/`false`; reads return `"1"`/`"0"`.; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_minstay` |  | string | Inherit season min-stay profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_cico` |  | string | Inherit season check-in/check-out profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_priceprofile` |  | string | Inherit season pricing profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `status` | string |  |
| `applied` | array[string] | Spec keys that were written (optional). |

Errors: `400`, `401`, `403`, `404`


## `GET /v1/customizations/listing`

Read listing-level customizations

> Returns the listing's OWN-level customization values (write-body-shaped). By default only
> toggled-ON customizations are returned; pass `toggled_on=false` to also include toggled-off
> ones with their full data packs. `?customizations=` filters the set.
> 404 only if the listing itself is not found; a listing with no customizations set returns
> 200 with an empty `customizations` map.

| param | in | req | type | notes |
|---|---|---|---|---|
| `listing_id` | query | Y | string | Listing id (listing-level). |
| `pms_name` | query | Y | string | PMS name (paired with listing_id). |
| `customizations` | query |  | string | Comma-separated spec keys to return; omit to return all supported. |
| `toggled_on` | query |  | boolean | When true (default), only customizations whose toggle is ON are returned. Pass false to also include toggled-off customizations with their full data packs.; default True |
| `X-API-Key` | header | Y | string |  |

**Response 200**: identical to `GET /v1/customizations/account`.

Errors: `400`, `401`, `403`, `404`


## `POST /v1/customizations/listing`

Create / update listing-level customizations

> Writes one or more customizations for the listing. `customizations` maps each spec key to its
> settings object. All-or-nothing: if any object is invalid the whole request is rejected and
> nothing is written. Self-serve control-panel features are auto-enabled async (no wait);
> admin-only feature-gated fields the account lacks -> `ERR-FEATURE-NOT-ENABLED` (no partial write).

| param | in | req | type | notes |
|---|---|---|---|---|
| `X-API-Key` | header | Y | string |  |

**Body** (`application/json`):

| field | req | type | notes |
|---|---|---|---|
| `listing_id` | Y | string |  |
| `pms_name` | Y | string |  |
| `customizations` | Y | object | Map of customization name → its settings. Include any one or more of the customizations below in a single request. Unknown or unsupported customization names are rejected. |
| `customizations.seasonality` |  | object | `seasonality` customization — how strongly prices follow the market's seasonal demand curve. (Spec key: `seasonality`.) Turning the toggle off keeps the stored value (only the toggle flips). |
| `customizations.seasonality.seasonality_customization_on` | Y | boolean |  |
| `customizations.seasonality.seasonality_type` |  | string | Required when the toggle is on. UI label in brackets. Each value follows the market's seasonal demand curve more closely than the one above it. - `no_seasonality` (No Seasonality) — flattens the seasonal curve entirely. - `conservative` (Conservative) - `moderately_conservative` (Moderately Conserva |
| `customizations.last_minute_prices` |  | object | `last_minute_prices` customization — adjust prices as check-in approaches. (Spec key: `last_minute_prices`.) Field requirements depend on `last_min_factor_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — value/dfd are   auto-filled (anything sent with them is ignored). - |
| `customizations.last_minute_prices.last_min_factor_on` | Y | boolean |  |
| `customizations.last_minute_prices.last_min_factor_type` |  | string | Required when the toggle is on. UI label in brackets. - `none` (No last minute adjustment) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — discount derived from live market data, tapering to 0% by the end of the window. - `conservative` (Mar |
| `customizations.last_minute_prices.last_min_factor_value` |  | number | Signed adjustment. linear/linear_gradual: percentage, discount magnitude 0-75 / premium magnitude 0-500. fixed: flat price. Required for linear/linear_gradual/fixed.; format double |
| `customizations.last_minute_prices.last_min_factor_dfd` |  | integer | Days from check-in the adjustment starts (1-90). Required for linear/linear_gradual/fixed.; min 1; max 90 |
| `customizations.day_of_week_adjustment` |  | object | `day_of_week_adjustment` customization — a signed percentage adjustment per weekday (negative = discount, positive = premium; each between -75 and 1000). Days omitted from the request default to 0 (no adjustment that day); at least one day must be non-empty. Turning the toggle off keeps the stored d |
| `customizations.day_of_week_adjustment.dow_factor_on` | Y | boolean |  |
| `customizations.day_of_week_adjustment.dow_factor_value_mon` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_tue` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_wed` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_thu` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_fri` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sat` |  | integer |  |
| `customizations.day_of_week_adjustment.dow_factor_value_sun` |  | integer |  |
| `customizations.far_out_premium` |  | object | `far_out_premium` customization — adjust prices for far-out dates. Field requirements depend on `far_out_premium_type`: - `none`, `recommended`, `conservative`, `aggressive`: only the type — other fields are   auto-filled (anything sent with them is ignored). - `linear`: `far_out_premium_value`, `fa |
| `customizations.far_out_premium.far_out_premium_on` | Y | boolean |  |
| `customizations.far_out_premium.far_out_premium_type` |  | string | Required when the toggle is on. UI label in brackets. Note this enum uses `fix`, not `fixed` as `last_min_factor_type` does, and has no `linear_gradual`. - `none` (No Far Out Premium) — suppresses the adjustment, unlike switching the toggle off. - `recommended` (Market Driven - Balanced) — premium d |
| `customizations.far_out_premium.far_out_premium_value` |  | integer | Signed percentage (-30..500). Required for linear/fix. |
| `customizations.far_out_premium.far_out_premium_start` |  | integer | Days from today where the adjustment reaches its maximum (1-999). Required for linear/fix.; min 1; max 999 |
| `customizations.far_out_premium.far_out_premium_step` |  | integer | Step size in days (1-999). Required for linear; ignored for fix (always 1).; min 1; max 999 |
| `customizations.demand_factor` |  | object | `demand_factor` customization — how strongly prices react to market demand. `hotel_compset_type` and `hotel_wt` require the hotel compset & weights feature (admin-granted): without it, writes including them are rejected (`ERR-FEATURE-NOT-ENABLED`) and reads omit them. With the feature, send the hote |
| `customizations.demand_factor.tone_demand_factor_on` | Y | boolean |  |
| `customizations.demand_factor.tone_demand_factor` |  | string | Required when the toggle is on. UI label in brackets. Each value moves prices further in response to a change in demand than the one above it. Note the "off" member here is the space-separated `no demand factor`, not `none` as the last-minute and far-out enums use. - `no demand factor` (No demand fa |
| `customizations.demand_factor.hotel_compset_type` |  | string | Hotel compset mode (feature-gated). UI label in brackets. - `recommended` (PriceLabs Default) — PriceLabs picks the hotel comp set. - `custom` (Selected in Hotel Data tab) — uses the comp set chosen there. fully_hotel + recommended is not a valid combination.; enum: `recommended`, `custom` |
| `customizations.demand_factor.hotel_wt` |  | string | Hotel vs short-term-rental weighting (feature-gated). UI label in brackets. Each value weights the comp set further toward hotels and away from short-term rentals than the one above it. - `fully_str` (Fully Short-Term Rental) - `mostly_str` (Mostly Short-Term Rental) - `balance` (Balance) - `mostly_ |
| `customizations.custom_seasonal_profile` |  | object | `custom_seasonal_profile` customization — define seasons with their own price settings and (optionally) min-stay / pricing / check-in-check-out profiles. (Spec key: `custom_seasonal_profile`.)  Structure: a toggle plus a `custom_seasonal_profile` object holding two season arrays — `seasons` (repeat  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile_on` | Y | boolean |  |
| `customizations.custom_seasonal_profile.custom_seasonal_profile` |  | object | Required when the toggle is on. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type` |  | string | How repeating-season prices are interpreted. Required when `seasons` is non-empty. - `percentage` — the season's prices are a signed adjustment to the base price. - `fixed` — the season's prices are absolute currency amounts.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.seasons` |  | array[object] | Seasons that repeat every year. |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.price_type_non_repeating` |  | string | Required when `non_repeating_seasons` is non-empty.; enum: `percentage`, `fixed` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.non_repeating_seasons` |  | array[object] | One-off seasons for specific calendar dates (feature-gated). |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_baseprice` |  | string | Inherit season base prices from the group/account level (feature-gated; listing/group level only). Writes accept `"1"`/`"0"` or `true`/`false`; reads return `"1"`/`"0"`.; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_minstay` |  | string | Inherit season min-stay profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_cico` |  | string | Inherit season check-in/check-out profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |
| `customizations.custom_seasonal_profile.custom_seasonal_profile.inherit_priceprofile` |  | string | Inherit season pricing profiles from the group/account level (feature-gated; listing/group level only; same format as `inherit_baseprice`).; enum: `1`, `0` |

**Response 200** (top fields):

| field | type | notes |
|---|---|---|
| `status` | string |  |
| `applied` | array[string] | Spec keys that were written (optional). |

Errors: `400`, `401`, `403`, `404`

