"""Render site/methodology.html and site/proposal.html from pipeline/templates/.

Every figure on those pages is a {{placeholder}} computed here from the build's outputs, so the prose can't drift
from the data. An unknown placeholder fails the build. Also stamps ?v= content hashes on local .js/.css links.
"""

import hashlib
import html
import json
import re
from pathlib import Path

import pandas as pd

from pipeline.build import BARANGAY_ALIASES, DATA, DOMAINS, RULES, SITE
from pipeline.fetch import DEPED_PAGE, GEO_TAG, PSGC_TAG

TEMPLATES = Path(__file__).parent / "templates"
PAGES = ["methodology.html", "proposal.html"]


def n(x) -> str:
    return f"{int(x):,}"


def peso(x) -> str:
    return f"₱{float(x):,.0f}"


def peso_m(x) -> str:
    return f"₱{float(x) / 1e6:,.1f} million"


def values() -> dict[str, str]:
    s = json.loads((DATA / "stats.json").read_text())
    bud = pd.read_csv(DATA / "budget_lines.csv", dtype={"aip_reference_code": str}, keep_default_na=False)
    gaps = pd.read_csv(DATA / "gaps.csv", dtype=str, keep_default_na=False)
    crla = pd.read_csv(DATA.parent / "data" / "raw" / "deped" / "crla_2025-26_selected.csv", dtype=str, usecols=["region"])
    a, b = s["budget"]["AIP2027"], s["budget"]["AB2026"]
    aip = bud[bud.cycle == "AIP2027"]
    named = lambda pat: aip[aip.name.str.contains(pat, case=False, regex=True)].total.sum()  # noqa: E731
    rules = "".join(f"<tr><td><code>{r}</code></td><td>{', '.join(sorted(o))}</td><td>{html.escape(p or 'every row')}</td>"
                    f"<td>{DOMAINS[d][0]}</td></tr>" for r, o, p, d in RULES)
    default = ", ".join(v[0].lower() for v in DOMAINS.values() if v[1])
    return {
        "built": s["built_at"][:10], "deped_page": DEPED_PAGE,
        "schools_all": n(s["schools"]["all"]), "schools_public": n(s["schools"]["public"]),
        "schools_private": n(s["schools"]["private"]), "districts": n(s["schools"]["districts"]),
        "learners_public": n(s["learners_public_2025_26"]), "learners_2017": n(s["learners_public_2017_18"]),
        "kinder_public": n(s["kinder_public_2025_26"]),
        "staff_sef": n(s["staff_city_sef_2023_24"]), "teachers_sef": n(s["teachers_city_sef_2023_24"]),
        "schools_sef": n(s["schools_with_city_sef_staff"]), "staff_lgu": n(s["staff_other_lgu_2023_24"]),
        "ict_items": n(s["ict_items_lgu_sef_2023_24"]), "schools_ict": n(s["schools_with_lgu_sef_ict"]),
        "public_in_2023": n(s["public_schools_in_2023_24_files"]),
        "schools_missing_2023": n(s["gaps"].get("school_not_in_2023_24", 0)),
        "crla_public": n(s["public_schools_with_crla"]), "crla_rows": n(len(crla)),
        "crla_regions": ", ".join(sorted(crla.region.unique())),
        "barangays": n(s["barangays"]), "barangays_with_school": n(s["barangays_with_public_school"]),
        "matched": n(s["schools_matched_to_psgc"]),
        "alias_list": "; ".join(f"DepEd's \"{k.title()}\" is PSGC's \"{v}\"" for k, v in BARANGAY_ALIASES.items()),
        "alias_schools": n(len(gaps[gaps.kind == "barangay_alias"])),
        "aip_rows": n(a["rows_on_portal"]), "aip_total": peso_m(a["portal_total"]),
        "ab_rows": n(b["rows_on_portal"]), "ab_total": peso_m(b["portal_total"]),
        "aip_scope": n(a["lines_in_scope"]), "ab_scope": n(b["lines_in_scope"]),
        "aip_edu": peso_m(a["education_ecd_total"]), "aip_edu_lines": n(a["education_ecd_lines"]),
        "ab_edu": peso_m(b["education_ecd_total"]), "ab_edu_lines": n(b["education_ecd_lines"]),
        "aip_sef": peso(a["sef_total"]), "aip_sef_share": f"{a['sef_total'] / a['education_ecd_total'] * 100:.0f}%",
        "aip_eccd": peso_m(a["by_domain"].get("early_childhood", 0)), "ab_eccd": peso_m(b["by_domain"].get("early_childhood", 0)),
        "aip_queen": peso_m(named(r"QUEEN")), "aip_scholar": peso_m(named(r"scholar")),
        "lines_with_place": n(a["lines_with_place_code"] + b["lines_with_place_code"]),
        "lines_total": n(a["education_ecd_lines"] + b["education_ecd_lines"]),
        "checks": n(s["checks"]), "checks_match": n(s["checks_matching"]),
        "gaps_total": n(sum(s["gaps"].values())),
        "psgc_tag": PSGC_TAG, "geo_tag": GEO_TAG, "rules_rows": rules, "default_domains": default,
        "diagram": diagram(),
    }


