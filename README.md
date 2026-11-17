# Naga education spending (prototype)

Naga City's education and early-childhood budget rows next to DepEd's school-level data for the Schools Division of Naga City, keyed by DepEd school ID and PSGC barangay code. Built 17 Nov 2026 as the prototype for Kim Williame Lee's BetterGov Fellowship 2026 application (Basic Education and Early Childhood challenges).

Static site plus Python pipelines, same pattern as [ph-energy-data](https://github.com/kimileeee/ph-energy-data).

## Pages

- `site/index.html`: explorer. City tiles, the City's budget rows (2027 AIP, 2026 enacted budget), then districts, schools and a barangay map.
- `site/checks.html`: every source with its period and status, reconciliation checks, and every unmatched or unpublished record.
- `site/methodology.html`: generated from `pipeline/templates/methodology.html`.
- `site/data.html`: downloads, Frictionless data package, OpenAPI 3.1 reference with try-it.
- `site/proposal.html`: the proposal, generated from `pipeline/templates/proposal.html`, with the flow diagram.

## What's real and what's a placeholder

| Layer | Status |
|---|---|
| City budget rows, AB 2026 (enacted) and AIP 2027 | Real: public pages of budget.naga.gov.ph |
| Schools, enrollment, classrooms, buildings, City-SEF-paid staff, LGU/SEF ICT | Real: DepEd machine-ready files (Project Bukas) |
| PSGC barangays and boundaries | Real: PSA PSGC 2026; faeldon/philippines-json-maps |
| CRLA per school (end of SY 2025-26) | Real: EDCOM 2 Early Childhood Dashboard's public Tableau workbook (data from DepEd); 30 of 31 public elementary schools. DepEd's own machine-ready CRLA file has no Naga school |
| OPT+ 2025 stunting | Real for the city as a whole (same workbook); not published by barangay, so that column stays empty |
| Child development centres | Real as yes/no per barangay (EDCOM 2's list of barangays without a CDC; none of Naga's is on it); counts not published |
| SEF budget line by line | Not on the portal |
| Procurement (PPMP, PhilGEPS), MCP server | Not built; fellowship work |

## Run

```bash
uv sync
uv run python -m pipeline.fetch            # all sources (DepEd ~150 MB); or: fetch deped | psgc | geo | portal | edcom2
uv run python -m pipeline.build            # data/*.csv|parquet, site/api, site/data, site/openapi.json
uv run python -m pipeline.site             # methodology + proposal pages, cache-busting stamps
uv run python -m pipeline.test_pipeline
python3 -m http.server 8766 --directory site
```

## Files

- `pipeline/fetch.py`: downloads; `data/raw/manifest.json` keeps URL and sha256 of each source.
- `pipeline/build.py`: tagging rules (`RULES`), barangay matching, checks, gaps, API, data package.
- `pipeline/openapi.py`: OpenAPI spec from the data package's fields. Lint: `npx @redocly/cli@1.34.3 lint site/openapi.json`.
- `pipeline/site.py`: renders the two templated pages and draws the diagram.
- `data/`: published tables (CSV + Parquet), `stats.json`.

## Licence

Code: AGPL-3.0. Compiled data: ODC-BY 1.0. Source data stays under its publishers' terms.
