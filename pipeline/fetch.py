"""Download every source into data/raw and record URL, date and sha256 in data/raw/manifest.json.

Sources (all public, no login):
- DepEd's machine-ready files (Project Bukas): school-level enrollment, personnel, ICT, facilities, CRLA.
- PSA's PSGC (2026), as parsed by github.com/bendlikeabamboo/barangay (MIT).
- Barangay boundaries, github.com/faeldon/philippines-json-maps (MIT).
- Naga City's People's Budget Portal, budget.naga.gov.ph: the public Browse pages of the enacted 2026 budget and
  the 2027 AIP, and the public page of each education, early-childhood, nutrition and child-welfare row. These are
  the pages any resident's browser receives. The portal's bulk open-data API is switched off for both years by the
  City, so it is not used.
- EDCOM 2's Early Childhood Dashboard is a public Tableau workbook on public.tableau.com whose author allows
  downloads and data access. The workbook is read there (not through edcom2.gov.ph's bot check) and only Naga's
  rows are kept: school CRLA, the city's OPT+ 2025 row, and the barangay-to-"no CDC" match.
"""

import hashlib
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
UA = {"User-Agent": "Mozilla/5.0 (open-data prototype; ph-education-spending)"}

DEPED_PAGE = "https://www.deped.gov.ph/machine-ready-files/"
DEPED_FILES = {  # file we keep -> zip it comes in (names as DepEd publishes them)
    "enrollment_2025-26.csv": "Enrollment-in-SY-2025-2026.zip",
    "enrollment_2023-24.csv": "Enrollment-in-SY-2023-2024.zip",
    "enrollment_2017-18.csv": "Enrollment-in-SY-2017-2018.zip",
    "personnel_2023-24.csv": "School-Personnel-in-SY-2023-2024.zip",
    "ict_2023-24.csv": "ICT-Data-in-SY-2023-2024.zip",
    "facilities_2023-24.csv": "School-Facilities-in-SY-2023-2024.zip",
    "crla_2025-26_selected.csv": "Comprehensive-Rapid-Literacy-Assessment-CRLA-2025-2026.zip",
    "ellna_2023-24_selected.csv": "Early-Language-Literacy-and-Numeracy-Assessment-ELLNA.zip",
    "nat_2023-24_selected.csv": "National-Achievement-Test-NAT-Grade-6-2023-2024.zip",
}
# The cities this prototype covers. budget: "portal" = Naga's People's Budget Portal (public pages);
# "ordinance" = the city's own appropriation ordinance PDF, machine-read by Stride's lgu-intel parsers.
CITIES = {
    "naga": {"name": "City of Naga", "province": "Camarines Sur", "psgc": "0501724000", "division": "Naga City", "budget": "portal",
             "budget_page": "https://peoples-budget.stridetech.workers.dev/lgus/naga"},
    "zamboanga": {"name": "City of Zamboanga", "province": "Zamboanga del Sur (independent)", "psgc": "0931700000",
                  "division": "Zamboanga City", "budget": "ordinance", "intel": "zamboanga",
                  "budget_page": "https://peoples-budget.stridetech.workers.dev/lgus/zamboanga"},
    "cdo": {"name": "City of Cagayan de Oro", "province": "Misamis Oriental (independent)", "psgc": "1030500000",
            "division": "Cagayan de Oro City", "budget": "ordinance", "intel": "cdo",
            "budget_page": "https://peoples-budget.stridetech.workers.dev/lgus/cagayan-de-oro"},
}
ORDINANCE_FY = 2026  # latest enacted year in both ordinance books (Zamboanga's FY 2027 reads at 76%, too low)
LGU_COMPARE = "https://peoples-budget.stridetech.workers.dev/lgus/explore"  # Stride's LGU budget comparison pages
LGU_INTEL = Path.home() / "Documents/GitHub/stride/stride-lgu-intel/data/budgets"
DIVISION = CITIES["naga"]["division"]

PSGC_TAG = "v2026.10.12.0"
PSGC_URL = f"https://raw.githubusercontent.com/bendlikeabamboo/barangay/{PSGC_TAG}/barangay/data/barangay_flat.json"
NAGA_PSGC = CITIES["naga"]["psgc"]

GEO_TAG = "v1.1.1"
GEO_URL = f"https://github.com/faeldon/philippines-json-maps/releases/download/{GEO_TAG}/geojson-medres.zip"
GEO_FILE = "geojson/municities/medres/bgysubmuns-municity-{code}.0.01.json"  # faeldon drops the leading zero

PORTAL = "https://budget.naga.gov.ph"
CYCLES = {"AB2026": "/annual/2026/browse", "AIP2027": "/aip/2027/browse"}
# Offices whose rows get their public page read (for fund sources and thematic tags). Everything else is read
# from the Browse page alone. ponytail: office list, not all 854 pages; widen when the tagging rules need it.
DETAIL_OFFICES = {"ESSO", "ECCDDO", "RSRL", "BSTC", "CCN", "CPNO", "CSWDO", "NCCAO"}


