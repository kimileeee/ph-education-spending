"""Turn data/raw into the published tables, checks, gaps, static JSON API, OpenAPI spec and data package.

Rules this file keeps:
- Never change a source's numbers. Problems go to checks/gaps; nothing is fixed in place.
- Codes are strings (DepEd school IDs, PSGC codes, AIP reference codes).
- A record that can't be joined is listed in gaps.csv, never dropped.
- Every row carries its city, source_id and period; sources.csv says where each source lives.
"""

import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache

import pandas as pd

from pipeline.fetch import CITIES, LGU_COMPARE, NAGA_PSGC, ORDINANCE_FY, PORTAL, RAW

ROOT = RAW.parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

# ---------------------------------------------------------------- tagging rules (the schema's "domain" field)
# Naga's portal rows carry an office code. Each rule: (rule_id, office codes, name regex or None, domain); first
# match wins. Rows of these offices that match no rule are tagged "office_other" and still listed.
RULES = [
    ("sef-line", {"ESSO"}, r"special education fund", "basic_education"),
    ("esso-education", {"ESSO"}, r"queen|scholar|education|bisekleta|pag-eskwela", "basic_education"),
    ("esso-sports", {"ESSO"}, r"sport|athlet|chess|tournament|championship|festival|camp|archery|arnis|badminton|"
                              r"billiard|karate|football|futsal|gymnas|silat|softball|taekwondo|tennis|volleyball|"
                              r"triathlon|duathlon|aquathlon|endurance|coaches|himnastica", "sports"),
    ("eccd-office", {"ECCDDO"}, None, "early_childhood"),
    ("nutrition", {"CPNO"}, r"nutrition|feeding|supplement|micronutrient|dietary", "nutrition"),
    ("child-welfare", {"CSWDO"}, r"child", "child_welfare"),
    ("children-office", {"NCCAO"}, None, "child_welfare"),
    ("library", {"RSRL"}, None, "library_literacy"),
    ("science-centre", {"BSTC"}, None, "science_centre"),
    ("city-college", {"CCN"}, None, "tertiary"),
]
# Ordinance books (Zamboanga, Cagayan de Oro) have no office codes. A whole sheet becomes a row when its office or
# unit says it is about schools; otherwise single object lines become rows when their name does.
SHEET_RULES = [
    ("aid-named-school", r"AGENCIES\)\s*[-:]?\s*.*\b(HIGH SCHOOL|ELEMENTARY|SCHOOL)\b(?!S)", "basic_education"),
    ("aid-public-schools", r"PUBLIC SCHOOLS", "basic_education"),
    ("education-office", r"EDUCATION DEVELOPMENT|SCHOOLS? DIVISION|EDUCATION OFFICE", "basic_education"),
    ("city-college", r"COLEGIO|COLLEGE|UNIVERSITY", "tertiary"),
]
LINE_RULES = [
    ("line-eccd", r"day ?care|child development|\bECCD\b|early childhood", "early_childhood"),
    ("line-nutrition", r"nutrition|feeding", "nutrition"),
    ("line-school", r"school building|school supplies|scholar|public school|teacher|learner|educational assistance|textbook|"
                    r"education & innovation|education councils", "basic_education"),
    ("line-child", r"\bchild", "child_welfare"),
]
DOMAINS = {  # label, counted in the explorer's "education and early childhood" total by default
    "basic_education": ("Basic education", True),
    "early_childhood": ("Early childhood (ECCD)", True),
    "nutrition": ("Child nutrition", True),
    "child_welfare": ("Child welfare", True),
    "library_literacy": ("Library and literacy", True),
    "science_centre": ("Science centre", False),
    "tertiary": ("City college", False),
    "sports": ("Sports", False),
    "office_other": ("Other rows of these offices", False),
}
CYCLE_DOCS = {  # Naga's portal documents
    "AB2026": ("Annual Budget 2026, enacted by Ord. No. 2025-131", 2026, "enacted"),
    "AIP2027": ("Annual Investment Program 2027", 2027, "proposed"),
}
# DepEd spells some barangays differently from PSA's PSGC. Matched by hand, listed on the checks page.
# (Parentheticals such as "(POB.)" and a leading "BARANGAY" are dropped by rule before matching.)
BARANGAY_ALIASES = {"naga": {"CONCEPCION PEQUENO": "Concepcion Pequeña"}, "cdo": {"BULULANG": "Balulang"}}
NOT_PUBLISHED = "not published"
E2: dict = {}  # EDCOM 2 dashboard's slice for these cities (data/raw/edcom2/cities.json), loaded in main()


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def place_key(s: str) -> str:
    """Barangay name for matching: folded, without parentheticals or a leading 'BARANGAY'."""
    s = re.sub(r"\(.*?\)", " ", fold(s))
    return re.sub(r"^BARANGAY\s+", "", re.sub(r"\s+", " ", s).strip())


