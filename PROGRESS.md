# Progress

Built 17 Nov 2026 (one afternoon) as the optional prototype for the BetterGov Fellowship application, due 17 Nov.

| Phase | Status | Notes |
|---|---|---|
| 1. Find what's public | Done | DepEd machine-ready files (Project Bukas): school-level enrollment, personnel by fund, ICT by fund, facilities. CRLA/ELLNA/NAT files have no Naga schools. EDCOM 2 dashboard behind a bot check. No barangay-level OPT+/CBMS for Naga found. |
| 2. Pipelines | Done | fetch, build (tagging rules, PSGC matching, checks, gaps), openapi, site. |
| 3. Pages | Done, local | Explorer, Source checks, Methodology, Data & API, Proposal. Verified desktop/phone, light/dark. |
| 4. EDCOM 2 dashboard data | Done, local | Kim cleared the bot check once; the dashboard embeds a public Tableau workbook (author allows downloads). Pipeline reads it from public.tableau.com: school CRLA (end of SY 2025-26), the city's OPT+ 2025 row, the no-CDC barangay list. |
| 5. Zamboanga City and Cagayan de Oro | Done, local | Pipeline runs over `CITIES`; explorer has a city switcher. Budgets: FY 2026 ordinances machine-read by Stride's lgu-intel parsers. Zamboanga: 44 sheets name a national high school, 42 matched to DepEd IDs. CDO: 30 of 80 barangays on EDCOM 2's no-CDC list. Links to the LGU budget comparison. |
| Deploy | Waiting for Kim | Public repo + Vercel project, as with ph-energy-data. |

## Deviations from the brief, and why

- **Naga budget source.** The portal's open-data API returns 404 for both years (the City hasn't switched it on), so rows come from the public Browse pages and each row's public page, which carry the same published data.
- **Outcomes.** DepEd's machine-ready CRLA covers no Bicol school; school-level CRLA for Naga comes from the EDCOM 2 dashboard's workbook instead (30 of 31 public elementary schools).
- **ECCD indicators.** OPT+ 2025 stunting is only city-level, so the barangay column stays empty ("city level only"). CDCs are a yes/no flag per barangay; counts aren't published.
- **DepEd text encoding.** pandas 3 reads text as `str`, not `object`, so the first build skipped the encoding repair; fixed (every column is repaired).
- **Map** is hand-drawn SVG from faeldon's boundaries, not MapLibre: 27 barangays don't need a tile server, and the site then makes no third-party requests.
- **Swagger-style try-it** reused from ph-energy-data's `data.js`.
- **Code licence AGPL-3.0** (the proposal text says so), where ph-energy-data is MIT.

## Next

1. Ask EDCOM 2 / NNC for barangay-level OPT+ and CDC counts for Naga.
2. Ask the City for the SEF budget (Local School Board) in machine-readable form.
3. PPMP → PhilGEPS matching; MCP server.