EDCOM2_WB = "EDCOM-dashboard_17847969310080"
EDCOM2_PAGE = "https://edcom2.gov.ph/eccddashboard/"


def get(url: str, tries: int = 3) -> bytes:
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def rsc(html: str) -> str:
    """The React Server Components payload a Next.js page carries, joined back into one string."""
    parts = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    if not parts:
        raise RuntimeError("no RSC payload: the portal's page layout changed")
    return "".join(json.loads(f'"{p}"') for p in parts)


def json_after(text: str, key: str):
    i = text.find(f'"{key}":')
    if i < 0:
        raise RuntimeError(f'"{key}" not found: the portal\'s page layout changed')
    return json.JSONDecoder().raw_decode(text[i + len(key) + 3:])[0]


def fetch_deped(manifest: dict) -> None:
    page = get(DEPED_PAGE).decode("utf-8", "replace")
    urls = {u.rsplit("/", 1)[-1]: u for u in re.findall(r'data-download-url="(https://[^"]+\.zip)"', page)}
    out = RAW / "deped"
    out.mkdir(parents=True, exist_ok=True)
    for name, zname in DEPED_FILES.items():
        if zname not in urls:
            raise RuntimeError(f"{zname} is no longer listed on {DEPED_PAGE}")
        blob = get(urls[zname])
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            member = next(m for m in z.namelist() if m.endswith("/" + name))
            readme = next((m for m in z.namelist() if m.endswith("README.md")), None)
            data = z.read(member)
            (out / name).write_bytes(data)  # gitignored; the division slice is what build.py keeps
            if readme:
                (out / (name.rsplit(".", 1)[0] + ".README.md")).write_bytes(z.read(readme))
        manifest[f"deped/{name}"] = {"url": urls[zname], "page": DEPED_PAGE, "zip_sha256": sha(blob),
                                     "sha256": sha(data), "bytes": len(data)}
        print(f"deped {name}: {len(data):,} bytes")


def fetch_psgc(manifest: dict) -> None:
    blob = get(PSGC_URL)
    places = json.loads(blob)
    (RAW / "psgc").mkdir(parents=True, exist_ok=True)
    for slug, c in CITIES.items():
        rows = [p for p in places if p["parent_psgc_id"] == c["psgc"] and p["type"] == "barangay"]
        city = next(p for p in places if p["psgc_id"] == c["psgc"])
        (RAW / "psgc" / f"{slug}.json").write_text(json.dumps({"city": city, "barangays": rows}, ensure_ascii=False, indent=1))
        manifest[f"psgc/{slug}.json"] = {"url": PSGC_URL, "sha256": sha(blob), "barangays": len(rows)}
        print(f"psgc {slug}: {len(rows)} barangays")


def fetch_geo(manifest: dict) -> None:
    blob = get(GEO_URL)
    (RAW / "geo").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for slug, c in CITIES.items():
            member = GEO_FILE.format(code=c["psgc"].lstrip("0"))
            data = z.read(member)
            (RAW / "geo" / f"{slug}-barangays.json").write_bytes(data)
            manifest[f"geo/{slug}-barangays.json"] = {"url": GEO_URL, "member": member, "sha256": sha(data)}
    print("geo: ok")


def fetch_portal(manifest: dict) -> None:
    out = RAW / "naga"
    out.mkdir(parents=True, exist_ok=True)
    for cycle, path in CYCLES.items():
        html = get(PORTAL + path).decode()
        p = rsc(html)
        items = json_after(p, "initialItems")
        total = json_after(p, "initialTotalBudget")
        if len(items) != json_after(p, "initialTotal"):
            raise RuntimeError(f"{cycle}: Browse page lists fewer rows than its own total")
        details = {}
        for it in items:
            if it["office"]["acronym"] not in DETAIL_OFFICES:
                continue
            prog = json_after(rsc(get(f"{PORTAL}/budget/{it['id']}").decode()), "program")
            details[it["id"]] = {k: prog.get(k) for k in (
                "fundSources", "thematicTags", "description", "expectedOutput", "publishedAt", "papSector",
                "projectActivities", "fundAllocations")}
            time.sleep(0.5)  # be gentle with the City's server
        doc = {"cycle": cycle, "url": PORTAL + path, "retrieved": now(), "stated_total": total,
               "items": items, "details": details}
        body = json.dumps(doc, ensure_ascii=False, indent=1).encode()
        (out / f"{cycle}.json").write_bytes(body)
        manifest[f"naga/{cycle}.json"] = {"url": PORTAL + path, "sha256": sha(html.encode()), "rows": len(items),
                                          "detail_pages": len(details)}
        print(f"portal {cycle}: {len(items)} rows, {len(details)} detail pages")


