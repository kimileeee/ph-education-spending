// Data & API page: downloads from /api/catalog.json, and a small Swagger-style reference rendered from /openapi.json
// (endpoint, parameters, "Send" to fetch the real response, curl, and the response schema). No dependencies.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const kb = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`);
const BASE = new URL(".", location.href).href;
const PREVIEW_LINES = 120;

let spec;

async function init() {
  const [catalog, stats] = await Promise.all(["api/catalog.json", "api/stats.json"].map((p) => fetch(p).then((r) => r.json())));
  spec = await (await fetch("openapi.json")).json();

  const peso = (v) => `₱${(v / 1e6).toLocaleString("en-PH", { maximumFractionDigits: 1 })}M`;
  const cs = Object.values(stats.cities), sum = (f) => cs.reduce((t, c) => t + f(c), 0);
  const lines = sum((c) => Object.values(c.budget).reduce((t, b) => t + b.education_ecd_lines, 0));
  const placed = sum((c) => Object.values(c.budget).reduce((t, b) => t + b.school_named_matched, 0));
  const crla = { a: sum((c) => c.crla.assessed), l: sum((c) => c.crla.low_emerging) };
  $("stats").innerHTML = [
    [cs.length, cs.map((c) => c.name.replace("City of ", "")).join(", ")],
    [lines, `education and early-childhood budget rows (${placed} placed at a named school)`],
    [sum((c) => c.schools.public), `public schools, ${sum((c) => c.learners_public_2025_26).toLocaleString("en-PH")} learners (SY 2025-26)`],
    [sum((c) => c.staff_city_sef_2023_24), "school staff DepEd lists as paid from a City SEF (SY 2023-24)"],
    [`${((crla.l / crla.a) * 100).toFixed(1)}%`, `low emerging readers, ${crla.a.toLocaleString("en-PH")} assessed (CRLA, end of SY 2025-26)`],

  ].map(([v, k]) => `<div><div class="v">${v}</div><div class="k">${esc(k)}</div></div>`).join("");

  $("files").innerHTML = `<table><thead><tr><th class="l">Table</th><th class="l">What it holds</th><th>Rows</th><th>Fields</th><th class="l">Download</th></tr></thead><tbody>${
    catalog.files.map((f) => `<tr><td class="l"><code>${esc(f.name)}</code></td><td class="l">${esc(f.description)}</td>
      <td>${f.rows.toLocaleString("en-PH")}</td><td>${f.fields}</td>
      <td class="l nowrap">${f.formats.map((x) => `<a href="${esc(x.path)}" download>${x.format}</a> <span class="note">${kb(x.bytes)}</span>`).join(" · ")}</td></tr>`).join("")}</tbody></table>`;

  $("api-desc").textContent = spec.info.description;
  $("ops").innerHTML = Object.entries(spec.paths).map(([path, item]) => op(path, item.get)).join("");
  $("ops").addEventListener("click", onClick);
  $("ops").addEventListener("input", (e) => e.target.matches("[data-param]") && updateUrl(e.target.closest(".op")));

  snippets();
}

// ---------- one operation ----------

function op(path, o) {
  const params = o.parameters || [];
  const id = o.operationId;
  const res = o.responses["200"].content["application/json"];
  return `<details class="op" id="op-${id}" data-path="${esc(path)}">
    <summary><span class="verb">GET</span><code class="path">${esc(path)}</code><span class="sum">${esc(o.summary)}</span></summary>
    <div class="opbody">
      <p>${esc(o.description)}</p>
      ${params.length ? `<h3>Parameters</h3>${params.map((p) => `<label class="param"><code>${esc(p.name)}</code> <span class="note">${p.in}${p.required ? ", required" : ""} · ${esc(p.description || "")}</span>
        ${p.schema.enum ? `<select data-param="${esc(p.name)}">${p.schema.enum.map((v) => `<option${v === p.example ? " selected" : ""}>${esc(v)}</option>`).join("")}</select>`
                        : `<input data-param="${esc(p.name)}" value="${esc(p.example || "")}">`}</label>`).join("")}` : ""}
      <div class="tryrow"><code class="url" data-url></code>
        <button type="button" class="btn" data-send>Send</button>
        <button type="button" class="btn ghost" data-copy="curl">Copy curl</button></div>
      <div class="resp" data-resp hidden></div>
      <details class="schema"><summary>Response schema · <code>${esc(res.schema.$ref.split("/").pop())}</code></summary>${schemaTable(res.schema)}</details>
      <details class="schema"><summary>Example response</summary><pre class="code">${esc(JSON.stringify(res.example, null, 2))}</pre></details>
    </div></details>`;
}

function resolve(s) {
  return s?.$ref ? spec.components.schemas[s.$ref.split("/").pop()] : s;
}

function typeOf(s) {
  s = s || {};
  if (s.$ref) return s.$ref.split("/").pop();
  if (s.enum) return s.enum.map((v) => JSON.stringify(v)).join(" | ");
  if (s.const) return JSON.stringify(s.const);
  if (s.type === "array") return `${typeOf(s.items || {})}[]`;
  return [].concat(s.type || "object").join(" | ");
}