def school_key(s: str) -> str:
    """School name for matching a budget sheet to DepEd: folded, punctuation and generic words dropped."""
    s = re.sub(r"[^A-Z0-9 ]", " ", fold(s))
    s = re.sub(r"\b(NATIONAL|HIGH|SCHOOL|MEMORIAL|INTEGRATED|SENIOR|NHS|MAIN|ANNEX|OF)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fix_text(s):
    """DepEd's CSVs mix UTF-8 and Windows-1252 cells. Read as cp1252, then undo UTF-8 mojibake per cell."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


@lru_cache(maxsize=None)
def read_deped(name: str) -> pd.DataFrame:
    """Callers filter and copy; the cached frame is shared across cities."""
    df = pd.read_csv(RAW / "deped" / name, encoding="cp1252", dtype=str, keep_default_na=False, low_memory=False)
    for c in df.columns:
        df[c] = df[c].map(fix_text)  # every column is read as text
    return df


def num(df: pd.DataFrame, cols) -> pd.Series:
    return df[list(cols)].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1).astype(int)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def gap(city, kind, record, detail, source_id, resolved=False) -> dict:
    return {"city": city, "kind": kind, "record_id": record, "detail": detail, "source_id": source_id, "resolved": resolved}


def check(city, cid, what, expected, actual, source_id, url, unit="PHP") -> dict:
    return {"city": city, "check_id": cid, "what": what, "expected": expected, "actual": actual, "unit": unit,
            "status": "match" if abs(float(expected) - float(actual)) < 0.005 else "mismatch", "source_id": source_id, "url": url}


# ---------------------------------------------------------------- sources
def sources(manifest: dict) -> pd.DataFrame:
    m = manifest
    dep = lambda f: m[f"deped/{f}"]  # noqa: E731
    pb = "DepEd, Project Bukas machine-ready files"
    rows = [
        ("deped-enrollment-2025-26", "Enrollment in SY 2025-2026 (school level)", pb, dep("enrollment_2025-26.csv")["url"], "SY 2025-26", "used", dep("enrollment_2025-26.csv")["sha256"]),
        ("deped-enrollment-2023-24", "Enrollment in SY 2023-2024 (school level)", pb, dep("enrollment_2023-24.csv")["url"], "SY 2023-24", "used", dep("enrollment_2023-24.csv")["sha256"]),
        ("deped-enrollment-2017-18", "Enrollment in SY 2017-2018 (school level)", pb, dep("enrollment_2017-18.csv")["url"], "SY 2017-18", "used", dep("enrollment_2017-18.csv")["sha256"]),
        ("deped-personnel-2023-24", "School Personnel in SY 2023-2024, incl. locally funded staff by fund", pb, dep("personnel_2023-24.csv")["url"], "SY 2023-24", "used", dep("personnel_2023-24.csv")["sha256"]),
        ("deped-ict-2023-24", "ICT Data in SY 2023-2024, incl. equipment by funding source", pb, dep("ict_2023-24.csv")["url"], "SY 2023-24", "used", dep("ict_2023-24.csv")["sha256"]),
        ("deped-facilities-2023-24", "School Facilities in SY 2023-2024", pb, dep("facilities_2023-24.csv")["url"], "SY 2023-24", "used", dep("facilities_2023-24.csv")["sha256"]),
        ("deped-crla-2025-26", "CRLA 2025-2026, selected schools", pb, dep("crla_2025-26_selected.csv")["url"], "SY 2025-26", "checked: none of these cities' schools", dep("crla_2025-26_selected.csv")["sha256"]),
        ("deped-ellna-2023-24", "ELLNA 2023-2024, selected schools", pb, dep("ellna_2023-24_selected.csv")["url"], "SY 2023-24", "checked: none of these cities' schools", dep("ellna_2023-24_selected.csv")["sha256"]),
        ("deped-nat-2023-24", "NAT Grade 6 2023-2024, selected schools", pb, dep("nat_2023-24_selected.csv")["url"], "SY 2023-24", "checked: none of these cities' schools", dep("nat_2023-24_selected.csv")["sha256"]),
        ("naga-ab2026", "Naga: Annual Budget 2026 (Ord. No. 2025-131), public Browse page", "City Government of Naga, People's Budget Portal",
         m["naga/AB2026.json"]["url"], "FY 2026", "used", m["naga/AB2026.json"]["sha256"]),
        ("naga-aip2027", "Naga: Annual Investment Program 2027, public Browse page", "City Government of Naga, People's Budget Portal",
         m["naga/AIP2027.json"]["url"], "FY 2027", "used", m["naga/AIP2027.json"]["sha256"]),
    ]
    for slug, c in CITIES.items():
        if c["budget"] == "ordinance":
            k = f"{slug}/ab-{ORDINANCE_FY}.json"
            rows.append((f"{slug}-ab{ORDINANCE_FY}", f"{c['name']}: Annual Budget {ORDINANCE_FY}, appropriation ordinance (PDF, machine-read)",
                         f"{c['name']}; read by {m[k]['parsed_by']}", m[k]["url"], f"FY {ORDINANCE_FY}", "used: machine-read, unreviewed", m[k]["sha256"]))
    rows += [
        ("psgc-2026", "Philippine Standard Geographic Code, 2026 (via bendlikeabamboo/barangay)", "Philippine Statistics Authority",
         m["psgc/naga.json"]["url"], "2026", "used", m["psgc/naga.json"]["sha256"]),
        ("faeldon-geo", "Barangay boundaries, medium resolution (philippines-json-maps)", "faeldon/philippines-json-maps (MIT)",
         m["geo/naga-barangays.json"]["url"], "release v1.1.1", "used", m["geo/naga-barangays.json"]["sha256"]),
        ("edcom2-crla", f"CRLA per school, from the EDCOM 2 Early Childhood Dashboard ({E2['crla_source_note']})", "EDCOM 2 (data: DepEd)",
         E2["workbook"], "End of SY 2025-26, as of 10 May 2026", "used", m["edcom2/cities.json"]["sha256"]),
        ("edcom2-opt-2025", "2025 Operation Timbang Plus report, city rows, from the EDCOM 2 Early Childhood Dashboard", "EDCOM 2 (data: NNC OPT+)",
         E2["workbook"], "2025", "used: city level only", m["edcom2/cities.json"]["sha256"]),
        ("edcom2-no-cdc", "Barangays without a child development centre, from the EDCOM 2 Early Childhood Dashboard", "EDCOM 2 (source of the list not stated)",
         E2["workbook"], f"workbook updated {E2['workbook_updated'][:10]}", "used: yes/no per barangay, no counts", m["edcom2/cities.json"]["sha256"]),
        ("nnc-opt-plus", "Operation Timbang Plus (OPT+) results by barangay", "National Nutrition Council",
         "https://www.nnc.gov.ph/", "annual", "checked: no barangay-level file found for these cities", ""),
    ]
    return pd.DataFrame(rows, columns=["source_id", "title", "publisher", "url", "period", "status", "sha256"])


# ---------------------------------------------------------------- schools
GRADES = r"^(kinder|g\d+|esng|jhsng)_"
CRLA_BANDS = {"crla_low_emerging": "Total Low Emerging", "crla_high_emerging": "Total High Emerging",
              "crla_developing": "Total Developing", "crla_transitioning": "Total Transitioning", "crla_at_grade_level": "Total At Grade Level"}


def crla_fields(r) -> dict:
    """One school's CRLA counts as published (Grades 1-3, end of SY 2025-26); None where the school has no row."""
    if r is None:
        return {"crla_assessed": None, **{k: None for k in CRLA_BANDS}}
    return {"crla_assessed": int(r["Total Assessed"]), **{k: int(r[v]) for k, v in CRLA_BANDS.items()}}


def match_barangay(slug: str, name: str, psgc: dict):
    """(barangay, how) for a DepEd barangay name; how is 'name', 'rule' or 'hand'."""
    exact = {fold(b["name"]): b for b in psgc["barangays"]}
    if fold(name) in exact:
        return exact[fold(name)], "name"
    alias = BARANGAY_ALIASES.get(slug, {}).get(fold(name))
    if alias:
        return next(b for b in psgc["barangays"] if b["name"] == alias), "hand"
    keyed = {}
    for b in psgc["barangays"]:
        keyed.setdefault(place_key(b["name"]), []).append(b)
    hits = keyed.get(place_key(name), [])
    return (hits[0], "rule") if len(hits) == 1 else (None, "")


def schools(slug: str, gaps: list, psgc: dict) -> pd.DataFrame:
    c = CITIES[slug]
    e25 = read_deped("enrollment_2025-26.csv")
    e25 = e25[e25.division == c["division"]].copy()
    if e25.empty:
        raise RuntimeError(f"no schools for division {c['division']!r}: DepEd renamed it?")
    grade_cols = [col for col in e25.columns if re.match(GRADES, col)]
    e25["learners_2025_26"] = num(e25, grade_cols)
    e25["kinder_2025_26"] = num(e25, ["kinder_male", "kinder_female"])
    ids = set(e25.school_id)

    def total(name):
        d = read_deped(name)
        d = d[d.school_id.isin(ids)].set_index("school_id")
        return num(d, [col for col in d.columns if re.match(GRADES, col)])

    e23, e17 = total("enrollment_2023-24.csv"), total("enrollment_2017-18.csv")
    sub = lambda name: read_deped(name).pipe(lambda d: d[d.school_id.isin(ids)]).set_index("school_id")  # noqa: E731
    per, ict, fac = sub("personnel_2023-24.csv"), sub("ict_2023-24.csv"), sub("facilities_2023-24.csv")
    sef_city = [col for col in per.columns if re.search(r"sef_municipal(ity)?_city$", col)]
    lgu = [col for col in per.columns if col.endswith("lgu_funding")]
    teach_sef = [col for col in sef_city if "_teachers_" in col]
    crla_deped = set(read_deped("crla_2025-26_selected.csv").school_id)
    crla = {str(r["School ID"]): r for r in E2["cities"][slug]["crla"]}

    out = []
    for r in e25.itertuples():
        sid = r.school_id
        b, how = match_barangay(slug, r.barangay, psgc)
        if b is None:
            gaps.append(gap(slug, "barangay_unmatched", sid, f"{r.school_name}: DepEd barangay {r.barangay!r} matches no PSGC barangay of {c['name']}",
                            "deped-enrollment-2025-26"))
        elif how == "hand":
            gaps.append(gap(slug, "barangay_alias", sid, f"{r.school_name}: DepEd's {r.barangay!r} matched by hand to PSGC {b['name']!r} ({b['psgc_id']})",
                            "deped-enrollment-2025-26", resolved=True))
        in23 = sid in per.index
        if not in23:
            gaps.append(gap(slug, "school_not_in_2023_24", sid, f"{r.school_name} ({r.sector}) is in DepEd's 2025-26 enrollment but not in the "
                            "2023-24 personnel, ICT and facilities files (new school or new ID)", "deped-personnel-2023-24"))
        f = fac.loc[[sid]] if sid in fac.index else None
        out.append({
            "city": slug, "school_id": sid, "school_name": r.school_name, "sector": r.sector, "management": r.school_management,
            "school_district": r.school_district, "barangay_deped": r.barangay,
            "psgc_barangay_code": b["psgc_id"] if b else "", "psgc_barangay_name": b["name"] if b else "", "barangay_match": how,
            "offers_es": r.offers_es == "Yes", "offers_jhs": r.offers_jhs == "Yes", "offers_shs": r.offers_shs == "Yes",
            "learners_2025_26": int(r.learners_2025_26), "kinder_2025_26": int(r.kinder_2025_26),
            "learners_2023_24": int(e23[sid]) if sid in e23.index else None,
            "learners_2017_18": int(e17[sid]) if sid in e17.index else None,
            "classrooms_instructional_2023_24": int(num(f, ["es_classrooms_instructional", "jhs_classrooms_instructional", "shs_classrooms_instructional"]).iloc[0]) if f is not None else None,
            "buildings_major_repair_or_worse_2023_24": int(num(f, ["buildings_needs_major_repair", "buildings_for_condemnation", "buildings_for_demolition"]).iloc[0]) if f is not None else None,
            "makeshift_rooms_2023_24": int(num(f, ["es_makeshift_rooms", "hs_makeshift_rooms"]).iloc[0]) if f is not None else None,
            "staff_city_sef_2023_24": int(num(per.loc[[sid]], sef_city).iloc[0]) if in23 else None,
            "teachers_city_sef_2023_24": int(num(per.loc[[sid]], teach_sef).iloc[0]) if in23 else None,
            "staff_other_lgu_2023_24": int(num(per.loc[[sid]], lgu).iloc[0]) if in23 else None,
            "ict_items_lgu_sef_2023_24": int(num(ict.loc[[sid]], [col for col in ict.columns if col.endswith("_lgu_sef")]).iloc[0]) if sid in ict.index else None,
            "crla_2025_26": "published" if sid in crla else NOT_PUBLISHED,
            **crla_fields(crla.get(sid)),
            "in_deped_crla_file": sid in crla_deped,
            "source_ids": "deped-enrollment-2025-26 deped-personnel-2023-24 deped-ict-2023-24 deped-facilities-2023-24"
                          + (" edcom2-crla" if sid in crla else ""),
        })
        if r.sector == "Public" and sid not in crla:
            why = ("CRLA tests Grades 1 to 3 and this school has no elementary grades" if r.offers_es != "Yes"
                   else "the school offers elementary grades but has no CRLA row")
            gaps.append(gap(slug, "crla_not_published", sid, f"{r.school_name}: not in the EDCOM 2 dashboard's CRLA data ({why})", "edcom2-crla",
                            resolved=r.offers_es != "Yes"))
    for sid in sorted(set(crla) - ids):
        gaps.append(gap(slug, "crla_school_unmatched", sid, f"{crla[sid]['School Name']}: CRLA row for a school ID not in DepEd's 2025-26 enrollment", "edcom2-crla"))
    df = pd.DataFrame(out)
    ints = [col for col in df.columns if col.startswith(("learners_20", "classrooms_", "buildings_", "makeshift_", "staff_", "teachers_", "ict_", "crla_")) and col != "crla_2025_26"]
    df[ints] = df[ints].astype("Int64")  # nullable: a school missing from a source stays empty, never 0
    df["learners_per_classroom_2023_24"] = (df.learners_2023_24 / df.classrooms_instructional_2023_24.where(df.classrooms_instructional_2023_24 > 0)).round(1)
    return df


# ---------------------------------------------------------------- budget lines
def budget_row(**kw) -> dict:
    base = {"line_id": "", "city": "", "cycle": "", "document": "", "fiscal_year": 0, "status": "", "aip_reference_code": "",
            "office_code": "", "office_name": "", "name": "", "pap_class": "", "domain": "", "tag_rule": "", "fund_sources": "",
            "thematic_tags": "", "ps": 0.0, "mooe": 0.0, "co": 0.0, "total": 0.0, "finish_line": "", "place_level": "city",
            "place_code": "", "school_ids": "", "place_match": "", "barangay_codes": "", "page": None, "source_id": "",
            "source_url": "", "retrieved": "", "machine_read": False, "validation": ""}
    return base | kw


def budget_naga(gaps: list, checks: list) -> list:
    out = []
    for cycle, (doc, fy, status) in CYCLE_DOCS.items():
        raw = json.loads((RAW / "naga" / f"{cycle}.json").read_text())
        items = raw["items"]
        src = f"naga-{cycle.lower()}"
        checks.append(check("naga", f"naga-{cycle}-total", f"Naga {doc}: rows on the public Browse page add up to the page's stated total",
                            float(raw["stated_total"]), round(sum(float(i["proposedTotal"]) for i in items), 2), src, raw["url"]))
        split = lambda i: round(sum(float(i[k]) for k in ("psTotal", "mooeTotal", "feTotal", "coTotal")), 2)  # noqa: E731
        unsplit = [i for i in items if split(i) == 0 and float(i["proposedTotal"]) != 0]  # declared as a total, no split
        has_split = [i for i in items if i not in unsplit]
        bad_split = [i for i in has_split if split(i) != float(i["proposedTotal"])]
        checks.append(check("naga", f"naga-{cycle}-split", f"Naga {doc}: PS + MOOE + FE + CO equals the row's total, for every row that gives a split "
                            f"({len(unsplit)} rows give only a total)", len(has_split), len(has_split) - len(bad_split), src, raw["url"], unit="rows"))
        for i in items:
            off = i["office"]["acronym"]
            det = raw["details"].get(i["id"])
            domain, rule = next(((dom, rid) for rid, offices, pat, dom in RULES
                                 if off in offices and (pat is None or re.search(pat, i["name"], re.I))), (None, None))
            if domain is None and det is None:
                continue  # outside the offices in scope
            if domain is None:
                domain, rule = "office_other", "office-in-scope"
            funds = det.get("fundSources") if det else None
            out.append(budget_row(
                line_id=i["id"], city="naga", cycle=cycle, document=doc, fiscal_year=fy, status=status,
                aip_reference_code=i["aipReferenceCode"], office_code=off, office_name=i["office"]["name"],
                name=i["name"].strip(), pap_class=i["papClass"] or "", domain=domain, tag_rule=rule,
                fund_sources=" ".join(funds) if funds else "",
                thematic_tags=" ".join(t["name"] for t in (det or {}).get("thematicTags") or [] if isinstance(t, dict)),
                ps=float(i["psTotal"]), mooe=float(i["mooeTotal"]), co=float(i["coTotal"]) + float(i["feTotal"]),
                total=float(i["proposedTotal"]), finish_line=(i.get("finishLine") or {}).get("name", ""),
                place_code=NAGA_PSGC, source_id=src, source_url=f"{PORTAL}/budget/{i['id']}", retrieved=raw["retrieved"][:10],
                validation="as published on the City's portal" + ("; enacted" if status == "enacted" else "; proposed, not yet enacted")))
            gaps.append(gap("naga", "budget_line_no_place", i["id"], f"{cycle} {i['aipReferenceCode']} {i['name'].strip()} "
                            f"(₱{float(i['proposedTotal']):,.0f}): no school ID or barangay code; city-wide only", src))
        if not any(r["cycle"] == cycle and "SEF" in r["fund_sources"] for r in out):
            gaps.append(gap("naga", "sef_budget_not_published", cycle, f"Naga {doc}: none of the rows read (the offices in scope) lists the SEF as a fund"
                            + (", and the enacted rows carry no fund field at all" if status == "enacted" else "")
                            + ". The SEF has its own budget, approved through the Local School Board, which the portal does not carry.", src))
    return out


def clean_unit(u: str) -> str:
    u = re.sub(r"^.*?AGENCIES\)\s*[-:]?\s*", "", u or "") if "AGENCIES)" in (u or "") else (u or "")
    return re.sub(r"\s{2,}.*$", "", u).strip(" -:") or u


def budget_ordinance(slug: str, sch: pd.DataFrame, gaps: list, checks: list) -> list:
    c = CITIES[slug]
    book = json.loads((RAW / slug / f"ab-{ORDINANCE_FY}.json").read_text())
    src = f"{slug}-ab{ORDINANCE_FY}"
    doc = f"Annual Budget {ORDINANCE_FY}" + (f", Ord. No. {book['ordinance']}" if book.get("ordinance") else ", appropriation ordinance")
    page_url = lambda page, obj=None: (obj or {}).get("page_url") or (f"{book['source_pdf_url']}#page={page}" if book.get("source_pdf_url") else book["source_url"])  # noqa: E731
    sheets_sum = round(sum(float(s["total"] or 0) for s in book["sheets"]), 2)
    ties = abs(sheets_sum - float(book["stated_total"])) < 0.005  # every sheet together equals the printed GRAND TOTAL
    if ties:
        checks.append(check(slug, f"{slug}-total", f"{c['name']} {doc}: the office sheets add up to the ordinance's GRAND TOTAL",
                            float(book["stated_total"]), sheets_sum, src, book["source_url"]))
    # school names for placing rows that name a school
    pub = sch[(sch.city == slug) & (sch.sector == "Public")]
    keys = {}
    for r in pub.itertuples():
        keys.setdefault(school_key(r.school_name), []).append(r)

    def place(name):
        k = school_key(name)
        hits = keys.get(k) or [r for kk, rs in keys.items() if kk and k and (kk.startswith(k) or k.startswith(kk)) for r in rs]
        if len({h.school_id for h in hits}) == 1:
            return hits[0], "name, exact" if keys.get(k) else "name, prefix"
        return None, ""

    out, n = [], 0
    for s in book["sheets"]:
        text = f"{s['office'] or ''} {s['unit'] or ''}"
        rule = next(((rid, dom) for rid, pat, dom in SHEET_RULES if re.search(pat, text, re.I)), None)
        basis = s.get("total_basis") or "unknown"
        confirmed = basis.startswith("two figures") or ties
        basis += "" if basis.startswith("two figures") or not ties else "; all sheets together tie to the GRAND TOTAL"
        common = dict(city=slug, cycle=f"AB{ORDINANCE_FY}", document=doc, fiscal_year=ORDINANCE_FY, status="enacted",
                      office_name=(s["office"] or "").lstrip("•").strip(), fund_sources=s.get("fund") or "", page=s.get("page"),
                      source_id=src, retrieved="", machine_read=True)
        if rule:
            n += 1
            ls = s.get("line_sums") or {}
            row = budget_row(line_id=f"{src}-p{s['page']}-{n}", name=clean_unit(s["unit"]) or s["office"], pap_class="sheet",
                             domain=rule[1], tag_rule=rule[0], ps=float(ls.get("PS") or 0), mooe=float(ls.get("MOOE") or 0),
                             co=float(ls.get("CO") or 0) + float(ls.get("FE") or 0), total=float(s["total"] or 0),
                             source_url=page_url(s["page"]), place_code=c["psgc"],
                             validation=f"machine-read; sheet total: {basis}" + ("" if confirmed else " (not confirmed)"),
                             **common)
            if rule[0] == "aid-named-school":
                hit, how = place(row["name"])
                if hit is not None:
                    row |= {"place_level": "school", "place_code": hit.psgc_barangay_code or c["psgc"], "school_ids": hit.school_id,
                            "barangay_codes": hit.psgc_barangay_code, "place_match": how}
                else:
                    gaps.append(gap(slug, "budget_school_unmatched", row["line_id"], f"{row['name']} (₱{row['total']:,.0f}): names a school, "
                                    "but no single public school in DepEd's list matches the name", src))
            out.append(row)
            continue
        for o in s["objects"]:
            lr = next(((rid, dom) for rid, pat, dom in LINE_RULES if re.search(pat, o["name"] or "", re.I)), None)
            if not lr or not o.get("amount"):
                continue
            n += 1
            cls = (o.get("class") or "").upper()
            amt = float(o["amount"])
            out.append(budget_row(line_id=f"{src}-p{o.get('page') or s['page']}-{n}", name=re.sub(r"^OMOE\s*-\s*", "", o["name"]).strip(),
                                  aip_reference_code=o.get("code") or "", pap_class=cls, domain=lr[1], tag_rule=lr[0],
                                  ps=amt if cls == "PS" else 0.0, mooe=amt if cls == "MOOE" else 0.0, co=amt if cls in ("CO", "FE") else 0.0,
                                  total=amt, source_url=page_url(o.get("page") or s["page"], o), place_code=c["psgc"],
                                  validation=f"machine-read line of a sheet whose total is: {basis}" + ("" if confirmed else " (not confirmed)"),
                                  **(common | {"page": o.get("page") or s.get("page")})))
    rows = [r for r in out if DOMAINS[r["domain"]][1]]
    checks.append(check(slug, f"{slug}-confirmed", f"{c['name']} {doc}: education and early-childhood rows come from sheets whose total is confirmed "
                        "(two printed figures agree, or the whole book ties to its GRAND TOTAL)", len(rows), sum("not confirmed" not in r["validation"] for r in rows), src, book["source_url"], unit="rows"))
    for r in out:
        if r["place_level"] == "city":
            gaps.append(gap(slug, "budget_line_no_place", r["line_id"], f"{r['name']} (₱{r['total']:,.0f}): no school ID or barangay code; city-wide only", src))
    gaps.append(gap(slug, "sef_budget_not_published", f"AB{ORDINANCE_FY}", f"{c['name']} {doc}: the ordinance is the General Fund book; the SEF's own "
                    "budget (Local School Board) isn't in it", src))
    return out


# ---------------------------------------------------------------- places
def barangays(slug: str, sch: pd.DataFrame, psgc: dict, gaps: list) -> pd.DataFrame:
    c = CITIES[slug]
    sch = sch[sch.city == slug]
    pub = sch[sch.sector == "Public"]
    cdc = {str(r["psgc_code"]).zfill(10): r["cdc_barangay"] is not None for r in E2["cities"][slug]["barangays"]}
    out = []
    for b in psgc["barangays"]:
        s = pub[pub.psgc_barangay_code == b["psgc_id"]]
        allp = sch[sch.psgc_barangay_code == b["psgc_id"]]
        if s.empty:
            gaps.append(gap(slug, "barangay_no_public_school", b["psgc_id"], f"{b['name']}: no public school listed in DepEd's 2025-26 enrollment "
                            f"({len(allp)} private)", "deped-enrollment-2025-26", resolved=True))
        if b["psgc_id"] not in cdc:
            gaps.append(gap(slug, "barangay_not_in_edcom2", b["psgc_id"], f"{b['name']}: not in the EDCOM 2 dashboard's barangay table", "edcom2-no-cdc"))
        out.append({
            "city": slug, "psgc_code": b["psgc_id"], "name": b["name"],
            "public_schools": len(s), "private_schools": int((allp.sector != "Public").sum()),
            "learners_public_2025_26": int(s.learners_2025_26.sum()), "kinder_public_2025_26": int(s.kinder_2025_26.sum()),
            "staff_city_sef_2023_24": int(s.staff_city_sef_2023_24.fillna(0).sum()),
            "ict_items_lgu_sef_2023_24": int(s.ict_items_lgu_sef_2023_24.fillna(0).sum()),
            "school_district": s.school_district.mode().iloc[0] if len(s) else "",
            "crla_schools": int(s.crla_assessed.notna().sum()),
            "crla_assessed": int(s.crla_assessed.fillna(0).sum()), "crla_low_emerging": int(s.crla_low_emerging.fillna(0).sum()),
            "crla_low_emerging_share": round(s.crla_low_emerging.sum() / s.crla_assessed.sum(), 4) if s.crla_assessed.sum() else None,
            "crla_status": "summed from school results" if s.crla_assessed.notna().any() else "no public school with CRLA results",
            "on_no_cdc_list": cdc.get(b["psgc_id"]),
            "cdc_status": "EDCOM 2 list of barangays without a CDC" if b["psgc_id"] in cdc else "barangay not in EDCOM 2's table",
            "stunting_0_59m_opt": None, "stunting_status": "city level only (OPT+ 2025)",
        })
    gaps.append(gap(slug, "eccd_indicator_not_published", "stunting_0_59m_opt", f"Stunting by barangay: OPT+ 2025 is published for {c['name']} "
                    f"as a whole only, so the column is empty for all {len(out)} barangays", "edcom2-opt-2025"))
    gaps.append(gap(slug, "eccd_indicator_not_published", "child_development_centres", "Number of child development centres per barangay: EDCOM 2 "
                    "publishes only which barangays have none, so barangays.csv carries a yes/no flag", "edcom2-no-cdc"))
    return pd.DataFrame(out)


def districts(sch: pd.DataFrame) -> pd.DataFrame:
    pub = sch[sch.sector == "Public"]
    g = pub.groupby(["city", "school_district"])
    d = pd.DataFrame({
        "public_schools": g.size(), "learners_2025_26": g.learners_2025_26.sum(), "learners_2017_18": g.learners_2017_18.sum(),
        "classrooms_instructional_2023_24": g.classrooms_instructional_2023_24.sum(), "learners_2023_24": g.learners_2023_24.sum(),
        "buildings_major_repair_or_worse_2023_24": g.buildings_major_repair_or_worse_2023_24.sum(),
        "staff_city_sef_2023_24": g.staff_city_sef_2023_24.sum(), "staff_other_lgu_2023_24": g.staff_other_lgu_2023_24.sum(),
        "ict_items_lgu_sef_2023_24": g.ict_items_lgu_sef_2023_24.sum(), "barangays": g.psgc_barangay_code.nunique(),
        "crla_schools": g.crla_assessed.count(), "crla_assessed": g.crla_assessed.sum(), "crla_low_emerging": g.crla_low_emerging.sum(),
    }).reset_index()
    ints = [col for col in d.columns if col not in ("city", "school_district")]
    d[ints] = d[ints].astype(int)
    d["crla_low_emerging_share"] = (d.crla_low_emerging / d.crla_assessed.where(d.crla_assessed > 0)).round(4)
    return d


# ---------------------------------------------------------------- stats
def city_stats(slug: str, sch, brgy, bud) -> dict:
    c = CITIES[slug]
    sch, brgy, bud = sch[sch.city == slug], brgy[brgy.city == slug], bud[bud.city == slug]
    pub = sch[sch.sector == "Public"]
    opt = E2["cities"][slug]["opt_2025_city"]
    edu = bud[bud.domain.map(lambda d: DOMAINS[d][1])]
    budgets = {}
    for cy in bud.cycle.unique():
        b, e = bud[bud.cycle == cy], edu[edu.cycle == cy]
        if slug == "naga":
            raw = json.loads((RAW / "naga" / f"{cy}.json").read_text())
            rows_in_doc, stated = len(raw["items"]), float(raw["stated_total"])
        else:
            book = json.loads((RAW / slug / f"ab-{ORDINANCE_FY}.json").read_text())
            rows_in_doc, stated = len(book["sheets"]), float(book["stated_total"])
        named = e[e.tag_rule == "aid-named-school"]  # sheets that name a school, matched or not
        budgets[cy] = {"document": b.document.iloc[0], "status": b.status.iloc[0], "machine_read": bool(b.machine_read.any()),
                       "rows_in_document": rows_in_doc, "document_total": stated, "lines_in_scope": len(b),
                       "education_ecd_total": float(e.total.sum()), "education_ecd_lines": len(e),
                       "by_domain": {d: float(v) for d, v in b.groupby("domain").total.sum().items()},
                       "sef_lines": int(b.fund_sources.str.contains("SEF").sum()),
                       "sef_total": float(b[b.fund_sources.str.contains("SEF")].total.sum()),
                       "lines_with_place_code": int((b.place_level != "city").sum()),
                       "school_named_lines": len(named), "school_named_total": float(named.total.sum()),
                       "school_named_matched": int((named.school_ids != "").sum())}
    cr = pub[pub.crla_2025_26 == "published"]
    return {
        "slug": slug, "name": c["name"], "province": c["province"], "psgc_code": c["psgc"], "deped_division": c["division"],
        "budget_source": c["budget"], "budget_page": c["budget_page"],
        "schools": {"all": len(sch), "public": len(pub), "private": int((sch.sector == "Private").sum()),
                    "suc_luc": int((~sch.sector.isin(["Public", "Private"])).sum()), "districts": int(pub.school_district.nunique())},
        "learners_public_2025_26": int(pub.learners_2025_26.sum()),
        "learners_public_2017_18": int(pub.learners_2017_18.fillna(0).sum()),
        "kinder_public_2025_26": int(pub.kinder_2025_26.sum()),
        "public_schools_in_2023_24_files": int(pub.staff_city_sef_2023_24.notna().sum()),
        "staff_city_sef_2023_24": int(pub.staff_city_sef_2023_24.fillna(0).sum()),
        "teachers_city_sef_2023_24": int(pub.teachers_city_sef_2023_24.fillna(0).sum()),
        "schools_with_city_sef_staff": int((pub.staff_city_sef_2023_24 > 0).sum()),
        "staff_other_lgu_2023_24": int(pub.staff_other_lgu_2023_24.fillna(0).sum()),
        "ict_items_lgu_sef_2023_24": int(pub.ict_items_lgu_sef_2023_24.fillna(0).sum()),
        "schools_with_lgu_sef_ict": int((pub.ict_items_lgu_sef_2023_24 > 0).sum()),
        "public_schools_with_crla": len(cr), "public_elementary_schools": int(pub.offers_es.sum()),
        "public_schools_in_deped_crla_file": int(pub.in_deped_crla_file.sum()),
        "crla": {"period": "End of SY 2025-26, as of 10 May 2026", "assessed": int(cr.crla_assessed.sum()),
                 "low_emerging": int(cr.crla_low_emerging.sum()), "high_emerging": int(cr.crla_high_emerging.sum()),
                 "at_grade_level": int(cr.crla_at_grade_level.sum()),
                 "low_emerging_share": round(cr.crla_low_emerging.sum() / cr.crla_assessed.sum(), 4),
                 "struggling_share": round((cr.crla_low_emerging.sum() + cr.crla_high_emerging.sum()) / cr.crla_assessed.sum(), 4),
                 "school_low_emerging_share_max": round(float((cr.crla_low_emerging / cr.crla_assessed).max()), 4)},
        "opt_2025_city": {"children_estimated": int(opt["Est_children"]), "children_measured": int(opt["Actual_children"]),
                          "coverage": round(float(opt["stunting_coverage"]), 3),
                          "stunted": int(opt["ST_Number"]), "severely_stunted": int(opt["SST_Number"]),
                          "stunted_or_severely": int(opt["STSST_Number"]), "stunted_or_severely_share": round(float(opt["STSST_Percent"]), 3),
                          "edcom2_measure_stunted": sum(int(opt[f"F{i}"] or 0) for i in [*range(24, 30), *range(38, 44)]),
                          "edcom2_measure_children": sum(int(opt[f"F{i}"] or 0) for i in range(10, 16))},
        "barangays": len(brgy), "barangays_with_public_school": int((brgy.public_schools > 0).sum()),
        "barangays_on_no_cdc_list": int(brgy.on_no_cdc_list.fillna(False).sum()),
        "barangays_in_edcom2": int(brgy.on_no_cdc_list.notna().sum()),
        "schools_matched_to_psgc": int((sch.psgc_barangay_code != "").sum()),
        "budget": budgets,
    }


# ---------------------------------------------------------------- outputs
FIELD_DOCS = {
    "city": "This project's city slug: naga, zamboanga or cdo",
    "school_id": "DepEd 6-digit school ID (string)", "psgc_barangay_code": "PSA 10-digit PSGC barangay code (string); empty if unmatched",
    "barangay_match": "How the DepEd barangay name was matched: name, rule (parenthetical or 'Barangay' dropped) or hand",
    "psgc_code": "PSA 10-digit PSGC code (string)", "aip_reference_code": "Naga: the City's AIP reference code; ordinance books: the account code if printed",
    "line_id": "Row ID. Naga: the row's ID on budget.naga.gov.ph. Ordinance books: city, year, page and sequence",
    "domain": "Tag from this project's rules (pipeline/build.py RULES, SHEET_RULES, LINE_RULES); tag_rule names the rule",
    "place_level": "Finest place the source states: 'school' when the row names a school, 'city' when it names none",
    "school_ids": "DepEd school ID the row names, matched by school name (place_match says how)",
    "fund_sources": "Naga: funds the portal lists (e.g. SEF, GF), empty if the row's page wasn't read. Ordinance books: the fund printed on the sheet",
    "ps": "Personal services, PHP", "mooe": "Maintenance and other operating expenses, PHP", "co": "Capital outlay (plus financial expenses), PHP",
    "total": "Row total as published (or as machine-read), PHP", "page": "Page of the ordinance PDF (ordinance books only)",
    "machine_read": "True when the figure was read by OCR from a scanned or printed PDF and hasn't been reviewed by a person",
    "staff_city_sef_2023_24": "School staff (teachers and non-teaching) paid from the City SEF, per DepEd's personnel file",
    "teachers_city_sef_2023_24": "Teachers paid from the City SEF, per DepEd's personnel file",
    "staff_other_lgu_2023_24": "School staff paid from other LGU funds, per DepEd's personnel file",
    "ict_items_lgu_sef_2023_24": "ICT equipment items DepEd lists as funded by the LGU or its SEF",
    "crla_2025_26": "'published' if the school has CRLA results in the EDCOM 2 dashboard's data, else 'not published'",
    "crla_assessed": "Learners in Grades 1-3 assessed, CRLA end of SY 2025-26 (EDCOM 2 dashboard, data from DepEd)",
    "crla_low_emerging": "Learners reading at the Low Emerging level, same source",
    "crla_low_emerging_share": "crla_low_emerging / crla_assessed",
    "in_deped_crla_file": "Whether DepEd's own machine-ready CRLA file (selected schools) has this school",
    "on_no_cdc_list": "True if the barangay is on EDCOM 2's list of barangays without a child development centre; empty if not in its table",
}


def write_table(name: str, df: pd.DataFrame, desc: str, files: list) -> None:
    df.to_csv(DATA / f"{name}.csv", index=False)
    df.to_parquet(DATA / f"{name}.parquet", index=False)
    files.append({"name": name, "description": desc, "rows": len(df), "fields": len(df.columns),
                  "schema": [{"name": col, "type": ftype(df[col]), "description": FIELD_DOCS.get(col, "")} for col in df.columns]})


def ftype(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_integer_dtype(s):
        return "integer"
    if pd.api.types.is_float_dtype(s):
        return "number"
    return "string"


def records(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records", force_ascii=False))


def main() -> None:
    manifest = json.loads((RAW / "manifest.json").read_text())
    E2.update(json.loads((RAW / "edcom2" / "cities.json").read_text()))
    gaps, checks = [], []
    src = sources(manifest)
    psgc = {slug: json.loads((RAW / "psgc" / f"{slug}.json").read_text()) for slug in CITIES}
    sch = pd.concat([schools(slug, gaps, psgc[slug]) for slug in CITIES], ignore_index=True)
    if sch.school_id.duplicated().any():
        raise RuntimeError("duplicate school_id across cities")
    lines = budget_naga(gaps, checks)
    for slug, c in CITIES.items():
        if c["budget"] == "ordinance":
            lines += budget_ordinance(slug, sch, gaps, checks)
    bud = pd.DataFrame(lines)
    brgy = pd.concat([barangays(slug, sch, psgc[slug], gaps) for slug in CITIES], ignore_index=True)
    dist = districts(sch)
    for slug, c in CITIES.items():  # EDCOM 2 data: do the published parts add up?
        e2 = E2["cities"][slug]
        ok = sum(sum(int(r[v]) for v in CRLA_BANDS.values()) == int(r["Total Assessed"]) for r in e2["crla"])
        checks.append(check(slug, f"{slug}-crla-bands", f"{c['name']} CRLA: each school's five reading levels add up to the learners it assessed",
                            len(e2["crla"]), ok, "edcom2-crla", E2["workbook"], unit="schools"))
        opt = e2["opt_2025_city"]
        checks.append(check(slug, f"{slug}-opt-st-sst", f"{c['name']} OPT+ 2025: stunted + severely stunted equals the combined count",
                            opt["STSST_Number"], opt["ST_Number"] + opt["SST_Number"], "edcom2-opt-2025", E2["workbook"], unit="children"))
        checks.append(check(slug, f"{slug}-opt-share", f"{c['name']} OPT+ 2025: the stated stunting share equals the combined count over children "
                            "measured (to the 3 decimals published)", round(opt["STSST_Percent"], 3),
                            round(opt["STSST_Number"] / opt["Actual_children"], 3), "edcom2-opt-2025", E2["workbook"], unit="share"))
    g, c = pd.DataFrame(gaps), pd.DataFrame(checks)

    stats = {
        "built_at": now(), "lgu_compare_url": LGU_COMPARE,
        "cities": {slug: city_stats(slug, sch, brgy, bud) for slug in CITIES},
        "sef_line_aip2027": records(bud[(bud.city == "naga") & (bud.cycle == "AIP2027") & bud.fund_sources.str.contains("SEF")]
                                    [["aip_reference_code", "name", "total", "ps", "mooe", "co", "source_url"]]),
        "gaps": {slug: g[g.city == slug].groupby("kind").size().to_dict() for slug in CITIES},
        "checks": int(len(c)), "checks_matching": int((c.status == "match").sum()),
        "domains": {k: {"label": v[0], "in_default_total": v[1]} for k, v in DOMAINS.items()},
    }

    files = []
    write_table("budget_lines", bud, "Education, early-childhood, nutrition and child-welfare budget rows for Naga (AB 2026, AIP 2027), "
                "Zamboanga City and Cagayan de Oro (AB 2026, machine-read), tagged by domain, fund and place", files)
    write_table("schools", sch, "Every school in DepEd's Schools Divisions of Naga City, Zamboanga City and Cagayan de Oro City, with enrollment, "
                "City-SEF-paid staff, LGU/SEF-funded ICT, facilities and CRLA", files)
    write_table("barangays", brgy, "Every barangay of the three cities (PSGC), public-school totals, CRLA, and ECCD indicator slots", files)
    write_table("districts", dist, "DepEd's school districts in the three cities, public-school totals", files)
    write_table("gaps", g, "Every record that could not be joined or has no public source: listed, not dropped", files)
    write_table("checks", c, "Reconciliation checks on the sources (totals add up, splits add up, confirmed sheets)", files)
    write_table("sources", src, "Every source, its URL, period and sha256 (where downloaded)", files)

    api = SITE / "api"
    if api.exists():
        shutil.rmtree(api)
    (api / "schools").mkdir(parents=True)
    dump = lambda p, o: (api / p).write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")))  # noqa: E731
    dump("stats.json", stats)
    dump("sources.json", {"sources": records(src)})
    dump("budget-lines.json", {"lines": records(bud)})
    dump("schools.json", {"schools": records(sch)})
    for s in records(sch):
        dump(f"schools/{s['school_id']}.json", s)
    dump("districts.json", {"districts": records(dist)})
    dump("barangays.json", {"barangays": records(brgy)})
    dump("gaps.json", {"gaps": records(g)})
    dump("checks.json", {"checks": records(c)})

    dl = SITE / "data"
    if dl.exists():
        shutil.rmtree(dl)
    dl.mkdir()
    for f in files:
        for ext in ("csv", "parquet"):
            shutil.copy(DATA / f"{f['name']}.{ext}", dl / f"{f['name']}.{ext}")
    pk = {"profile": "tabular-data-package", "name": "ph-education-spending",
          "title": "City education and early-childhood spending next to school data: Naga, Zamboanga City, Cagayan de Oro (prototype)",
          "licenses": [{"name": "ODC-BY-1.0", "path": "https://opendatacommons.org/licenses/by/1-0/"}],
          "created": stats["built_at"],
          "sources": [{"title": r.title, "path": r.url} for r in src.itertuples()],
          "resources": [{"name": f["name"], "path": f"{f['name']}.csv", "format": "csv", "mediatype": "text/csv",
                         "description": f["description"], "schema": {"fields": f["schema"]}} for f in files]}
    pk["resources"][0]["schema"]["primaryKey"] = "line_id"
    pk["resources"][1]["schema"] |= {"primaryKey": "school_id", "foreignKeys": [
        {"fields": "psgc_barangay_code", "reference": {"resource": "barangays", "fields": "psgc_code"}}]}
    pk["resources"][2]["schema"]["primaryKey"] = "psgc_code"
    pk["resources"][3]["schema"]["primaryKey"] = ["city", "school_district"]
    (dl / "datapackage.json").write_text(json.dumps(pk, ensure_ascii=False, indent=1))
    dump("catalog.json", {"files": [{**{k: f[k] for k in ("name", "description", "rows", "fields")},
                                     "formats": [{"format": ext.upper(), "path": f"data/{f['name']}.{ext}",
                                                  "bytes": (dl / f"{f['name']}.{ext}").stat().st_size} for ext in ("csv", "parquet")]}
                                    for f in files]})

    (SITE / "geo").mkdir(exist_ok=True)
    for slug in CITIES:  # barangay outlines, properties trimmed to the PSGC code
        geo = json.loads((RAW / "geo" / f"{slug}-barangays.json").read_text())
        for ft in geo["features"]:
            ft["properties"] = {"psgc_code": f"{int(ft['properties']['adm4_psgc']):010d}", "name": ft["properties"]["adm4_en"]}
        (SITE / "geo" / f"{slug}-barangays.geojson").write_text(json.dumps(geo, separators=(",", ":")))

    (DATA / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    from pipeline.openapi import write as write_openapi
    write_openapi(stats)
    for slug, s in stats["cities"].items():
        b = {cy: (v["education_ecd_total"], v["education_ecd_lines"], v["school_named_lines"], v["school_named_matched"]) for cy, v in s["budget"].items()}
        print(slug, s["schools"], s["learners_public_2025_26"], f"CRLA {s['public_schools_with_crla']}/{s['public_elementary_schools']}", b)
    print("gaps", stats["gaps"], "checks", stats["checks_matching"], "/", stats["checks"])


if __name__ == "__main__":
    main()
