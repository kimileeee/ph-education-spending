// Source checks: sources, reconciliation checks, and the gap list (filter by kind, kept in the URL hash).
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmt = (v, unit) => (unit === "PHP" ? `₱${Number(v).toLocaleString("en-PH", { maximumFractionDigits: 2 })}` : `${Number(v).toLocaleString("en-PH")} ${unit}`);
const KINDS = {
  budget_line_no_place: "Budget row names no school or barangay",
  crla_not_published: "Public school with no CRLA results",
  crla_school_unmatched: "CRLA row for an unknown school ID",
  barangay_not_in_edcom2: "Barangay missing from EDCOM 2's table",
  budget_school_unmatched: "Budget row names a school DepEd's list can't match",
  school_not_in_2023_24: "School missing from the 2023-24 files",
  sef_budget_not_published: "SEF budget not on the portal",
  eccd_indicator_not_published: "ECCD indicator not published by barangay",
  barangay_unmatched: "DepEd barangay not matched to PSGC",
  barangay_alias: "DepEd barangay matched by hand",
  barangay_no_public_school: "Barangay with no public school",
};

async function init() {
  const [src, chk, gaps] = await Promise.all(["api/sources.json", "api/checks.json", "api/gaps.json"].map((p) => fetch(p).then((r) => r.json())));
  $("sources").innerHTML = `<table><thead><tr><th class="l">Source</th><th class="l">Publisher</th><th class="l">Period</th><th class="l">Status</th></tr></thead><tbody>${
    src.sources.map((s) => `<tr id="src-${esc(s.source_id)}"><td class="l"><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a><br><code class="note">${esc(s.source_id)}</code></td>
      <td class="l">${esc(s.publisher)}</td><td class="l nowrap">${esc(s.period)}</td>
      <td class="l"><span class="result ${s.status === "used" ? "match" : "blank"}">${esc(s.status)}</span></td></tr>`).join("")}</tbody></table>`;
  const CITY = { naga: "Naga", zamboanga: "Zamboanga City", cdo: "Cagayan de Oro" };
  $("checks").innerHTML = `<table><thead><tr><th class="l">Check</th><th>Expected</th><th>Found</th><th class="l">Result</th></tr></thead><tbody>${
    chk.checks.map((c) => `<tr><td class="l"><a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.what)}</a></td>
      <td class="nowrap">${fmt(c.expected, c.unit)}</td><td class="nowrap">${fmt(c.actual, c.unit)}</td>
      <td class="l"><span class="result ${c.status}">${esc(c.status)}</span></td></tr>`).join("")}</tbody></table>`;
  const kind = $("kind"), city = $("gcity");
  const fillKinds = () => {
    const pool = gaps.gaps.filter((g) => !city.value || g.city === city.value);
    const counts = pool.reduce((m, g) => ((m[g.kind] = (m[g.kind] || 0) + 1), m), {});
    const keep = kind.value;
    kind.innerHTML = `<option value="">All (${pool.length})</option>` +
      Object.entries(counts).map(([k, n]) => `<option value="${k}">${esc(KINDS[k] || k)} (${n})</option>`).join("");
    kind.value = counts[keep] ? keep : "";
  };
  const show = () => {
    const k = kind.value, c = city.value;
    history.replaceState(null, "", k || c ? `#gaps:${k}:${c}` : location.pathname);
    const rows = gaps.gaps.filter((g) => (!k || g.kind === k) && (!c || g.city === c));
    $("gaplist").innerHTML = `<table><thead><tr><th class="l">City</th><th class="l">Kind</th><th class="l">Record</th><th class="l">Detail</th><th class="l">Source</th></tr></thead><tbody>${
      rows.map((g) => `<tr><td class="l">${esc(CITY[g.city] || g.city)}</td><td class="l dom">${esc(KINDS[g.kind] || g.kind)}${g.resolved ? ` <span class="tag">resolved</span>` : ""}</td>
        <td class="l"><code>${esc(g.record_id)}</code></td><td class="l">${esc(g.detail)}</td>
        <td class="l"><a href="#src-${esc(g.source_id)}">${esc(g.source_id)}</a></td></tr>`).join("")}</tbody></table>`;
  };
  const m = location.hash.match(/^#gaps:(\w*):?(\w*)/);
  if (m) city.value = m[2] || "";
  fillKinds();
  if (m && m[1]) kind.value = m[1];
  kind.onchange = show;
  city.onchange = () => { fillKinds(); show(); };
  show();
}
init().catch((e) => { $("sources").textContent = `Could not load: ${e.message}`; });
