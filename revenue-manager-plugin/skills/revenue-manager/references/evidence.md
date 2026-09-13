# Evidence and measurements behind the runbook rules
> Reference for the revenue-manager skill. Read when you want to know WHY a runbook rule exists. Nothing here is an instruction; every rule these paragraphs justify is in SKILL.md.

## AirROI named comps

One `get_comparables` response is **~103,000 tokens**: 25 listings at ~7.8 KB each, and ~40%
of every listing is its description and photo URLs, which a pricing decision never reads.
The 13 fields it does read fit in a 75-byte CSV row.

## Reconciliation: the incident that created Step 4.9

Measured live 2026-09-12 across a 7-listing portfolio, forward 180 days: **54 booked
nights worth CA$97,083 were invisible to PriceLabs on 4 listings.** One ski chalet read
0% occupancy for December and January in PriceLabs while the PMS had it 71% and 84%
booked over Christmas and New Year at CA$1,161 to CA$3,500 a night.

Left unguarded, Step 6's own red-flag table fires *"5+ consecutive unbooked days, drop
10 to 15%"* and *"comp set fully booked and you are not, match comp pricing"* on
sold-out peak inventory. That is the single most expensive failure this skill can make.

## Neighborhood data

**Do not call `pricelabs_get_neighborhood_data` directly.** One response is ~118,000 tokens:
every bedroom category the market has, 540 days of daily occupancy of which the first 180 are
the past, and ten series where the decision reads seven. Run the reducer instead:

## Calendar and markup

**Do not load the raw PMS calendar for this.** A 365-day Hospitable calendar is ~49,000
tokens per listing and Step 4.9 already pulled it. Every number below comes from the gate's

## Per-property token cost, measured 2026-09-12 with count_tokens (one 4BR listing, 365 days)

| Pull | Raw via MCP | Via reducer | Fact classes proven |
|---|---|---|---|
| AirROI get_comparables | 103,542 | 1,725 | 13 |
| PriceLabs neighborhood | 118,037 | 14,296 (4,472 at 90d) | 25 |
| Hospitable calendar | 49,139 | ~1,000 (folded into the gate) | 13 |
| PriceLabs reservations | 13,417 | 941 | 12 |
| PriceLabs prices with reason | 541,727 | 6,316 (Tier A) | 18 smoke checks |
| Total per property | ~295,000 | ~24,400 | |

Every reducer is checked by `fetch/factcheck.py` on every commit: the same named facts are
computed from the raw payload and from the printed output through separate parsing paths and
must match. In August a trimmed tier dropped four fields that looked like noise and inverted a
verdict on one listing; the harness exists so that cannot recur silently.