# ---------------------------------------------------------------- flow diagram (wide and tall drawings of one graph)
COLS = [  # (heading, boxes); a box is (title, subtitle, built?)
    ("SOURCES", [("City AIP and budget", "budget.naga.gov.ph public pages", True),
                 ("DepEd school data", "Project Bukas machine-ready files", True),
                 ("ECCD indicators", "OPT+, CRLA, CBMS by barangay", False),
                 ("Procurement", "PPMP items, PhilGEPS notices", False)]),
    ("SCHEMA", [("Tag and place", "fund, domain, school ID, PSGC", True),
                ("Join and check", "source, period, status", True)]),
    ("PUBLISH", [("Open API and downloads", "OpenAPI 3.1, CSV, Parquet", True),
                 ("MCP server", "answers with citations", False)]),
    ("USERS", [("City School Board", "the SEF, school by school", False),
               ("Local ECCD coalition", "barangays without a CDC", False),
               ("DBM COMPASS", "LGU pages joined on PSGC", False),
               ("EDCOM 2 dashboard", "spending beside outcomes", False)]),
]
DESC = ("The City's AIP and budget, DepEd's school data, ECCD indicators and procurement records are tagged by fund, "
        "domain and place (DepEd school ID, PSGC barangay code), joined and checked with every unmatched record listed, "
        "then published as an open API and downloads and, later, an MCP server, for the City School Board, a local ECCD "
        "coalition, DBM COMPASS and EDCOM 2. Solid boxes run in this prototype; dashed boxes are fellowship work.")


def _box(x, y, w, h, title, sub, built) -> str:
    cls = "dg-box dg-core" if built else "dg-box dg-planned"
    cx, cy = x + w / 2, y + h / 2
    return (f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="8"/>'
            f'<text class="dg-title" x="{cx}" y="{cy - 3}" text-anchor="middle">{html.escape(title)}</text>'
            f'<text class="dg-sub" x="{cx}" y="{cy + 14}" text-anchor="middle">{html.escape(sub)}</text>')


def _svg(cls, vb, tid, body) -> str:
    return (f'<svg class="dg {cls}" viewBox="{vb}" role="img" aria-labelledby="{tid}-t {tid}-d" xmlns="http://www.w3.org/2000/svg">'
            f'<title id="{tid}-t">How the education spending data layer works</title><desc id="{tid}-d">{html.escape(DESC)}</desc>'
            f'<defs><marker id="{tid}-a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path class="dg-arrowhead" d="M0,0 L10,5 L0,10 z"/></marker></defs>{body}</svg>')


