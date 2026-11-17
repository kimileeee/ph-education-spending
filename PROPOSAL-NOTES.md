# Proposal notes: numbers for the Option 1 answers

Numbers as of 17 Nov 2026, from `data/stats.json`. Rerun the pipeline and they move.

## The City's budget (budget.naga.gov.ph, public pages)

- **2027 AIP (proposed):** 424 rows, ₱8,698,439,574 on the Browse page. Each row is a published programme; the portal's AIP overview says the same (424 programmes, ₱8.70B, 57 of 63 offices published, 17 Nov 2026). The application's 332 programmes / ₱8.13B is an earlier snapshot: 63 programmes were last updated on 6 Nov, and the figure keeps moving until all offices publish. Education and early childhood (basic education, ECCD, child nutrition, child welfare, library): **₱278.7 million in 24 rows**.
- **The SEF in the 2027 AIP is one row:** "Management of the Special Education Fund and Secretariat Support to the Naga City School Board", 3000-2-03-38-002-001-000, **₱130,000,000**, all MOOE, fund SEF. That's **47%** of the education and early-childhood total, and it names no school. https://budget.naga.gov.ph/budget/01a13564-6353-7486-bdec-a67a8a8f798a
- Other 2027 rows: scholarships ₱44.15M, QUEEN ₱27.52M (GF + LDF), ECCD office ₱45.38M across 6 rows (₱29.01M of it institutional and administrative support).
- **2026 enacted budget:** 430 rows, ₱1,664,699,680 on Browse (the overview's ₱2.12B adds ₱457.66M of special purpose appropriations). The same offices: ₱30.4 million in 23 rows. The enacted rows carry no fund field and **the SEF's own 2026 budget isn't on the portal**.
- **0 of 47** tagged rows (both years) name a school or barangay. All are city-wide.
- Both documents reconcile: rows add up to the page's stated total to the peso; PS+MOOE+FE+CO equals each row total (4 enacted rows give only a total).

## DepEd's school data (Project Bukas machine-ready files)

- Schools Division of Naga City: **98 schools, 45 public** in 4 districts (East 14, North 14, South 10, West 7), **47,176 public-school learners** in SY 2025-26 (2,926 in kindergarten). All 98 matched to PSGC barangay codes (two DepEd spellings matched by hand); 19 of 27 barangays have a public school.
- **Where SEF money shows up on the school side (SY 2023-24):** **28 school staff paid from the City SEF** at 9 schools (2 teachers; the rest learning support aides and administrative staff), 23 more paid from other LGU funds, and **306 ICT items** (mostly TVs and printers) at 37 schools bought with LGU or SEF money.
- **Reading results (CRLA, end of SY 2025-26, as of 10 May 2026, via the EDCOM 2 dashboard's public workbook):** 30 of Naga's 31 public elementary schools (the SPED Center is the one without). **445 of 9,616 learners (4.6%) read at the Low Emerging level**; 7.6% are struggling readers (Low + High Emerging). By district: North 2.0%, East 5.1%, West 5.5%, South 6.4%. Highest school: Jose Rizal ES, 11.4% (18 of 158). DepEd's own machine-ready CRLA file has no Naga school (it covers CAR and Regions I, III, VIII, IX).
- Naga North has 26,946 of the 47,176 learners and 86 buildings needing major repair or worse (of 182 citywide).

## Zamboanga City and Cagayan de Oro (added 17 Nov; budgets machine-read from the 2026 ordinance PDFs, unreviewed)

- **Zamboanga City:** 222 public schools in 12 districts, 234,814 learners. 2026 ordinance: ₱594.9M for education and early childhood in 59 rows. **44 sheets name a single national high school (₱11.6M, supplies/utilities/travel); 42 are matched to a DepEd school ID**, so its money can be followed to a school. Also ₱148.2M allowances for public school heads and teachers, ₱100M school supplies allowance, ₱127.1M school buildings, ₱21M honoraria for barangay child development workers. CRLA: 174 of 174 public elementary schools, **12.6% low emerging** (7.7% Tetuan to 17.8% Labuan by district). OPT+ 2025: 1.9%. 3 of 98 barangays without a CDC. 40 school staff paid from the City SEF.
- **Cagayan de Oro:** 115 public schools in 10 districts, 138,334 learners. 2026 ordinance (sheets tie exactly to the ₱8.95B GRAND TOTAL): ₱393.0M in 24 rows, incl. ₱35.2M City Education Development Office, ₱350M scholarship grants, ₱1.0M day care/ECCD lines. No row names a school. CRLA: 73 of 73, **8.5% low emerging**. **30 of 80 barangays are on EDCOM 2's no-CDC list.** OPT+ 2025 row says 0.3% stunted (192 of 68,903), suspiciously low: ask NNC.
- Neither ordinance carries the SEF (General Fund books).
- Whole budgets, side by side: https://peoples-budget.stridetech.workers.dev/lgus/explore (LGU budget comparison).
- One-liner: *The same pipeline runs on Zamboanga City and Cagayan de Oro from their ordinance PDFs: in Zamboanga, 42 budget rows already name a specific high school and join to its DepEd ID; in Cagayan de Oro, 30 of 80 barangays have no child development centre.*

## ECCD (EDCOM 2 Early Childhood Dashboard, public Tableau workbook, author allows downloads)

- **OPT+ 2025, City of Naga (city level only):** 17,736 children under five measured (83.2% of an estimated 21,325); **328 (1.8%) stunted or severely stunted** (228 stunted, 100 severely). On the dashboard's own measure (described by EDCOM 2 as ages 0 to 2): 79 of 6,535 (1.2%). Not published by barangay.
- **Child development centres:** none of Naga's 27 barangays is on EDCOM 2's list of barangays without a CDC. No counts per barangay.

## Credit

- The 40% → 4% fall in low emerging readers after the City School Board used Project Bukas to realign the SEF is **Naga's**, as the Evidence for Education Coalition reports it. The public end-of-SY 2025-26 figure (4.6%) is in line with the 4%; the 40% starting point can't be rebuilt from public data.

## One-liners for the form

- Prototype sentence: *A working prototype puts Naga City's 2027 AIP and 2026 budget rows for education and early childhood next to DepEd's Project Bukas data and CRLA reading results for the 45 public schools in the Schools Division of Naga City, keyed by school ID and PSGC: [[link]] (code: https://github.com/kimileeee/ph-education-spending).*
- Why it matters: *In Naga's 2027 AIP, ₱130 million of ₱278.7 million for education and early childhood sits in one SEF row that names no school, and none of the 47 rows I tagged names a school or barangay. The outcomes are public school by school (low emerging readers range from 2.0% to 6.4% by district, and up to 11.4% in one school), so the missing link is the spending side.*
