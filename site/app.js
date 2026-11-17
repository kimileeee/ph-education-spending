// Explorer: city tiles, the City's budget rows, and districts -> schools -> barangay map.
// All state lives in the URL hash (cycle, scope, tab, district, metric, bgy); controls call go().
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const int = (v) => (v == null ? "–" : Number(v).toLocaleString("en-PH"));
const peso = (v) => `₱${Number(v).toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;
const pesoM = (v) => `₱${(v / 1e6).toLocaleString("en-PH", { maximumFractionDigits: 1 })}M`;
const NP = `<span class="np">not published</span>`;
const DEFAULTS = { cycle: "AIP2027", scope: "edu", tab: "districts", district: "", metric: "learners", bgy: "", all: "" };

let D = {};
let state = { ...DEFAULTS };

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  state = { ...DEFAULTS, ...Object.fromEntries(h) };
}
function go(patch) {
  state = { ...state, ...patch };
  const h = new URLSearchParams(Object.entries(state).filter(([k, v]) => v !== DEFAULTS[k]));
  history.replaceState(null, "", `#${h}`);
  render();
}

async function init() {
  const [stats, budget, schools, districts, barangays, geo] = await Promise.all(
    ["api/stats.json", "api/budget-lines.json", "api/schools.json", "api/districts.json", "api/barangays.json", "geo/naga-barangays.geojson"]
      .map((p) => fetch(p).then((r) => r.json())));
  D = { stats, lines: budget.lines, schools: schools.schools, districts: districts.districts, barangays: barangays.barangays, geo };
  readHash();
  tiles();
  $("built").textContent = `Built ${stats.built_at.slice(0, 10)} from DepEd's machine-ready files and the City of Naga's People's Budget Portal. Prototype by Kim Williame Lee.`;
  $("tabs").addEventListener("click", (e) => e.target.dataset.tab && go({ tab: e.target.dataset.tab }));
  window.addEventListener("hashchange", () => { readHash(); render(); });
  render();
}

function tiles() {
  const s = D.stats, a = s.budget.AIP2027, b = s.budget.AB2026;
  const t = [
    ["2027 AIP: education and early childhood", pesoM(a.education_ecd_total), `${a.education_ecd_lines} rows, proposed`],
    ["Of which, the SEF row", pesoM(a.sef_total), `${Math.round((a.sef_total / a.education_ecd_total) * 100)}% of it, in one row with no school named`],
    ["2026 enacted budget: same offices", pesoM(b.education_ecd_total), `${b.education_ecd_lines} rows; the SEF's own budget isn't on the portal`],
    ["Public schools", int(s.schools.public), `${int(s.learners_public_2025_26)} learners, SY 2025-26, in ${s.schools.districts} districts`],
    ["Staff paid from the City SEF", int(s.staff_city_sef_2023_24), `at ${s.schools_with_city_sef_staff} schools (${s.teachers_city_sef_2023_24} of them teachers), SY 2023-24`],
    ["Reading results (CRLA)", `${s.public_schools_with_crla} of ${s.schools.public}`, "public schools in DepEd's machine-ready CRLA file"],
  ];
  $("tiles").innerHTML = t.map(([k, v, sub]) => `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div><div class="s">${esc(sub)}</div></div>`).join("");
}

function seg(id, opts, key) {
  $(id).innerHTML = opts.map(([v, l]) => `<button type="button" aria-pressed="${state[key] === v}" data-v="${v}">${esc(l)}</button>`).join("");
  $(id).onclick = (e) => e.target.dataset.v != null && go({ [key]: e.target.dataset.v });
}

function render() {
  seg("cycle", [["AIP2027", "2027 AIP (proposed)"], ["AB2026", "2026 budget (enacted)"]], "cycle");
  seg("scope", [["edu", "Education and early childhood"], ["all", "Every row of these offices"]], "scope");
  budget();
  for (const b of $("tabs").children) b.setAttribute("aria-selected", b.dataset.tab === state.tab);
  for (const t of ["districts", "schools", "map"]) $(`p-${t}`).hidden = state.tab !== t;
  ({ districts, schools, map })[state.tab]();
}

// ---------- budget ----------
function budget() {
  const dom = D.stats.domains;
  const rows = D.lines.filter((l) => l.cycle === state.cycle && (state.scope === "all" || dom[l.domain].in_default_total))
    .sort((a, b) => b.total - a.total);
  const total = rows.reduce((s, r) => s + r.total, 0);
  const max = Math.max(...rows.map((r) => r.total), 1);
  const placed = rows.filter((r) => r.place_level !== "city").length;
  $("budget-note").innerHTML = `${rows.length} rows, ${peso(total)}. <strong>${placed} of ${rows.length}</strong> name a school or barangay; the rest are city-wide, so they can't be lined up with a school yet.
    Each row links to its page on the City's portal. ${state.cycle === "AB2026" ? "The enacted 2026 rows carry no fund field on the portal, and the SEF's own 2026 budget isn't loaded there." : ""}`;
  $("budget").innerHTML = `<table><thead><tr><th class="l">Row</th><th>Amount</th><th class="l">Fund</th><th class="l">Office</th><th class="l">Domain</th><th class="l">Place</th></tr></thead>
    <tbody>${rows.map((r) => `<tr><td class="l"><a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.name)}</a><br><code class="note">${esc(r.aip_reference_code)}</code></td>
      <td class="nowrap"><span class="bar" style="width:${Math.max(2, (r.total / max) * 60)}px"></span>${peso(r.total)}</td>
      <td class="l">${r.fund_sources ? esc(r.fund_sources) : `<span class="np">not stated</span>`}</td>
      <td class="l">${esc(r.office_code)}</td><td class="l dom">${esc(dom[r.domain].label)}</td>
      <td class="l">${r.place_level === "city" ? "City-wide" : esc(r.place_code)}</td></tr>`).join("")}</tbody>
    <tfoot><tr><td class="l">Total</td><td class="nowrap">${peso(total)}</td><td colspan="4"></td></tr></tfoot></table>`;
}