def fetch_edcom2(manifest: dict) -> None:
    from tableauhyperapi import Connection, HyperProcess, Telemetry  # only this step needs it

    meta = json.loads(get(f"https://public.tableau.com/profile/api/single_workbook/{EDCOM2_WB}?"))
    if not meta.get("allowDataAccess"):
        raise RuntimeError("EDCOM 2's workbook no longer allows data access; stop and ask EDCOM 2")
    blob = get(f"https://public.tableau.com/workbooks/{EDCOM2_WB}.twb")
    out = RAW / "edcom2"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        twb = z.read(next(m for m in z.namelist() if m.endswith(".twb"))).decode()
        hyper = out / "extract.hyper"  # gitignored; the Naga slice below is what build.py reads
        hyper.write_bytes(z.read(next(m for m in z.namelist() if m.endswith(".hyper"))))
    crla_note = re.search(r"Source: DepEd - CRLA[^<\n]*", twb)
    # OPT+ columns come headerless (F7, F10, ...); the workbook's own captions name them
    caps = {f: c for c, f in re.findall(r"<column caption='([^']*)'[^>]*name='\[(F\d+)\]'", twb)}
    tables = {}
    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp, Connection(hp.endpoint, str(hyper)) as c:
        for t in c.catalog.get_table_names("Extract"):
            cols = [str(col.name).strip('"') for col in c.catalog.get_table_definition(t).columns]
            tables[str(t.name).strip('"').split(".")[0].split(" - ")[0]] = [dict(zip(cols, r)) for r in c.execute_list_query(f"SELECT * FROM {t}")]
    for need in ("school_crla_EOSY", "prov_stunting_2025", "matching_table_v3"):
        if need not in tables:
            raise RuntimeError(f"EDCOM 2 workbook no longer has {need}")
    per_city = {}
    for slug, c in CITIES.items():
        stunting = [r for r in tables["prov_stunting_2025"] if str(r.get("F1")) == c["psgc"].lstrip("0")]
        if len(stunting) != 1:
            raise RuntimeError(f"expected one OPT+ 2025 row for {c['name']}")
        per_city[slug] = {
            "crla": [r for r in tables["school_crla_EOSY"] if r.get("Division") == c["division"]],
            "opt_2025_city": {caps.get(k, k): v for k, v in stunting[0].items()},
            "barangays": [r for r in tables["matching_table_v3"] if str(r.get("psgc_code", "")).zfill(10).startswith(c["psgc"][:7])],
        }
    doc = {
        "workbook": f"https://public.tableau.com/views/{EDCOM2_WB}/Overview", "page": EDCOM2_PAGE,
        "author": meta.get("authorName"), "allow_data_access": True,
        "workbook_updated": datetime.fromtimestamp(meta["lastUpdateDate"] / 1000, timezone.utc).isoformat(timespec="seconds"),
        "retrieved": now(),
        "crla_source_note": crla_note.group(0).strip() if crla_note else "",
        "no_cdc_list_rows_total": len(tables.get("barangay_cdc", [])),
        "cities": per_city,
    }
    (out / "cities.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1, default=str))
    manifest["edcom2/cities.json"] = {"url": f"https://public.tableau.com/workbooks/{EDCOM2_WB}.twb", "sha256": sha(blob)}
    for slug, v in per_city.items():
        print(f"edcom2 {slug}: {len(v['crla'])} CRLA schools, {len(v['barangays'])} barangays, OPT+ city row")


def fetch_ordinances(manifest: dict) -> None:
    """Copy each ordinance city's machine-read book (Stride's lgu-intel parser output, read from the city's own PDF)."""
    for slug, c in CITIES.items():
        if c["budget"] != "ordinance":
            continue
        src = LGU_INTEL / c["intel"] / f"ab-{ORDINANCE_FY}.json"
        blob = src.read_bytes()
        book = json.loads(blob)
        if book["psgc_code"] != c["psgc"] or book["fiscal_year"] != ORDINANCE_FY:
            raise RuntimeError(f"{src} is not {c['name']} FY {ORDINANCE_FY}")
        (RAW / slug).mkdir(parents=True, exist_ok=True)
        (RAW / slug / f"ab-{ORDINANCE_FY}.json").write_bytes(blob)
        manifest[f"{slug}/ab-{ORDINANCE_FY}.json"] = {"url": book.get("source_pdf_url") or book["source_url"], "page": book["source_url"],
                                                      "parsed_by": f"stride-lgu-intel scripts/parse_budget_{c['intel']}.py", "sha256": sha(blob)}
        print(f"ordinance {slug}: {len(book['sheets'])} sheets, stated {book['stated_total']:,.0f}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    mpath = RAW / "manifest.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    steps = {"deped": fetch_deped, "psgc": fetch_psgc, "geo": fetch_geo, "portal": fetch_portal, "edcom2": fetch_edcom2,
             "ordinances": fetch_ordinances}
    for name in sys.argv[1:] or steps:
        steps[name](manifest)
    manifest["_retrieved"] = now()
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
