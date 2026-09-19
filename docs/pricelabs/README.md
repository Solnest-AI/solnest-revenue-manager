# PriceLabs OpenAPI specs (archived)

Downloaded from the published docs so the generated reference is reproducible and diffable.

| file | source |
|---|---|
| `customer-api.json` | https://developers.pricelabs.co/openapi/customer-api.json |
| `revenue-estimator-api.json` | https://developers.pricelabs.co/openapi/revenue-estimator-api.json |

`https://developers.pricelabs.co/openapi.json` is an HTML chooser page, not a spec. The two URLs
above are the real specs.

Refresh and regenerate the reference:

```bash
python3 tools/pricelabs_spec_report.py --fetch
git diff revenue-manager-plugin/skills/revenue-manager/references/pricelabs-api/
```

A non-empty diff means PriceLabs changed the API. That has happened inside nine days before:
`/v1/listings` renamed `city` to `city_name`, `lat`/`lon` to `latitude`/`longitude` and `push` to
`push_enabled` between 2026-08-25 and 2026-09-03, and a client reading the old names failed
silently rather than erroring.

Other documentation surfaces, for reference:
- `https://developers.pricelabs.co/llms.txt` indexes every doc page
- appending `.md` to any doc page URL returns clean markdown
- the docs site runs its own MCP server at `https://developers.pricelabs.co/_mcp/server`