// ---------- districts ----------
function districts() {
  const rows = D.districts;
  const ratio = (r) => (r.classrooms_instructional_2023_24 ? (r.learners_2023_24 / r.classrooms_instructional_2023_24).toFixed(1) : "–");
  $("p-districts").innerHTML = `<p class="note">DepEd's four school districts in Naga, public schools only. Pick one to see its schools.</p>
    <div class="tablewrap" style="max-height:none"><table><thead><tr><th class="l">District</th><th>Schools</th><th>Learners 2025-26</th><th>Learners 2017-18</th>
    <th>Learners per classroom 2023-24</th><th>Buildings needing major repair</th><th>Staff paid from City SEF</th><th>Other LGU-paid staff</th><th>ICT items from LGU/SEF</th><th class="l">Reading (CRLA)</th></tr></thead>
    <tbody>${rows.map((r) => `<tr><td class="l"><button class="link" data-d="${esc(r.school_district)}">${esc(r.school_district)}</button></td>
      <td>${int(r.public_schools)}</td><td>${int(r.learners_2025_26)}</td><td>${int(r.learners_2017_18)}</td><td>${ratio(r)}</td>
      <td>${int(r.buildings_major_repair_or_worse_2023_24)}</td><td>${int(r.staff_city_sef_2023_24)}</td><td>${int(r.staff_other_lgu_2023_24)}</td>
      <td>${int(r.ict_items_lgu_sef_2023_24)}</td><td class="l">${NP}</td></tr>`).join("")}</tbody></table></div>
    <p class="note">Learners 2017-18 counts only schools that existed then under the same ID. SY 2023-24 figures are the latest DepEd publishes for staff, ICT and facilities.</p>`;
  $("p-districts").onclick = (e) => e.target.dataset.d && go({ tab: "schools", district: e.target.dataset.d });
}

// ---------- schools ----------
function schools() {
  const list = D.schools.filter((s) => (state.all ? true : s.sector === "Public") && (!state.district || s.school_district === state.district))
    .sort((a, b) => b.learners_2025_26 - a.learners_2025_26);
  const dists = [...new Set(D.schools.filter((s) => s.sector === "Public").map((s) => s.school_district))].sort();
  $("p-schools").innerHTML = `<div class="filters">
      <label>District <select id="dsel"><option value="">All districts</option>${dists.map((d) => `<option${d === state.district ? " selected" : ""}>${esc(d)}</option>`).join("")}</select></label>
      <label class="check"><input type="checkbox" id="allsec"${state.all ? " checked" : ""}> Include private schools and the state college</label></div>
    <p class="note">${list.length} schools. A dash means the school isn't in DepEd's SY 2023-24 files (new school or new ID); those are listed on the <a href="checks.html#gaps">checks page</a>.</p>
    <div class="tablewrap"><table><thead><tr><th class="l">School</th><th class="l">Barangay (PSGC)</th><th>Learners 2025-26</th><th>Per classroom</th><th>Buildings needing major repair</th><th>City SEF staff</th><th>LGU/SEF ICT items</th><th class="l">CRLA</th></tr></thead>
    <tbody>${list.map((s) => `<tr><td class="l">${esc(s.school_name)}<br><code class="note">${esc(s.school_id)}</code>${s.sector !== "Public" ? `<span class="tag">${esc(s.sector)}</span>` : ""}</td>
      <td class="l">${esc(s.psgc_barangay_name)}<br><code class="note">${esc(s.psgc_barangay_code)}</code></td>
      <td>${int(s.learners_2025_26)}</td><td>${s.learners_per_classroom_2023_24 ?? "–"}</td><td>${int(s.buildings_major_repair_or_worse_2023_24)}</td>
      <td>${int(s.staff_city_sef_2023_24)}</td><td>${int(s.ict_items_lgu_sef_2023_24)}</td>
      <td class="l">${s.crla_2025_26 === "published" ? "published" : NP}</td></tr>`).join("")}</tbody></table></div>`;
  $("dsel").onchange = (e) => go({ district: e.target.value });
  $("allsec").onchange = (e) => go({ all: e.target.checked ? "1" : "" });
}

