# CLAUDE.md

Prototype for Kim Williame Lee's BetterGov Fellowship 2026 application (Option 1: Basic Education + ECCD). Three cities: Naga, Zamboanga City, Cagayan de Oro (`CITIES` in `pipeline/fetch.py`). Read `PROGRESS.md` first, `README.md` for the layout. Sibling of `~/Documents/GitHub/ph-energy-data`.

## Commands

```bash
uv run python -m pipeline.fetch [deped|psgc|geo|portal]
uv run python -m pipeline.build && uv run python -m pipeline.site && uv run python -m pipeline.test_pipeline
python3 -m http.server 8766 --directory site
```

Always use absolute paths in Bash.

## Rules that are easy to break

- **Public data only.** The Naga portal is read from its public pages (Browse + each row's `/budget/<id>` page). Its bulk open-data API is off by the City's choice: don't use it, and never use anything from the `naga-budget-portal` repo or its admin side. Kim's company builds that portal; this repo must stay separate from the contract.
- **EDCOM 2's dashboard** is read from its public Tableau workbook on public.tableau.com (`fetch.py edcom2`), never through edcom2.gov.ph's bot check. The step stops if the author turns `allowDataAccess` off; keep it that way. Only Naga's rows are kept.
- **Ordinance cities are machine-read.** Zamboanga and Cagayan de Oro rows come from Stride's lgu-intel parser output (`fetch ordinances` copies `stride-lgu-intel/data/budgets/<slug>/ab-2026.json`), read from the cities' public PDFs. Keep `machine_read` true and the validation note on every row until a person reviews them. A row is placed at a school only when one public school's name matches; otherwise it's a `budget_school_unmatched` gap.
- **Link to the LGU budget comparison** (`LGU_COMPARE`, `/lgus/<slug>` pages), not to the People's Budget demo portal.
- **Never invent a figure.** An indicator with no public source stays empty with a `*_status` of "not published". Never fill it with a guess or a sample.
- **Never change a source's numbers.** Problems go to `checks.csv` / `gaps.csv`.
- **Unmatched is listed, not dropped.** Every join failure is a row in `gaps.csv`; the test enforces it for schools, budget rows and CRLA.
- **Codes are strings:** DepEd school IDs (6 digits), PSGC (10 digits, leading zero), AIP reference codes.
- **DepEd CSVs mix encodings.** Read as cp1252 and repair per cell with `fix_text`.
- **Naga's achievements are Naga's.** The 40% to 4% low-emerging-readers result is the City School Board's work as E4E reports it; never attribute it to Kim or this prototype.
- **Methodology and proposal pages are generated.** Edit `pipeline/templates/*.html`; every figure is a `{{placeholder}}` filled by `pipeline/site.py`.
- **No third-party requests.** The map is plain SVG (no tiles). Prose: Kim's voice, run the humanizer skill, no em dashes.
- **Privacy:** nothing about the author beyond the name "Kim Williame Lee".
- Ask Kim before deploying or making the GitHub repo public. Commits use the GitHub no-reply email (repo-local git config).