function schemaTable(s, depth = 0) {
  s = resolve(s);
  if (s.type === "array") return schemaTable(s.items, depth);
  const props = Object.entries(s.properties || {});
  if (!props.length) return `<p class="note">${esc(s.description || typeOf(s))}</p>`;
  return `${s.description && depth === 0 ? `<p class="note">${esc(s.description)}</p>` : ""}<table class="fields"><tbody>${props.map(([k, v]) => {
    const inner = resolve(v.type === "array" ? v.items : v);
    const nested = depth < 2 && inner && inner.properties && Object.keys(inner.properties).length;
    return `<tr><td class="l"><code>${esc(k)}</code></td><td class="l type">${esc(typeOf(v))}</td><td class="l">${esc(v.description || inner?.description || "")}
      ${nested ? `<details><summary class="note">fields</summary>${schemaTable(inner, depth + 1)}</details>` : ""}</td></tr>`;
  }).join("")}</tbody></table>`;
}

function urlFor(box) {
  let path = box.dataset.path;
  box.querySelectorAll("[data-param]").forEach((el) => { path = path.replace(`{${el.dataset.param}}`, encodeURIComponent(el.value)); });
  return new URL(path.replace(/^\//, ""), BASE).href;
}

function updateUrl(box) {
  box.querySelector("[data-url]").textContent = urlFor(box);
}

async function onClick(e) {
  const box = e.target.closest(".op");
  if (!box) return;
  if (e.target.closest("summary") && !box.open) requestAnimationFrame(() => updateUrl(box));
  if (e.target.matches("[data-copy]")) {
    await navigator.clipboard.writeText(`curl -s '${urlFor(box)}'`);
    e.target.textContent = "Copied";
    setTimeout(() => (e.target.textContent = "Copy curl"), 1500);
  }
  if (e.target.matches("[data-send]")) send(box);
}

async function send(box) {
  const out = box.querySelector("[data-resp]");
  const url = urlFor(box);
  out.hidden = false;
  out.innerHTML = `<p class="note">Fetching…</p>`;
  const t0 = performance.now();
  try {
    const r = await fetch(url);
    const text = await r.text();
    const ms = Math.round(performance.now() - t0);
    let pretty = text;
    try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch { /* not JSON: show as is */ }
    const lines = pretty.split("\n");
    const cut = lines.length > PREVIEW_LINES;
    out.innerHTML = `<p class="meta"><span class="status ${r.ok ? "ok" : "bad"}">${r.status} ${esc(r.statusText)}</span> · ${ms} ms · ${kb(text.length)}
      · <a href="${esc(url)}" target="_blank" rel="noopener">open raw</a></p>
      <pre class="code">${esc(lines.slice(0, PREVIEW_LINES).join("\n"))}${cut ? `\n… ${lines.length - PREVIEW_LINES} more lines (open raw for all)` : ""}</pre>`;
  } catch (err) {
    out.innerHTML = `<p class="note">Request failed: ${esc(err.message)}</p>`;
  }
}

// ---------- snippets ----------

function snippets() {
  const base = BASE;
  $("base").textContent = base;
  const S = {
    Python: `import pandas as pd

base = "${base}"
schools = pd.read_parquet(base + "data/schools.parquet")
lines = pd.read_parquet(base + "data/budget_lines.parquet")

# Public schools with staff paid from the City SEF, by barangay (PSGC)
pub = schools.query("sector == 'Public'")
by_bgy = pub.groupby(["psgc_barangay_code", "psgc_barangay_name"]).staff_city_sef_2023_24.sum()

# 2027 AIP rows funded by the SEF
sef = lines[(lines.cycle == "AIP2027") & lines.fund_sources.str.contains("SEF")]`,
    DuckDB: `-- duckdb, with the httpfs extension
SELECT s.school_district, count(*) AS schools, sum(s.learners_2025_26) AS learners,
       sum(s.staff_city_sef_2023_24) AS city_sef_staff
FROM '${base}data/schools.parquet' s
WHERE s.sector = 'Public'
GROUP BY ALL ORDER BY learners DESC;`,
    JavaScript: `const base = "${base}";
const { lines } = await fetch(base + "api/budget-lines.json").then((r) => r.json());
const sef = lines.filter((l) => l.cycle === "AIP2027" && l.fund_sources.includes("SEF"));
console.log(sef.map((l) => \`\${l.aip_reference_code} \${l.name}: ₱\${l.total.toLocaleString()} (\${l.source_url})\`));`,
    curl: `curl -s ${base}api/schools.json | jq '.schools[] | select(.sector=="Public") | {school_id, school_name, psgc_barangay_code, staff_city_sef_2023_24}'
curl -s ${base}api/gaps.json | jq '[.gaps[] | .kind] | group_by(.) | map({(.[0]): length}) | add'`,
  };
  const names = Object.keys(S);
  $("langs").innerHTML = names.map((n, i) => `<button role="tab" aria-selected="${i === 0}" data-l="${n}">${n}</button>`).join("");
  const show = (n) => {
    $("snippet").textContent = S[n];
    for (const b of $("langs").children) b.setAttribute("aria-selected", b.dataset.l === n);
  };
  $("langs").addEventListener("click", (e) => e.target.dataset?.l && show(e.target.dataset.l));
  show(names[0]);
}

init().catch((e) => { $("stats").textContent = `Could not load: ${e.message}`; });