// ---------- map ----------
const METRICS = {
  learners: ["Public-school learners, 2025-26", (b) => b.learners_public_2025_26, "DepEd enrollment"],
  sef: ["Staff paid from the City SEF, 2023-24", (b) => b.staff_city_sef_2023_24, "DepEd personnel file"],
  ict: ["ICT items from LGU/SEF, 2023-24", (b) => b.ict_items_lgu_sef_2023_24, "DepEd ICT file"],
  stunting: ["Stunting, children under 5 (OPT+)", (b) => b.stunting_0_59m_opt, "not published by barangay"],
  cdc: ["Child development centres (CBMS)", (b) => b.child_development_centres, "not published by barangay"],
  crla: ["Low emerging readers (CRLA)", (b) => b.crla_low_emerging_share, "not published for Naga"],
};

function project(geo) {
  const pts = geo.features.flatMap((f) => (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates).flat(1)).flat(1);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const k = Math.cos(((y0 + y1) / 2) * Math.PI / 180); // equirectangular, corrected for latitude
  const W = 600, s = W / ((x1 - x0) * k), H = Math.round((y1 - y0) * s);
  const pt = ([x, y]) => `${((x - x0) * k * s).toFixed(1)},${((y1 - y) * s).toFixed(1)}`;
  const path = (g) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates).map((poly) => poly.map((ring) => `M${ring.map(pt).join("L")}Z`).join("")).join("");
  return { W, H, path };
}

function map() {
  const [label, get, src] = METRICS[state.metric];
  const by = Object.fromEntries(D.barangays.map((b) => [b.psgc_code, b]));
  const vals = D.barangays.map(get).filter((v) => v != null);
  const max = Math.max(...vals, 1);
  const color = (v) => (v == null ? "url(#np)" : v === 0 ? "var(--none)" : `var(--seq-${Math.min(5, 1 + Math.floor((v / max) * 4.999))})`);
  const { W, H, path } = project(D.geo);
  const sel = by[state.bgy];
  $("p-map").innerHTML = `<div class="filters"><div class="seg" role="group" aria-label="Measure" id="metric"></div></div>
    <div class="mapgrid"><div class="map svgmap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of Naga's 27 barangays: ${esc(label)}">
      <defs><pattern id="np" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="7" height="7" fill="var(--none)"/><rect width="3" height="7" fill="var(--nodata)"/></pattern></defs>
      ${D.geo.features.map((f) => { const b = by[f.properties.psgc_code]; const v = b ? get(b) : null;
        return `<path class="b${state.bgy === f.properties.psgc_code ? " sel" : ""}" d="${path(f.geometry)}" fill="${color(v)}" data-b="${f.properties.psgc_code}"><title>${esc(f.properties.name)}: ${v == null ? "not published" : int(v)}</title></path>`; }).join("")}
    </svg></div>
    <div><p class="label">${esc(label)}</p><p class="note">Source: ${esc(src)}. ${vals.length ? `Darkest = ${int(max)}. Pale = none.` : "No barangay has a public figure yet, so every barangay is hatched."}</p>
      <div class="keys"><span><i class="box" style="background:var(--seq-4)"></i>more</span><span><i class="box" style="background:var(--seq-1)"></i>fewer</span>
      <span><i class="box" style="background:var(--none)"></i>none</span><span><i class="box hatch"></i>not published</span></div>
      <div class="placecard" ${sel ? "" : "hidden"} style="margin-top:16px">${sel ? place(sel) : ""}</div>
      ${sel ? "" : `<p class="note" style="margin-top:16px">Pick a barangay to see its schools.</p>`}</div></div>`;
  seg("metric", Object.entries(METRICS).map(([k, [l]]) => [k, l.split(",")[0].replace(/ \(.*\)/, "")]), "metric");
  $("p-map").querySelector("svg").onclick = (e) => e.target.dataset.b && go({ bgy: e.target.dataset.b });
}

function place(b) {
  const sch = D.schools.filter((s) => s.psgc_barangay_code === b.psgc_code && s.sector === "Public");
  return `<div class="pc-head"><div><h3>${esc(b.name)}</h3><p class="note"><code>${esc(b.psgc_code)}</code> · ${esc(b.school_district || "no public school")}</p></div></div>
    <table class="fields"><tbody>
      <tr><td class="l">Public schools</td><td>${int(b.public_schools)} (${int(b.private_schools)} private)</td></tr>
      <tr><td class="l">Learners 2025-26</td><td>${int(b.learners_public_2025_26)}</td></tr>
      <tr><td class="l">City SEF staff 2023-24</td><td>${int(b.staff_city_sef_2023_24)}</td></tr>
      <tr><td class="l">Stunting (OPT+)</td><td>${NP}</td></tr>
      <tr><td class="l">Child development centres</td><td>${NP}</td></tr>
      <tr><td class="l">City budget rows naming it</td><td>0</td></tr></tbody></table>
    ${sch.length ? `<ul class="plain" style="margin-top:8px">${sch.map((s) => `<li>${esc(s.school_name)} <span class="note">(${int(s.learners_2025_26)})</span></li>`).join("")}</ul>` : ""}`;
}

init().catch((e) => { $("tiles").textContent = `Could not load the data: ${e.message}`; });
