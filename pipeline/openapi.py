"""site/openapi.json (OpenAPI 3.1) for the static JSON API.

Row schemas come from the data package's field list, so the spec can't drift from the tables; examples are cut
from the real responses. Lint: npx @redocly/cli@1.34.3 lint site/openapi.json
"""

import json

from pipeline.build import SITE

TYPES = {"integer": ["integer", "null"], "number": ["number", "null"], "boolean": "boolean", "string": "string"}
TABLES = {  # schema name -> (resource in datapackage, list key in the response)
    "BudgetLine": ("budget_lines", "lines"), "School": ("schools", "schools"), "Barangay": ("barangays", "barangays"),
    "District": ("districts", "districts"), "Gap": ("gaps", "gaps"), "Check": ("checks", "checks"), "Source": ("sources", "sources"),
}
PATHS = [  # path, operationId, schema, list key or None, summary, description
    ("/api/budget-lines.json", "listBudgetLines", "BudgetLine", "lines", "Education and early-childhood budget rows",
     "Rows of Naga City's enacted 2026 budget and 2027 AIP from the offices in scope, each tagged with a domain, its funds, "
     "and a link to its public page on budget.naga.gov.ph. place_level says how finely the City's document places it."),
    ("/api/schools.json", "listSchools", "School", "schools", "Schools in the Schools Division of Naga City",
     "Every school in DepEd's enrollment file for the division, keyed by DepEd school ID and PSGC barangay code."),
    ("/api/schools/{school_id}.json", "getSchool", "School", None, "One school", "One school by its DepEd school ID."),
    ("/api/districts.json", "listDistricts", "District", "districts", "School districts",
     "DepEd's four school districts in Naga, public-school totals."),
    ("/api/barangays.json", "listBarangays", "Barangay", "barangays", "Barangays",
     "Naga's 27 barangays by PSGC code, with public-school totals and the ECCD indicator slots. An empty indicator "
     "comes with a *_status of 'not published'."),
    ("/api/gaps.json", "listGaps", "Gap", "gaps", "Unmatched and unpublished records",
     "Everything that could not be joined or has no public source, one row each. Nothing is dropped."),
    ("/api/checks.json", "listChecks", "Check", "checks", "Reconciliation checks", "Do the sources add up to their own totals?"),
    ("/api/sources.json", "listSources", "Source", "sources", "Sources", "Every source with URL, period and sha256."),
]


def write(stats: dict) -> None:
    pk = json.loads((SITE / "data" / "datapackage.json").read_text())
    fields = {r["name"]: r["schema"]["fields"] for r in pk["resources"]}
    schemas = {
        name: {"type": "object", "description": next(r["description"] for r in pk["resources"] if r["name"] == res),
               "properties": {f["name"]: {"type": TYPES[f["type"]], **({"description": f["description"]} if f["description"] else {})}
                              for f in fields[res]}}
        for name, (res, _) in TABLES.items()
    }
    schemas["Stats"] = {"type": "object", "description": "Headline counts and totals from this build.", "additionalProperties": True}
    paths = {}
    for path, op_id, schema, key, summary, desc in PATHS:
        real = json.loads((SITE / path.lstrip("/").replace("{school_id}", "302160" if False else first_school())).read_text())
        if key:
            body = {"type": "object", "properties": {key: {"type": "array", "items": {"$ref": f"#/components/schemas/{schema}"}}},
                    "required": [key]}
            example = {key: real[key][:2]}
        else:
            body = {"$ref": f"#/components/schemas/{schema}"}
            example = real
        params = [{"name": "school_id", "in": "path", "required": True, "description": "DepEd 6-digit school ID",
                   "schema": {"type": "string", "pattern": r"^\d{6}$"}, "example": first_school()}] if "{" in path else []
        paths[path] = {"get": {"operationId": op_id, "summary": summary, "description": desc, "parameters": params,
                               "responses": {"200": {"description": "OK", "content": {"application/json": {
                                   "schema": body if key is None else {"$ref": f"#/components/schemas/{schema}List"}, "example": example}}},
                                   **({"404": {"description": "No school with that ID in the Schools Division of Naga City"}} if params else {})}}}
        if key:
            schemas[f"{schema}List"] = body
    paths["/api/stats.json"] = {"get": {"operationId": "getStats", "summary": "Headline figures",
                                        "description": "Counts and totals the site quotes, computed at build time.", "parameters": [],
                                        "responses": {"200": {"description": "OK", "content": {"application/json": {
                                            "schema": {"$ref": "#/components/schemas/Stats"},
                                            "example": {"built_at": stats["built_at"], "cities": {k: {kk: v[kk] for kk in ("name", "schools", "learners_public_2025_26")}
                                                                                    for k, v in stats["cities"].items()}}}}}}}}
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "City education and early-childhood spending (prototype)", "version": stats["built_at"][:10],
                 "description": "Static JSON files for Naga, Zamboanga City and Cagayan de Oro: no key, no tracking, CORS open. Every row has a city field. Join schools on DepEd school ID and "
                                "places on 10-digit PSGC codes. Every row names its source_id; see /api/sources.json.",
                 "license": {"name": "ODC-BY-1.0", "url": "https://opendatacommons.org/licenses/by/1-0/"}},
        "servers": [{"url": "/"}],
        "security": [],  # public files, no auth
        "paths": paths,
        "components": {"schemas": schemas},
    }
    (SITE / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1))


def first_school() -> str:
    return sorted(p.stem for p in (SITE / "api" / "schools").glob("*.json"))[0]
