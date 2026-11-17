# Progress

Built 17 Nov 2026 (one afternoon) as the optional prototype for the BetterGov Fellowship application, due 17 Nov.

| Phase | Status | Notes |
|---|---|---|
| 1. Find what's public | Done | DepEd machine-ready files (Project Bukas): school-level enrollment, personnel by fund, ICT by fund, facilities. CRLA/ELLNA/NAT files have no Naga schools. EDCOM 2 dashboard behind a bot check. No barangay-level OPT+/CBMS for Naga found. |
| 2. Pipelines | Done | fetch, build (tagging rules, PSGC matching, checks, gaps), openapi, site. |
| 3. Pages | Done, local | Explorer, Source checks, Methodology, Data & API, Proposal. Verified desktop/phone, light/dark. |
| Deploy | Waiting for Kim | Public repo + Vercel project, as with ph-energy-data. |

## Deviations from the brief, and why

- **Naga budget source.** The portal's open-data API returns 404 for both years (the City hasn't switched it on), so rows come from the public Browse pages and each row's public page, which carry the same published data.
- **Outcomes.** The brief asked for Project Bukas outcomes keyed by school ID. DepEd's machine-ready CRLA covers no Bicol school, so the school-side "outcome" columns are what DepEd does publish for Naga (enrollment, classrooms, buildings needing repair) plus the SEF-funded staff and ICT, and CRLA is shown as "not published".
- **ECCD indicators.** Columns exist per barangay, empty, status "not published".
- **Map** is hand-drawn SVG from faeldon's boundaries, not MapLibre: 27 barangays don't need a tile server, and the site then makes no third-party requests.
- **Swagger-style try-it** reused from ph-energy-data's `data.js`.
- **Code licence AGPL-3.0** (the proposal text says so), where ph-energy-data is MIT.

## Next

1. Ask DepEd / the Naga Schools Division for school-level CRLA, and EDCOM 2 for barangay OPT+/CDC tables.
2. Ask the City for the SEF budget (Local School Board) in machine-readable form.
3. PPMP → PhilGEPS matching; MCP server.
