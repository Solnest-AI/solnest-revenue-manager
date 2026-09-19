# Reasoning about the PriceLabs customization stack

**Status:** design approved in chat 2026-09-18, implementation plan not yet written.
**Scope of this document:** how the revenue-manager skill reads, reasons about, and (behind the
existing approval gate) changes the six PriceLabs listing customizations, plus the vendor
diagnostics that surround them.

---

## 1. The problem

The skill today reads a price curve and reaches four levers: base, min, max, and a date-specific
override. The curve is not a number PriceLabs chose. It is the output of a stack:

```
base
  -> customization stack   (seasonality, day of week, last minute, far out,
                            demand factor, custom seasonal profile)
  -> clamp to [min, max]
  -> per-date override
  -> push to the PMS       (sync ratio, expected 1.0)
  -> channel markup        (applied by the PMS, not PriceLabs)
  -> the price a guest sees
```

Six of those layers are invisible to the skill. Two measured consequences on the reference
account:

**Misattribution.** One listing had 9 floor-pinned dates. Seven fell on the two weekdays
carrying a -10% day-of-week rule. The decision eval argued about raising the minimum price, which
treats a symptom produced one layer up.

**Invisible behaviour.** A second listing reads "off" on every lever and runs a 40% same-day
discount, because switching a rule off hands the date back to the algorithm's market-driven
default. The skill cannot see it, cannot explain it, and would fight it with the floor.

A third, found while probing on 2026-09-18: `GET /v1/customizations/listing` **omits every
toggled-off rule by default.** the probe listing returned 4 rules by default and 6 with
`toggled_on=false`. One of the hidden two was a `custom_seasonal_profile` holding two real
seasons (two named seasons, -5% and +5%), dormant, waiting for a toggle.

## 2. The core rule

> **A price complaint is a layer question before it is a number question.**

Before any recommendation, attribute the observed behaviour to the layer that produced it, then
propose the lever that owns that layer. Changing a number at the wrong layer is the failure mode
this design exists to prevent.

## 3. What gets read: Step 4c

Added to the existing parallel pull, through a new reducer.

| Call | Why | Notes |
|---|---|---|
| `GET /v1/customizations/listing?toggled_on=false` | the six rules | **The flag is mandatory.** The default hides off rules, including dormant ones with real values. |
| the `effective` block on every rule | what the rule currently does | Raw values cannot tell you what a market-driven type works out to, nor whether a number is a discount or a premium. |
| `GET /v1/customization_profiles` | shared min-stay / pricing / CICO profiles | Account-level objects. A profile change is a portfolio change. |
| `GET /v1/customizations/account` | inherited defaults | |
| `GET /v1/actions` | the vendor's own issue list | One call, whole account. |
| `GET /v1/nudges/available` | pending vendor suggestions | Feeds the lever ladder. |
| `POST /v1/logs` | change history | `log_type` is required. |

**Caching.** Customizations were unchanged over 18 days on the reference account while override
state decayed 846 dates in 12. Cache the stack for **days**, refresh on demand, and cache
overrides daily. This is the one read in the skill where a long cache is correct, and the
measurement is the reason.

**Reducer contract.** One line per rule carrying the toggle, the type, the signed value, the
window, and the `effective` string. Exit 2 means the stack could not be read this run, never
"no customizations". `dates=0`-style empty results are valid and must be distinguished from
failure, exactly as `reduce_overrides.py` already does.

## 4. Attribution

`ce = price / uncustomized_price`. Verified exact: a listing with every rule off returns 1.000 on
all seven weekdays.

| Symptom | Layer that could own it | Evidence that decides |
|---|---|---|
| Date pinned at the floor | base, a rule pushing down, or the min itself | `ce` on that date, and whether a rule's window covers it |
| Same-day collapse | last minute, on or off-and-market-driven | `ce` by days to check-in, plus the effective string |
| One weekday systematically low | day of week | `ce` grouped by weekday |
| Far dates flat or high | far-out premium | `ce` by days out |
| A whole season wrong | seasonality or the custom profile | `ce` by month vs the neighborhood's seasonal shape |
| Price ignores the market | demand factor | `ce` variance vs neighborhood variance |
| One date odd, neighbours fine | override | the override reducer row |
| PMS disagrees with PriceLabs | sync | the Step 4.9 ratio. Never fix this with a price |
| Guest sees a different number | channel markup | Step 3.2 |

### 4.1 The co-incidence test

`ce` is exact **in total** and does not decompose per rule. Several rules overlap the same date,
and the far-out premium covers most of a 365-day window. So:

- **Candidate**: the rule's window covers the affected dates and the sign of `ce` matches the
  rule's direction.
- **Confirmed**: the affected dates fall inside the window **and** the unaffected dates fall
  outside it.
- Anything else stays a candidate, and the report says so in those words.

The skill never writes "the day-of-week rule cost you 10% on this date". It writes "these dates
run 12% under the uncustomized price, three rules cover them, I cannot separate them."

## 5. The lever ladder

Prefer the smallest instrument that fixes the diagnosed layer. Ascending blast radius:

1. **Accept a nudge.** One listing, one field, a vendor-generated value.
2. **Date override.** Bounded and obviously reversible.
3. **Bounds**, min or max.
4. **Base price.**
5. **One customization rule.** Every date in its window, forward, until changed.
6. **Custom seasonal profile.** A write replaces the entire stored season set.
7. **Account level, group level, or a shared profile.** A portfolio change.

**One lever per diagnosis per run.** Never a rule change and a base change on the same symptom in
the same run: neither the operator nor the `pricing_decisions` outcome columns can then attribute
which one worked.