def diagram() -> str:
    # wide: four columns, each box column-centred; a vertical bus between columns carries the arrows
    W, top, h, gap = 960, 40, 70, 14
    xs, ws = [16, 268, 512, 756], [212, 206, 206, 188]
    rows = lambda k: [top + i * (h + gap) for i in range(k)]  # noqa: E731
    full = top + 4 * h + 3 * gap  # bottom of a four-box column
    body, arrow = [], 'marker-end="url(#dgw-a)"'
    for (head, boxes), x, w in zip(COLS, xs, ws):
        body.append(f'<text class="dg-head" x="{x}" y="22">{head}</text>')
        if len(boxes) == 4:
            ys, hh = rows(4), h
        else:  # two boxes spread over the same height
            hh = (full - top - 2 * gap) / 2
            ys = [top, top + hh + 2 * gap]
        for (t, s, b), y in zip(boxes, ys):
            body.append(_box(x, y, w, hh, t, s, b))
    mids4 = [y + h / 2 for y in rows(4)]
    hh2 = (full - top - 2 * gap) / 2
    mids2 = [top + hh2 / 2, top + hh2 + 2 * gap + hh2 / 2]
    line = lambda d, end=True: f'<path class="dg-line" d="{d}" {arrow if end else ""}/>'  # noqa: E731
    bus1 = (xs[0] + ws[0] + xs[1]) / 2
    body += [line(f"M{xs[0] + ws[0]},{m} L{bus1},{m}", False) for m in mids4]
    body += [line(f"M{bus1},{mids4[0]} L{bus1},{mids4[-1]}", False), line(f"M{bus1},{mids2[0]} L{xs[1] - 2},{mids2[0]}")]
    cx1 = xs[1] + ws[1] / 2
    body.append(line(f"M{cx1},{top + hh2} L{cx1},{top + hh2 + 2 * gap - 2}"))
    bus2 = (xs[1] + ws[1] + xs[2]) / 2
    body += [line(f"M{xs[1] + ws[1]},{mids2[1]} L{bus2},{mids2[1]}", False), line(f"M{bus2},{mids2[0]} L{bus2},{mids2[1]}", False)]
    body += [line(f"M{bus2},{m} L{xs[2] - 2},{m}") for m in mids2]
    bus3 = (xs[2] + ws[2] + xs[3]) / 2
    body += [line(f"M{xs[2] + ws[2]},{m} L{bus3},{m}", False) for m in mids2]
    body.append(line(f"M{bus3},{mids4[0]} L{bus3},{mids4[-1]}", False))
    body += [line(f"M{bus3},{m} L{xs[3] - 2},{m}") for m in mids4]
    wide = _svg("dg-wide", f"0 0 {W} {full + 16}", "dgw", "".join(body))

    # tall: the same columns stacked, one arrow between sections
    y, body, arrow = 0, [], 'marker-end="url(#dgt-a)"'
    for i, (head, boxes) in enumerate(COLS):
        body.append(f'<text class="dg-head" x="16" y="{y + 22}">{head}</text>')
        y += 34
        for t, s, b in boxes:
            body.append(_box(16, y, 328, 60, t, s, b))
            y += 68
        if i < len(COLS) - 1:
            body.append(f'<path class="dg-line" d="M180,{y} L180,{y + 26}" {arrow}/>')
            y += 30
    tall = _svg("dg-tall", f"0 0 360 {y + 8}", "dgt", "".join(body))
    return wide + tall


def bust_cache() -> None:
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:10] for p in [*SITE.glob("*.js"), *SITE.glob("*.css")]}
    pat = re.compile(r'((?:src|href)=")([\w-]+\.(?:js|css))(?:\?v=[0-9a-f]+)?(")')
    for page in SITE.glob("*.html"):
        text = page.read_text()
        new = pat.sub(lambda m: f"{m[1]}{m[2]}?v={digest[m[2]]}{m[3]}" if m[2] in digest else m[0], text)
        if new != text:
            page.write_text(new)


def main() -> None:
    v = values()
    for name in PAGES:
        out = re.sub(r"\{\{(\w+)\}\}", lambda m: v[m.group(1)], (TEMPLATES / name).read_text())
        (SITE / name).write_text(out)
        print(f"wrote site/{name}")
    bust_cache()


if __name__ == "__main__":
    main()
