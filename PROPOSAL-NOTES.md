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
- **Reading results:** DepEd's machine-ready CRLA 2025-26 file has 6,121 schools from CAR and Regions I, III, VIII and IX only. **0 of Naga's 45 public schools** have a CRLA row. Same for ELLNA and NAT.
- Naga North has 26,946 of the 47,176 learners and 86 buildings needing major repair or worse (of 182 citywide).

## ECCD

- EDCOM 2's Early Childhood Dashboard (edcom2.gov.ph/eccddashboard) sits behind a bot check; no download or API found.
- No public barangay-level OPT+ or CBMS (CDC) table found for Naga. The barangay table has the columns, empty, marked "not published".

## Credit

- The 40% → 4% fall in low emerging readers after the City School Board used Project Bukas to realign the SEF is **Naga's**, as the Evidence for Education Coalition reports it. The prototype doesn't reproduce it (the school-level CRLA isn't public).

## One-liners for the form

- Prototype sentence: *A working prototype puts Naga City's 2027 AIP and 2026 budget rows for education and early childhood next to DepEd's Project Bukas data for all 45 public schools in the Schools Division of Naga City, keyed by school ID and PSGC: [[link]] (code: https://github.com/kimileeee/ph-education-spending).*
- Why it matters: *In Naga's 2027 AIP, ₱130 million of ₱278.7 million for education and early childhood sits in one SEF row that names no school, and none of the 47 rows I tagged names a school or barangay. Meanwhile DepEd's own files show 28 school staff paid from the City SEF, and none of Naga's public schools has CRLA results in DepEd's machine-ready files.*