## 6. What a rule change must clear before it is proposed

- **Blast radius counted and named** in the approval card: dates in the horizon covered by the
  window, and how many are open.
- **The pattern holds.** One bad Tuesday is not a day-of-week problem. A minimum affected-date
  count, and consistency across them.
- **Occupancy inside the window vs outside it.** If those dates book fine, the rule is working.

## 7. Write safety

Every item is a measured trap and each one is a silent wrong price, returned with a 200.

- **Read, modify, write the full object.** Day-of-week days omitted from a write reset to 0, so a
  Friday/Saturday write wipes Monday to Thursday.
- **A `custom_seasonal_profile` write replaces every season.** Never send a delta.
- **Echo check after every write.** Re-read and compare the `effective` block to intent. The sign
  is accepted either way, because a premium is a legitimate setting.
- **"Off" is not "none".** To suppress a rule, send type `none` (or `no demand factor`) with the
  toggle ON. A recommendation may never say "turn it off" without saying which of the two it
  means.
- **All or nothing.** One invalid value rejects the whole call. Validate every field against the
  spec ranges first: day of week -75 to 1000, far out -30 to 500, last minute discount 0 to 75 or
  premium 0 to 500, far-out start 1 to 999.
- **Toggling off resets** the stored config for last minute and far out. Capture the full config
  before any toggle.
- **Feature-gated fields reject the whole call** with `ERR-FEATURE-NOT-ENABLED`: hotel compset and
  weights, non-repeating seasons, `inherit_*`, pricing profiles.
- **Snapshot before every write**, to disk, as the exact payload needed to re-POST the prior
  state. This is the kill switch and it ships with the feature, not after it.

### 7.1 The two sign conventions in `get_actions`

Measured on the probe listing 2026-09-18:

```
action_type: last_minute_conservative_vs_market
current:     { discount_pct: -12.0, days_from_date: 7 }
recommended: { discount_pct:  40.0, days_from_date: 10 }
stored rule: last_min_factor_value: -12.0
```

`current.discount_pct` echoes the stored **signed** value. `recommended.discount_pct` is a
positive **magnitude**, because the action type means "you discount less than the market".
Copying `recommended` into `last_min_factor_value` writes +40, a 40% premium, on a live
guest-facing calendar, and returns success.

**This inference is not confirmed by a write.** Before any automated apply of an action's
recommended value, confirm the convention with PriceLabs or with one controlled write on a
listing that is not taking bookings.

## 8. Vendor first

**`get_actions` is read before the skill forms its own diagnosis, and both are reported.** Where
they agree, confidence is high. Where they disagree, that disagreement is the most informative
line in the report, and the skill never silently overrides the vendor.

On the reference account, 5 of 8 listings carry an action. Four are
`last_minute_conservative_vs_market`, one is `oba_turned_off`, one is `many_blocked_dates`.

**`get_user_logs` closes a real hole.** The Supabase audit trail only records changes this skill
made. A client editing their base price in the PriceLabs dashboard is invisible to us today, and
this product ships to operators who are certainly also clicking in that dashboard. The "prior
attempts" line in the Step 7 card reads from the vendor log, not only from our own table.

## 9. Runbook changes

| Step | Change |
|---|---|
| 3.2 | unchanged; channel markup already stored |
| **4c (new)** | pull the customization stack, profiles, actions, nudges and logs through a reducer |
| **5.5 (new)** | attribute the layer, using section 4, before the framework runs |
| 6 | the floor-pinned red flag checks the stack before touching the minimum |
| 7 | the approval card gains `Layer:` and `Blast radius:` lines |
| 8 | the customization write path: snapshot, validate, write, echo check |
| 9 | the audit row records the layer and the snapshot path |

## 10. Scope

**In:** diagnosis of all six rules, and recommending plus executing **listing-level** rule changes
behind the existing human approval gate.

**Out, read-only, surfaced but never written:** account-level customizations, group-level
customizations, group overrides, shared min-stay profiles, `map`/`unmap`, `create_reservations`.

The reason is blast radius you can state in one line. A listing-level change names its own scope.
A shared profile silently touches listings that were never analysed, and a shared min-stay profile
is already a shared object on this account. The distance between "I approved a change to my
cabin" and "I changed 40 listings" is where the trust goes.

## 11. Coverage of the full API

`references/pricelabs-coverage.md` is the routing table for all 43 published operations: what each
answers, which runbook step owns it, which `references/pricelabs-api/` file documents it, and what
a live probe returned. `tools/pricelabs_endpoint_probe.py` regenerates the live column and never
fires a write.

Account entitlement varies and must be probed per client, not assumed. On the reference account
the Revenue Estimator returns `403 API_KEY_UNAUTHORIZED` (separately licensed) and the Listing
Optimizer has no report, so its two detail endpoints 400. A 403 on those is a plan boundary, not
an auth failure.

## 12. Risks

1. **A confident wrong attribution is worse than none.** Mitigated by candidate vs confirmed, but
   only if the report is genuinely allowed to say "I cannot separate these."
2. **This is the first design proposing changes the operator cannot eyeball later.** A wrong
   override on one date is obvious. A day-of-week rule quietly shaping a forward year is not.
   The snapshot and rollback must be built with the feature.
3. **Every run gets heavier.** Mitigated by the multi-day cache, which the stability measurement
   supports, but the reducer has to be tight.
4. **The sign convention in 7.1 is inferred, not proven.** Auto-applying an action's recommended
   value before confirming it can invert a discount into a premium on a live calendar.
