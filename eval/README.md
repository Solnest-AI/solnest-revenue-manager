# Decision-level eval: do the reducers change the decision?

The `fetch/` reducers cut a property's Step 4 payload from hundreds of thousands of tokens to a
few tens of thousands. The fact-class harness (`fetch/factcheck.py`) proves the *numbers* survive.
This eval asks the only question that matters after that: **does the model reach the same
decision from the reduced tables as it would from the raw payloads?**

For each property, the same model (`claude-opus-5`, adaptive thinking, effort `xhigh`, the
Claude Code default), the same runbook (`SKILL.md` + `references/`) and the same task run under
two conditions that differ ONLY in the Step 4 data block:

| condition | the data block |
|---|---|
| `full` | raw tool payloads: prices with `reason` (first 90 dates; the complete reason payload alone is ~400k tokens and pushed one property past the 1M window), the whole neighborhood payload, every reservation row (PII stripped), the raw PMS calendar, the raw AirROI comparables, `listing_metrics` |
| `reduced` | the stdout of the five reducers, exactly as the runbook consumes it |

Both are built from the **same cached snapshot** (the reducers write the raw payload to
`~/.cache/revenue-manager/`; the full bundle reads those files back), so the only variable is
the reduction. Prices in both conditions are asserted equal per date (`price_snapshot_agreement`).

## Grading

Output is constrained to `schema.py` (`output_config.format`), so the comparison is mechanical:
`compare.py` turns each decision into canonical positions (gate status, overall direction, the
sign and size of each account-level field, the direction of dated changes by month, the flag
set) and diffs them. Two severities:

- **HARD**: a different decision. Opposite sign on a price field, a move of more than 5 points
  against a hold, gate blocked vs pass, a hard flag on one side only, opposite direction in the
  same month for dated changes.
- **SOFT**: the same decision, shaded differently.

Every property runs with several reps per condition. A key counts as **DIVERGE** only when both
conditions are internally consistent across their reps and disagree with each other. A key one
condition disagrees with *itself* on is **NOISE** (the model is unstable there; nothing can be
attributed to the reduction). `test_compare.py` locks this with an oracle (identical decisions
diverge nowhere), a null (a flipped decision is HARD) and noise-attribution cases.

A DIVERGE is not automatically the reducer's fault: adjudicate against the raw data. The
first live pair found one in each direction (a standing override the reduced side could not
see; a max-price raise on dates the PMS already had sold that the full side missed).

## Harness rules (from the eval health checklist)

- Infra failures (429 after retries, timeouts, unparseable output, served-model mismatch) go to
  `errors.jsonl`, never into `results.jsonl`. Truncated (`max_tokens`) and refused responses are
  recorded with their status and not scored as decisions.
- Every rep's trajectory (thinking summary, text, usage, model, request id, bundle hashes) is
  saved under `trajectories/`.
- Token counts and cost come from the API's `usage`, never from estimates.
- Transient errors retry with jittered backoff; attempt counts are recorded per row.

## Running

```bash
# from the repo root; keys are read from the env files named in the roster, never printed
python3 eval/decision_eval.py roster --env-file <pricelabs .env> --env-file <hospitable .env> --env-file <airroi .env>
python3 eval/decision_eval.py build --today YYYY-MM-DD        # runs the reducers, fetches the raw payloads
python3 eval/decision_eval.py count --reps-reduced 3 --reps-full 2   # tokens + cost before spending
ANTHROPIC_API_KEY=... python3 eval/decision_eval.py run --condition reduced --reps 3 --workers 2
ANTHROPIC_API_KEY=... python3 eval/decision_eval.py run --condition full --reps 2 --workers 2
python3 eval/decision_eval.py report                           # report.md + summary.json
```

Everything under `_private/` (roster, bundles, results, trajectories) is gitignored: it carries
listing ids, property names and revenue.
