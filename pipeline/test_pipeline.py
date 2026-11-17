"""Smallest checks that fail if the logic breaks. Run after a build: uv run python -m pipeline.test_pipeline"""

import json
import re

import pandas as pd

from pipeline.build import DATA, SITE, fix_text, fold


def main() -> None:
    assert fix_text("Concepcion PequeÃ±a") == "Concepcion Pequeña"
    assert fix_text("PEÑAFRANCIA") == "PEÑAFRANCIA"  # already-right cells stay as they are
    assert fold("Concepción  Pequeño") == "CONCEPCION PEQUENO"

    sch = pd.read_csv(DATA / "schools.csv", dtype=str, keep_default_na=False)
    gaps = pd.read_csv(DATA / "gaps.csv", dtype=str, keep_default_na=False)
    bud = pd.read_csv(DATA / "budget_lines.csv", dtype=str, keep_default_na=False)
    chk = pd.read_csv(DATA / "checks.csv", dtype=str, keep_default_na=False)
    brgy = pd.read_csv(DATA / "barangays.csv", dtype=str, keep_default_na=False)

    assert sch.school_id.str.fullmatch(r"\d{6}").all(), "school IDs are 6-digit strings"
    assert brgy.psgc_code.str.fullmatch(r"05017240\d\d").all() and len(brgy) == 27, "Naga's 27 barangays, PSGC strings"
    unplaced = set(sch[sch.psgc_barangay_code == ""].school_id)
    assert unplaced <= set(gaps[gaps.kind == "barangay_unmatched"].record_id), "an unmatched school is listed, not dropped"
    assert set(bud.line_id) <= set(gaps[gaps.kind == "budget_line_no_place"].record_id) | set(bud[bud.place_level != "city"].line_id)
    pub = sch[sch.sector == "Public"]
    crla_missing = set(pub[pub.crla_2025_26 != "published"].school_id)
    assert crla_missing == set(gaps[gaps.kind == "crla_not_published"].record_id)
    assert (chk.status == "match").all(), f"source totals don't add up: {chk[chk.status != 'match'].to_dict('records')}"
    assert (brgy.stunting_0_59m_opt == "").all(), "stunting is published for the city only: no invented barangay figures"
    got = pub[pub.crla_2025_26 == "published"]
    bands = got[["crla_low_emerging", "crla_high_emerging", "crla_developing", "crla_transitioning", "crla_at_grade_level"]].astype(int).sum(axis=1)
    assert (bands == got.crla_assessed.astype(int)).all(), "CRLA levels add up to learners assessed"
    assert (pub[pub.crla_2025_26 != "published"].crla_assessed == "").all(), "a school without CRLA stays empty, never 0"

    stats = json.loads((SITE / "api" / "stats.json").read_text())
    assert stats["budget"]["AIP2027"]["sef_lines"] >= 1
    spec = json.loads((SITE / "openapi.json").read_text())
    for path in spec["paths"]:
        p = SITE / path.lstrip("/").replace("{school_id}", sch.school_id.iloc[0])
        assert p.exists(), f"OpenAPI path with no file: {path}"
    for page in SITE.glob("*.html"):
        text = page.read_text()
        assert "{{" not in text, f"unfilled placeholder in {page.name}"
        assert not re.search(r"[\w.]+@gmail\.com|\b09\d{9}\b", text), f"email or mobile number in {page.name}"
    print("ok")


if __name__ == "__main__":
    main()
