"""Turn data/raw into the published tables, checks, gaps, static JSON API, OpenAPI spec and data package.

Rules this file keeps:
- Never change a source's numbers. Problems go to checks/gaps; nothing is fixed in place.
- Codes are strings (DepEd school IDs, PSGC codes, AIP reference codes).
- A record that can't be joined is listed in gaps.csv, never dropped.
- Every row carries its source_id and period; sources.csv says where each source lives.
"""

import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline.fetch import DIVISION, NAGA_PSGC, PORTAL, RAW

ROOT = RAW.parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

# ---------------------------------------------------------------- tagging rules (the schema's "domain" field)
# Each rule: (rule_id, office codes, name regex or None, domain). First match wins. Rows of these offices that
# match no rule are tagged "office_other" and still listed. The row's PAP class "GAS" marks office running costs.
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
CYCLE_DOCS = {
    "AB2026": ("Annual Budget 2026, enacted by Ord. No. 2025-131", 2026, "enacted"),
    "AIP2027": ("Annual Investment Program 2027", 2027, "proposed"),
}
# DepEd spells two barangay names differently from PSA's PSGC. Matched by hand, listed on the checks page.
BARANGAY_ALIASES = {"CONCEPCION PEQUENO": "Concepcion Pequeña", "SAN FRANCISCO (POB.)": "San Francisco"}
NOT_PUBLISHED = "not published"  # status for an indicator with no public, machine-readable source for Naga


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def fix_text(s):
    """DepEd's CSVs mix UTF-8 and Windows-1252 cells. Read as cp1252, then undo UTF-8 mojibake per cell."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def read_deped(name: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / "deped" / name, encoding="cp1252", dtype=str, keep_default_na=False, low_memory=False)
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(fix_text)
    return df


def num(df: pd.DataFrame, cols) -> pd.Series:
    return df[list(cols)].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1).astype(int)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- sources
def sources(manifest: dict) -> pd.DataFrame:
    dep = manifest
    rows = [
        ("deped-enrollment-2025-26", "Enrollment in SY 2025-2026 (school level)", "DepEd, Project Bukas machine-ready files",
         dep["deped/enrollment_2025-26.csv"]["url"], "SY 2025-26", "used", dep["deped/enrollment_2025-26.csv"]["sha256"]),
        ("deped-enrollment-2023-24", "Enrollment in SY 2023-2024 (school level)", "DepEd, Project Bukas machine-ready files",
         dep["deped/enrollment_2023-24.csv"]["url"], "SY 2023-24", "used", dep["deped/enrollment_2023-24.csv"]["sha256"]),
        ("deped-enrollment-2017-18", "Enrollment in SY 2017-2018 (school level)", "DepEd, Project Bukas machine-ready files",
         dep["deped/enrollment_2017-18.csv"]["url"], "SY 2017-18", "used", dep["deped/enrollment_2017-18.csv"]["sha256"]),
        ("deped-personnel-2023-24", "School Personnel in SY 2023-2024, incl. locally funded staff by fund", "DepEd, Project Bukas machine-ready files",
         dep["deped/personnel_2023-24.csv"]["url"], "SY 2023-24", "used", dep["deped/personnel_2023-24.csv"]["sha256"]),
        ("deped-ict-2023-24", "ICT Data in SY 2023-2024, incl. equipment by funding source", "DepEd, Project Bukas machine-ready files",
         dep["deped/ict_2023-24.csv"]["url"], "SY 2023-24", "used", dep["deped/ict_2023-24.csv"]["sha256"]),
        ("deped-facilities-2023-24", "School Facilities in SY 2023-2024", "DepEd, Project Bukas machine-ready files",
         dep["deped/facilities_2023-24.csv"]["url"], "SY 2023-24", "used", dep["deped/facilities_2023-24.csv"]["sha256"]),
        ("deped-crla-2025-26", "Comprehensive Rapid Literacy Assessment (CRLA) 2025-2026, selected schools", "DepEd, Project Bukas machine-ready files",
         dep["deped/crla_2025-26_selected.csv"]["url"], "SY 2025-26", "checked: no Naga schools", dep["deped/crla_2025-26_selected.csv"]["sha256"]),
        ("deped-ellna-2023-24", "ELLNA 2023-2024, selected schools", "DepEd, Project Bukas machine-ready files",
         dep["deped/ellna_2023-24_selected.csv"]["url"], "SY 2023-24", "checked: no Naga schools", dep["deped/ellna_2023-24_selected.csv"]["sha256"]),
        ("deped-nat-2023-24", "NAT Grade 6 2023-2024, selected schools", "DepEd, Project Bukas machine-ready files",
         dep["deped/nat_2023-24_selected.csv"]["url"], "SY 2023-24", "checked: no Naga schools", dep["deped/nat_2023-24_selected.csv"]["sha256"]),
        ("naga-ab2026", "Annual Budget 2026 (Ord. No. 2025-131), public Browse page", "City Government of Naga, People's Budget Portal",
         manifest["naga/AB2026.json"]["url"], "FY 2026", "used", manifest["naga/AB2026.json"]["sha256"]),
        ("naga-aip2027", "Annual Investment Program 2027, public Browse page", "City Government of Naga, People's Budget Portal",
         manifest["naga/AIP2027.json"]["url"], "FY 2027", "used", manifest["naga/AIP2027.json"]["sha256"]),
        ("psgc-2026", "Philippine Standard Geographic Code, 2026 (via bendlikeabamboo/barangay)", "Philippine Statistics Authority",
         manifest["psgc/naga.json"]["url"], "2026", "used", manifest["psgc/naga.json"]["sha256"]),
        ("faeldon-geo", "Barangay boundaries, medium resolution (philippines-json-maps)", "faeldon/philippines-json-maps (MIT)",
         manifest["geo/naga-barangays.json"]["url"], "release v1.1.1", "used", manifest["geo/naga-barangays.json"]["sha256"]),
        ("edcom2-eccd-dashboard", "EDCOM 2 Early Childhood Dashboard", "EDCOM 2 with AC Analytics",
         "https://edcom2.gov.ph/eccddashboard/", "launched Aug 2026", "checked: behind a bot check, no download or API found", ""),
        ("nnc-opt-plus", "Operation Timbang Plus (OPT+) results by barangay", "National Nutrition Council",
         "https://www.nnc.gov.ph/", "annual", "checked: no barangay-level file for Naga found", ""),
        ("cbms", "Community-Based Monitoring System", "Philippine Statistics Authority",
         "https://psa.gov.ph/", "2024 round", "checked: no barangay-level child development centre table for Naga found", ""),
    ]
    return pd.DataFrame(rows, columns=["source_id", "title", "publisher", "url", "period", "status", "sha256"])


# ---------------------------------------------------------------- schools
def schools(gaps: list, psgc: dict) -> pd.DataFrame:
    e25 = read_deped("enrollment_2025-26.csv")
    e25 = e25[e25.division == DIVISION].copy()
    if e25.empty:
        raise RuntimeError(f"no schools for division {DIVISION!r}: DepEd renamed it?")
    grade_cols = [c for c in e25.columns if re.match(r"^(kinder|g\d+|esng|jhsng)_", c)]
    e25["learners_2025_26"] = num(e25, grade_cols)
    e25["kinder_2025_26"] = num(e25, ["kinder_male", "kinder_female"])
    ids = set(e25.school_id)

    def total(name):
        d = read_deped(name)
        d = d[d.school_id.isin(ids)]
        return d.set_index("school_id").pipe(lambda x: num(x, [c for c in x.columns if re.match(r"^(kinder|g\d+|esng|jhsng)_", c)]))

    e23, e17 = total("enrollment_2023-24.csv"), total("enrollment_2017-18.csv")

    per = read_deped("personnel_2023-24.csv").set_index("school_id")
    per = per[per.index.isin(ids)]
    sef_city = [c for c in per.columns if re.search(r"sef_municipal(ity)?_city$", c)]
    lgu = [c for c in per.columns if c.endswith("lgu_funding")]
    teach_sef = [c for c in sef_city if "_teachers_" in c]
    ict = read_deped("ict_2023-24.csv").set_index("school_id")
    ict = ict[ict.index.isin(ids)]
    fac = read_deped("facilities_2023-24.csv").set_index("school_id")
    fac = fac[fac.index.isin(ids)]

    crla = set(read_deped("crla_2025-26_selected.csv").school_id)

    by_name = {fold(b["name"]): b for b in psgc["barangays"]}
    aliases = {k: next(b for b in psgc["barangays"] if b["name"] == v) for k, v in BARANGAY_ALIASES.items()}

    out = []
    for r in e25.itertuples():
        sid = r.school_id
        b = by_name.get(fold(r.barangay)) or aliases.get(fold(r.barangay))
        if b is None:
            gaps.append(gap("barangay_unmatched", sid, f"{r.school_name}: DepEd barangay {r.barangay!r} matches no PSGC barangay of Naga",
                            "deped-enrollment-2025-26"))
        elif fold(r.barangay) in aliases:
            gaps.append(gap("barangay_alias", sid, f"{r.school_name}: DepEd's {r.barangay!r} matched by hand to PSGC {b['name']!r} ({b['psgc_id']})",
                            "deped-enrollment-2025-26", resolved=True))
        in23 = sid in per.index
        if not in23:
            gaps.append(gap("school_not_in_2023_24", sid, f"{r.school_name} ({r.sector}) is in DepEd's 2025-26 enrollment but not in the "
                            "2023-24 personnel, ICT and facilities files (new school or new ID)", "deped-personnel-2023-24"))
        cls = num(fac.loc[[sid]], ["es_classrooms_instructional", "jhs_classrooms_instructional", "shs_classrooms_instructional"]).iloc[0] if sid in fac.index else None
        out.append({
            "school_id": sid, "school_name": r.school_name, "sector": r.sector, "management": r.school_management,
            "school_district": r.school_district, "barangay_deped": r.barangay,
            "psgc_barangay_code": b["psgc_id"] if b else "", "psgc_barangay_name": b["name"] if b else "",
            "offers_es": r.offers_es == "Yes", "offers_jhs": r.offers_jhs == "Yes", "offers_shs": r.offers_shs == "Yes",
            "learners_2025_26": int(r.learners_2025_26), "kinder_2025_26": int(r.kinder_2025_26),
            "learners_2023_24": int(e23[sid]) if sid in e23.index else None,
            "learners_2017_18": int(e17[sid]) if sid in e17.index else None,
            "classrooms_instructional_2023_24": int(cls) if cls is not None else None,
            "buildings_major_repair_or_worse_2023_24": int(num(fac.loc[[sid]], ["buildings_needs_major_repair", "buildings_for_condemnation", "buildings_for_demolition"]).iloc[0]) if sid in fac.index else None,
            "makeshift_rooms_2023_24": int(num(fac.loc[[sid]], ["es_makeshift_rooms", "hs_makeshift_rooms"]).iloc[0]) if sid in fac.index else None,
            "staff_city_sef_2023_24": int(num(per.loc[[sid]], sef_city).iloc[0]) if in23 else None,
            "teachers_city_sef_2023_24": int(num(per.loc[[sid]], teach_sef).iloc[0]) if in23 else None,
            "staff_other_lgu_2023_24": int(num(per.loc[[sid]], lgu).iloc[0]) if in23 else None,
            "ict_items_lgu_sef_2023_24": int(num(ict.loc[[sid]], [c for c in ict.columns if c.endswith("_lgu_sef")]).iloc[0]) if sid in ict.index else None,
            "crla_2025_26": "published" if sid in crla else NOT_PUBLISHED,
            "source_ids": "deped-enrollment-2025-26 deped-personnel-2023-24 deped-ict-2023-24 deped-facilities-2023-24",
        })
        if r.sector == "Public" and sid not in crla:
            gaps.append(gap("crla_not_published", sid, f"{r.school_name}: no row in DepEd's machine-ready CRLA 2025-26 file "
                            "(the file covers selected schools in CAR and Regions I, III, VIII and IX only)", "deped-crla-2025-26"))
    df = pd.DataFrame(out)
    df["learners_per_classroom_2023_24"] = (df.learners_2023_24 / df.classrooms_instructional_2023_24.where(df.classrooms_instructional_2023_24 > 0)).round(1)
    if df.school_id.duplicated().any():
        raise RuntimeError("duplicate school_id in DepEd's enrollment file")
    return df


def gap(kind, record, detail, source_id, resolved=False) -> dict:
    return {"kind": kind, "record_id": record, "detail": detail, "source_id": source_id, "resolved": resolved}


# ---------------------------------------------------------------- budget lines
def budget(gaps: list, checks: list) -> pd.DataFrame:
    out = []
    for cycle, (doc, fy, status) in CYCLE_DOCS.items():
        raw = json.loads((RAW / "naga" / f"{cycle}.json").read_text())
        items = raw["items"]
        stated = float(raw["stated_total"])
        summed = round(sum(float(i["proposedTotal"]) for i in items), 2)
        checks.append(check(f"{cycle}-total", f"{doc}: rows on the public Browse page add up to the page's stated total",
                            stated, summed, f"naga-{cycle.lower()}", raw["url"]))
        split = lambda i: round(sum(float(i[k]) for k in ("psTotal", "mooeTotal", "feTotal", "coTotal")), 2)  # noqa: E731
        unsplit = [i for i in items if split(i) == 0 and float(i["proposedTotal"]) != 0]  # declared as a total, no split
        has_split = [i for i in items if i not in unsplit]
        bad_split = [i for i in has_split if split(i) != float(i["proposedTotal"])]
        checks.append(check(f"{cycle}-split", f"{doc}: PS + MOOE + FE + CO equals the row's total, for every row that gives a split "
                            f"({len(unsplit)} rows give only a total)",
                            len(has_split), len(has_split) - len(bad_split), f"naga-{cycle.lower()}", raw["url"], unit="rows"))
        for i in items:
            off = i["office"]["acronym"]
            det = raw["details"].get(i["id"])
            domain, rule = None, None
            for rid, offices, pat, dom in RULES:
                if off in offices and (pat is None or re.search(pat, i["name"], re.I)):
                    domain, rule = dom, rid
                    break
            if domain is None and det is None:
                continue  # outside the offices in scope
            if domain is None:
                domain, rule = "office_other", "office-in-scope"
            funds = det.get("fundSources") if det else None
            url = f"{PORTAL}/budget/{i['id']}"
            out.append({
                "line_id": i["id"], "cycle": cycle, "document": doc, "fiscal_year": fy, "status": status,
                "aip_reference_code": i["aipReferenceCode"], "office_code": off, "office_name": i["office"]["name"],
                "name": i["name"].strip(), "pap_class": i["papClass"], "domain": domain, "tag_rule": rule,
                "fund_sources": " ".join(funds) if funds else "",
                "thematic_tags": " ".join(t["name"] for t in (det or {}).get("thematicTags") or [] if isinstance(t, dict)),
                "ps": float(i["psTotal"]), "mooe": float(i["mooeTotal"]), "co": float(i["coTotal"]) + float(i["feTotal"]),
                "total": float(i["proposedTotal"]), "finish_line": (i.get("finishLine") or {}).get("name", ""),
                "place_level": "city", "place_code": NAGA_PSGC, "school_ids": "", "barangay_codes": "",
                "source_id": f"naga-{cycle.lower()}", "source_url": url, "retrieved": raw["retrieved"][:10],
                "validation": "as published on the City's portal; enacted figures match the printed ordinance per the portal" if status == "enacted"
                              else "as published on the City's portal; proposed, not yet enacted",
            })
            gaps.append(gap("budget_line_no_place", i["id"], f"{cycle} {i['aipReferenceCode']} {i['name'].strip()} "
                            f"(₱{float(i['proposedTotal']):,.0f}): no school ID or barangay code; city-wide only", f"naga-{cycle.lower()}"))
    df = pd.DataFrame(out)
    # The SEF itself: in 2027 one AIP line carries it; the enacted 2026 General Fund book has no SEF row at all.
    for cycle in CYCLE_DOCS:
        sef = df[(df.cycle == cycle) & df.fund_sources.str.contains("SEF")]
        if sef.empty:
            gaps.append(gap("sef_budget_not_published", cycle, f"{CYCLE_DOCS[cycle][0]}: none of the rows read (the offices in scope) lists the SEF as a fund"
                            + (", and the enacted rows carry no fund field at all" if CYCLE_DOCS[cycle][2] == "enacted" else "")
                            + ". The SEF has its own budget, approved through the Local School Board, which the portal does not carry.",
                            f"naga-{cycle.lower()}"))
    return df


def check(cid, what, expected, actual, source_id, url, unit="PHP") -> dict:
    return {"check_id": cid, "what": what, "expected": expected, "actual": actual, "unit": unit,
            "status": "match" if abs(float(expected) - float(actual)) < 0.005 else "mismatch", "source_id": source_id, "url": url}


# ---------------------------------------------------------------- places
def barangays(sch: pd.DataFrame, psgc: dict, gaps: list) -> pd.DataFrame:
    pub = sch[sch.sector == "Public"]
    out = []
    for b in psgc["barangays"]:
        s = pub[pub.psgc_barangay_code == b["psgc_id"]]
        allp = sch[sch.psgc_barangay_code == b["psgc_id"]]
        if s.empty:
            gaps.append(gap("barangay_no_public_school", b["psgc_id"], f"{b['name']}: no public school listed in DepEd's 2025-26 enrollment "
                            f"({len(allp)} private)", "deped-enrollment-2025-26", resolved=True))
        out.append({
            "psgc_code": b["psgc_id"], "name": b["name"],
            "public_schools": len(s), "private_schools": int((allp.sector != "Public").sum()),
            "learners_public_2025_26": int(s.learners_2025_26.sum()), "kinder_public_2025_26": int(s.kinder_2025_26.sum()),
            "staff_city_sef_2023_24": int(s.staff_city_sef_2023_24.fillna(0).sum()),
            "ict_items_lgu_sef_2023_24": int(s.ict_items_lgu_sef_2023_24.fillna(0).sum()),
            "school_district": s.school_district.mode().iloc[0] if len(s) else "",
            # ECCD indicators: the slots exist so the joins are ready; no public machine-readable source for Naga yet.
            "stunting_0_59m_opt": None, "stunting_status": NOT_PUBLISHED,
            "child_development_centres": None, "cdc_status": NOT_PUBLISHED,
            "crla_low_emerging_share": None, "crla_status": NOT_PUBLISHED,
        })
    for ind, src in (("stunting_0_59m_opt", "nnc-opt-plus"), ("child_development_centres", "cbms"),
                     ("crla_low_emerging_share", "deped-crla-2025-26")):
        gaps.append(gap("eccd_indicator_not_published", ind, f"{ind}: no public, machine-readable barangay figure for Naga's "
                        f"{len(out)} barangays; the column is empty in barangays.csv", src))
    return pd.DataFrame(out)


def districts(sch: pd.DataFrame) -> pd.DataFrame:
    pub = sch[sch.sector == "Public"]
    g = pub.groupby("school_district")
    return pd.DataFrame({
        "public_schools": g.size(), "learners_2025_26": g.learners_2025_26.sum(), "learners_2017_18": g.learners_2017_18.sum(),
        "classrooms_instructional_2023_24": g.classrooms_instructional_2023_24.sum(),
        "learners_2023_24": g.learners_2023_24.sum(),
        "buildings_major_repair_or_worse_2023_24": g.buildings_major_repair_or_worse_2023_24.sum(),
        "staff_city_sef_2023_24": g.staff_city_sef_2023_24.sum(), "staff_other_lgu_2023_24": g.staff_other_lgu_2023_24.sum(),
        "ict_items_lgu_sef_2023_24": g.ict_items_lgu_sef_2023_24.sum(),
        "barangays": g.psgc_barangay_code.nunique(),
    }).reset_index().astype({c: int for c in ["public_schools", "learners_2025_26", "learners_2017_18", "classrooms_instructional_2023_24",
                                               "learners_2023_24", "buildings_major_repair_or_worse_2023_24", "staff_city_sef_2023_24",
                                               "staff_other_lgu_2023_24", "ict_items_lgu_sef_2023_24", "barangays"]})


# ---------------------------------------------------------------- outputs
FIELD_DOCS = {
    "school_id": "DepEd 6-digit school ID (string)", "psgc_barangay_code": "PSA 10-digit PSGC barangay code (string); empty if unmatched",
    "psgc_code": "PSA 10-digit PSGC code (string)", "aip_reference_code": "The City's AIP reference code, as printed",
    "line_id": "The row's ID on budget.naga.gov.ph; its public page is source_url",
    "domain": "Tag from this project's rules (pipeline/build.py RULES); tag_rule names the rule",
    "place_level": "Finest place the source states: 'city' means no school or barangay is named",
    "fund_sources": "Funds the City's portal lists for the row (e.g. SEF, GF); empty if the row's page wasn't read",
    "ps": "Personal services, PHP", "mooe": "Maintenance and other operating expenses, PHP", "co": "Capital outlay (plus financial expenses), PHP",
    "total": "Row total as published, PHP",
    "staff_city_sef_2023_24": "School staff (teachers and non-teaching) paid from the City SEF, per DepEd's personnel file",
    "teachers_city_sef_2023_24": "Teachers paid from the City SEF, per DepEd's personnel file",
    "staff_other_lgu_2023_24": "School staff paid from other LGU funds, per DepEd's personnel file",
    "ict_items_lgu_sef_2023_24": "ICT equipment items DepEd lists as funded by the LGU or its SEF",
    "crla_2025_26": "'published' if the school has a row in DepEd's machine-ready CRLA file, else 'not published'",
}


def write_table(name: str, df: pd.DataFrame, desc: str, files: list) -> None:
    out = DATA / f"{name}.csv"
    df.to_csv(out, index=False)
    df.to_parquet(DATA / f"{name}.parquet", index=False)
    files.append({"name": name, "description": desc, "rows": len(df), "fields": len(df.columns),
                  "schema": [{"name": c, "type": ftype(df[c]), "description": FIELD_DOCS.get(c, "")} for c in df.columns]})


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
    psgc = json.loads((RAW / "psgc" / "naga.json").read_text())
    gaps, checks = [], []
    src = sources(manifest)
    sch = schools(gaps, psgc)
    bud = budget(gaps, checks)
    brgy = barangays(sch, psgc, gaps)
    dist = districts(sch)
    g = pd.DataFrame(gaps)
    c = pd.DataFrame(checks)

    # cross-source observations (questions, not verdicts)
    sef_aip = bud[(bud.cycle == "AIP2027") & bud.fund_sources.str.contains("SEF")]
    pub = sch[sch.sector == "Public"]
    edu = bud[bud.domain.map(lambda d: DOMAINS[d][1])]

    stats = {
        "built_at": now(),
        "city": {"name": "City of Naga, Camarines Sur", "psgc_code": NAGA_PSGC, "deped_division": DIVISION},
        "schools": {"all": len(sch), "public": len(pub), "private": int((sch.sector == "Private").sum()),
                    "suc_luc": int((~sch.sector.isin(["Public", "Private"])).sum()),
                    "districts": int(pub.school_district.nunique())},
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
        "public_schools_with_crla": int((pub.crla_2025_26 == "published").sum()),
        "barangays": len(brgy), "barangays_with_public_school": int((brgy.public_schools > 0).sum()),
        "schools_matched_to_psgc": int((sch.psgc_barangay_code != "").sum()),
        "budget": {cy: {"rows_on_portal": json.loads((RAW / "naga" / f"{cy}.json").read_text())["items"].__len__(),
                        "portal_total": float(json.loads((RAW / "naga" / f"{cy}.json").read_text())["stated_total"]),
                        "lines_in_scope": int((bud.cycle == cy).sum()),
                        "education_ecd_total": float(edu[edu.cycle == cy].total.sum()),
                        "education_ecd_lines": int((edu.cycle == cy).sum()),
                        "by_domain": {d: float(v) for d, v in bud[bud.cycle == cy].groupby("domain").total.sum().items()},
                        "sef_lines": int((bud[bud.cycle == cy].fund_sources.str.contains("SEF")).sum()),
                        "sef_total": float(bud[(bud.cycle == cy) & bud.fund_sources.str.contains("SEF")].total.sum()),
                        "lines_with_place_code": int(((bud.cycle == cy) & (bud.place_level != "city")).sum())}
                   for cy in CYCLE_DOCS},
        "sef_line_aip2027": records(sef_aip[["aip_reference_code", "name", "total", "ps", "mooe", "co", "source_url"]]),
        "gaps": g.groupby("kind").size().to_dict(),
        "checks": int(len(c)), "checks_matching": int((c.status == "match").sum()),
        "domains": {k: {"label": v[0], "in_default_total": v[1]} for k, v in DOMAINS.items()},
    }

    files = []
    write_table("budget_lines", bud, "Naga City education, early-childhood, nutrition and child-welfare budget rows (AB 2026 enacted, AIP 2027), tagged by domain and fund", files)
    write_table("schools", sch, "Every school in DepEd's Schools Division of Naga City, with enrollment, City-SEF-paid staff, LGU/SEF-funded ICT and facilities", files)
    write_table("barangays", brgy, "Naga's 27 barangays (PSGC), public-school totals, and ECCD indicator slots (empty where not published)", files)
    write_table("districts", dist, "DepEd's four school districts in Naga, public-school totals", files)
    write_table("gaps", g, "Every record that could not be joined or has no public source: listed, not dropped", files)
    write_table("checks", c, "Reconciliation checks on the sources (totals add up, splits add up)", files)
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

    # data package + catalog
    dl = SITE / "data"
    if dl.exists():
        shutil.rmtree(dl)
    dl.mkdir()
    for f in files:
        for ext in ("csv", "parquet"):
            shutil.copy(DATA / f"{f['name']}.{ext}", dl / f"{f['name']}.{ext}")
    pk = {"profile": "tabular-data-package", "name": "ph-education-spending-naga",
          "title": "Naga City education and early-childhood spending next to school data (prototype)",
          "licenses": [{"name": "ODC-BY-1.0", "path": "https://opendatacommons.org/licenses/by/1-0/"}],
          "created": stats["built_at"],
          "sources": [{"title": r.title, "path": r.url} for r in src.itertuples()],
          "resources": [{"name": f["name"], "path": f"{f['name']}.csv", "format": "csv", "mediatype": "text/csv",
                         "description": f["description"], "schema": {"fields": f["schema"]}} for f in files]}
    pk["resources"][0]["schema"]["primaryKey"] = "line_id"
    pk["resources"][1]["schema"] |= {"primaryKey": "school_id", "foreignKeys": [
        {"fields": "psgc_barangay_code", "reference": {"resource": "barangays", "fields": "psgc_code"}}]}
    pk["resources"][2]["schema"]["primaryKey"] = "psgc_code"
    (dl / "datapackage.json").write_text(json.dumps(pk, ensure_ascii=False, indent=1))
    dump("catalog.json", {"files": [{**{k: f[k] for k in ("name", "description", "rows", "fields")},
                                     "formats": [{"format": ext.upper(), "path": f"data/{f['name']}.{ext}",
                                                  "bytes": (dl / f"{f['name']}.{ext}").stat().st_size} for ext in ("csv", "parquet")]}
                                    for f in files]})

    # map: Naga's barangays only, properties trimmed to the PSGC code
    geo = json.loads((RAW / "geo" / "naga-barangays.json").read_text())
    for ft in geo["features"]:
        ft["properties"] = {"psgc_code": f"{int(ft['properties']['adm4_psgc']):010d}", "name": ft["properties"]["adm4_en"]}
    (SITE / "geo").mkdir(exist_ok=True)
    (SITE / "geo" / "naga-barangays.geojson").write_text(json.dumps(geo, separators=(",", ":")))

    (DATA / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    from pipeline.openapi import write as write_openapi
    write_openapi(stats)
    print(json.dumps({k: stats[k] for k in ("schools", "learners_public_2025_26", "staff_city_sef_2023_24", "budget", "gaps")}, indent=1, default=str))


if __name__ == "__main__":
    main()
