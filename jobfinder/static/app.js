const qs = (sel) => document.querySelector(sel);
const qsa = (sel) => Array.from(document.querySelectorAll(sel));

let companies = [];
let jobs = [];
let filtered = [];
let page = 1;
let pageSize = 50;
let sortSpec = [{ key: "score", dir: "desc" }]; // Shift+click to add multi-sort
let lastScanIds = new Set();
let newIds = new Set();

function saveLocal(key, val) { localStorage.setItem(key, JSON.stringify(val)); }
function loadLocal(key, def){ try{ return JSON.parse(localStorage.getItem(key)) ?? def }catch{ return def } }

function renderCompanies() {
  const body = document.querySelector("#companiesBody");
  if (!body) return;
  body.innerHTML = "";
  companies.forEach((c, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="p-2"><input type="checkbox" class="rowSel" data-i="${i}"></td>
      <td class="p-2">${escapeHtml(c.name || "")}</td>
      <td class="p-2">${escapeHtml(c.provider || "")}</td>
      <td class="p-2">${escapeHtml(c.org || "")}</td>
    `;
    body.appendChild(tr);
  });
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toISOString().slice(0,10);
}

function escapeHtml(s) {
  return (s ?? "").toString().replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[m]));
}

function sanitize(html) {
  const div = document.createElement("div");
  div.innerHTML = html || "";
  div.querySelectorAll("script,style,iframe,object,embed,link").forEach(n => n.remove());
  return div.textContent || div.innerText || "";
}

function extractSkills(job) {
  const kwEl = document.querySelector("#keywords");
  const kws = (kwEl?.value || "").split(",").map(s => s.trim().toLowerCase()).filter(Boolean);
  const text = `${job.title} ${sanitize(job.extra?.description || "")}`.toLowerCase();
  const hits = new Set();
  for (const k of kws) if (k && text.includes(k)) hits.add(k);
  return Array.from(hits).slice(0, 20);
}

function badgeWorkMode(job) {
  const wm = (job.extra?.work_mode || "").toLowerCase();
  if (!wm) return "";
  const label = wm === "remote" ? "Remote" : wm === "hybrid" ? "Hybrid" : "Onsite";
  return `<span class="text-xs bg-gray-100 rounded px-2 py-1 ml-2">${label}</span>`;
}

function openDrawer(job) {
  const el = document.querySelector("#drawer");
  const d = document.querySelector("#drawerContent");
  if (!el || !d) return;
  const skills = extractSkills(job);
  d.innerHTML = `
    <h3 class="text-xl font-semibold mb-1">${escapeHtml(job.title || "")}</h3>
    <div class="text-sm text-gray-600 mb-3">
      ${escapeHtml(job.company || "")} • ${escapeHtml(job.location || "N/A")} • ${escapeHtml(job.provider || "")}
      ${badgeWorkMode(job)}
    </div>
    <div class="flex flex-wrap gap-1 mb-3">
      ${(skills.map(s => `<span class="text-xs bg-gray-100 rounded px-2 py-1">${escapeHtml(s)}</span>`).join(" "))}
    </div>
    <div class="text-sm mb-2">Reasons: ${escapeHtml(job.reasons || "")}</div>
    <div class="text-sm whitespace-pre-wrap">${escapeHtml(sanitize(job.extra?.description || ""))}</div>
  `;
  el.classList.remove("hidden");
}

function closeDrawerIfBackdrop(e) {
  if (e.target.id === "drawer") document.querySelector("#drawer")?.classList.add("hidden");
}

function matchRemote(job, sel) {
  const wm = (job.extra?.work_mode || "").toLowerCase();
  if (sel === "any") return true;
  if (sel === "hybrid") return wm === "hybrid";
  if (sel === "true")  return wm ? wm === "remote" : Boolean(job.remote) === true;
  if (sel === "false") return wm ? wm === "onsite" : Boolean(job.remote) === false;
  return true;
}

function renderJobs() {
  const prov = document.querySelector("#fltProvider")?.value || "";
  const remoteSel = document.querySelector("#fltRemote")?.value || "any";
  const minScore = parseInt(document.querySelector("#fltScore")?.value || "0");
  const minSalary = parseInt(document.querySelector("#fltSalary")?.value || "0");
  const onlyNew = !!document.querySelector("#onlyNew")?.checked;

  filtered = jobs.filter(j => {
    if (prov && (j.provider||"") !== prov) return false;
    if (!matchRemote(j, remoteSel)) return false;
    if ((j.score||0) < minScore) return false;
    const smin = Number(j.extra?.salary_min || 0);
    const smax = Number(j.extra?.salary_max || 0);
    if (minSalary && Math.max(smin, smax) < minSalary) return false;
    if (onlyNew && !newIds.has(j.id)) return false;
    return true;
  });

  filtered.sort((a,b) => {
    for (const s of sortSpec) {
      let av = a[s.key]; let bv = b[s.key];
      if (s.key === "created_at") { av = av || ""; bv = bv || ""; }
      const cmp = (av > bv) - (av < bv);
      if (cmp !== 0) return s.dir === "asc" ? cmp : -cmp;
    }
    return 0;
  });

  pageSize = parseInt(document.querySelector("#pageSize")?.value || "50");
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  if (page > totalPages) page = totalPages;
  const start = (page-1)*pageSize;
  const rows = filtered.slice(start, start+pageSize);

  const body = document.querySelector("#jobsBody");
  if (!body) return;
  body.innerHTML = "";
  rows.forEach((j) => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-gray-50 cursor-pointer";
    tr.addEventListener("click", () => openDrawer(j));
    tr.innerHTML = `
      <td class="p-2">${j.score ?? ""}</td>
      <td class="p-2">${escapeHtml(j.title || "")}${badgeWorkMode(j)}</td>
      <td class="p-2">${escapeHtml(j.company || "")}</td>
      <td class="p-2">${escapeHtml(j.location || "")}</td>
      <td class="p-2">${escapeHtml(j.provider || "")}</td>
      <td class="p-2">${fmtDate(j.created_at)}</td>
      <td class="p-2"><a class="text-blue-600 underline" target="_blank" rel="noopener" href="${j.url}" onclick="event.stopPropagation()">open</a></td>
    `;
    body.appendChild(tr);
  });

  const jobsCount = document.querySelector("#jobsCount"); if (jobsCount) jobsCount.textContent = String(filtered.length);
  const newCount = document.querySelector("#newCount"); if (newCount) newCount.textContent = String(newIds.size);
  const pageInfo = document.querySelector("#pageInfo"); if (pageInfo) pageInfo.textContent = `${page} / ${totalPages}`;
}

async function discover() {
  const msg = document.querySelector("#discoverMsg");
  if (msg) msg.textContent = "Discovering...";
  const cities = (document.querySelector("#cities")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const keywords = (document.querySelector("#keywords")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const sources = Array.from(document.querySelector("#sources")?.selectedOptions || []).map(o => o.value);
  const limit = parseInt(document.querySelector("#limit")?.value || "50", 10);
  try {
    const r = await fetch("/discover", {
      method: "POST",
      headers: {"content-type":"application/json"},
      body: JSON.stringify({cities, keywords, sources, limit})
    });
    const data = await r.json();
    if (!r.ok) { if (msg) msg.textContent = data.error || "Discover failed"; return; }
    companies = data.companies || [];
    renderCompanies();
    if (msg) msg.textContent = `Found ${companies.length} companies`;
    saveSearchSelect();
  } catch (e) {
    if (msg) msg.textContent = "Network error";
  }
}

function selectedCompanies() {
  return Array.from(document.querySelectorAll(".rowSel:checked")).map(cb => companies[parseInt(cb.dataset.i, 10)]);
}

async function scanSelected() {
  const selected = selectedCompanies();
  if (!selected.length) return;
  const cities = (document.querySelector("#cities")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const keywords = (document.querySelector("#keywords")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const radius_km = parseFloat(document.querySelector("#radius")?.value || "0");
  const body = {
    cities, keywords, companies: selected,
    geo: radius_km > 0 ? { cities, radius_km } : undefined,
    provider: (document.querySelector("#fltProvider")?.value || undefined),
    remote: document.querySelector("#fltRemote")?.value || "any",
    min_score: parseInt(document.querySelector("#fltScore")?.value || "0"),
    max_age_days: (document.querySelector("#fltAge")?.value ? parseInt(document.querySelector("#fltAge").value) : undefined)
  };
  const r = await fetch("/scan", { method:"POST", headers:{"content-type":"application/json"}, body: JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) { alert(data.error || "Scan failed"); return; }
  const prev = new Set(loadLocal("lastScanIds", []));
  lastScanIds = prev;
  jobs = data.results || [];
  const curIds = new Set(jobs.map(j => j.id));
  newIds = new Set([...curIds].filter(x => !prev.has(x)));
  saveLocal("lastScanIds", [...curIds]);
  page = 1;
  renderJobs();
}

function saveCurrentSearch() {
  const key = prompt("Save search as name:", "");
  if (!key) return;
  const val = {
    cities: document.querySelector("#cities")?.value, keywords: document.querySelector("#keywords")?.value,
    sources: Array.from(document.querySelector("#sources")?.selectedOptions || []).map(o=>o.value), limit: document.querySelector("#limit")?.value,
    radius: document.querySelector("#radius")?.value,
    fltProvider: document.querySelector("#fltProvider")?.value, fltRemote: document.querySelector("#fltRemote")?.value,
    fltScore: document.querySelector("#fltScore")?.value, fltAge: document.querySelector("#fltAge")?.value, fltSalary: document.querySelector("#fltSalary")?.value
  };
  const all = loadLocal("savedSearches", {});
  all[key] = val; saveLocal("savedSearches", all);
  saveSearchSelect();
}

function saveSearchSelect() {
  const sel = document.querySelector("#savedSearches"); if (!sel) return;
  const all = loadLocal("savedSearches", {});
  sel.innerHTML = `<option value="">-- Saved searches --</option>` + Object.keys(all).map(k=>`<option>${escapeHtml(k)}</option>`).join("");
  sel.onchange = () => {
    const v = sel.value; if (!v) return;
    const s = loadLocal("savedSearches", {})[v];
    if (!s) return;
    const cities = document.querySelector("#cities"); if (cities) cities.value = s.cities || "";
    const keywords = document.querySelector("#keywords"); if (keywords) keywords.value = s.keywords || "";
    const sources = document.querySelector("#sources"); if (sources) Array.from(sources.options).forEach(o => o.selected = (s.sources||[]).includes(o.value));
    const limit = document.querySelector("#limit"); if (limit) limit.value = s.limit || "50";
    const radius = document.querySelector("#radius"); if (radius) radius.value = s.radius || "0";
    const fp = document.querySelector("#fltProvider"); if (fp) fp.value = s.fltProvider || "";
    const fr = document.querySelector("#fltRemote"); if (fr) fr.value = s.fltRemote || "any";
    const fs = document.querySelector("#fltScore"); if (fs) fs.value = s.fltScore || "0";
    const fa = document.querySelector("#fltAge"); if (fa) fa.value = s.fltAge || "";
    const fsa = document.querySelector("#fltSalary"); if (fsa) fsa.value = s.fltSalary || "";
  };
}

function setupSort() {
  Array.from(document.querySelectorAll("th.sort")).forEach(th => {
    th.addEventListener("click", (e) => {
      const key = th.dataset.key;
      const shift = e.shiftKey;
      const existing = sortSpec.find(s => s.key === key);
      if (existing) {
        existing.dir = existing.dir === "asc" ? "desc" : "asc";
      } else {
        if (!shift) sortSpec = [];
        sortSpec.push({ key, dir: "asc" });
      }
      renderJobs();
    });
  });
}

function setupPaging() {
  const prev = document.querySelector("#prevPage");
  const next = document.querySelector("#nextPage");
  if (prev) prev.addEventListener("click", () => { if (page>1){ page--; renderJobs(); }});
  if (next) next.addEventListener("click", () => { page++; renderJobs(); });
  const ps = document.querySelector("#pageSize");
  if (ps) ps.addEventListener("change", () => { page=1; renderJobs(); });
}

function setupAutoRefresh() {
  const chk = document.querySelector("#autoRefresh");
  const sel = document.querySelector("#refreshInterval");
  let timer = null;
  const update = () => {
    if (timer) { clearInterval(timer); timer = null; }
    if (chk && sel && chk.checked) {
      timer = setInterval(() => { scanSelected(); }, parseInt(sel.value,10)*1000);
    }
  };
  if (chk) chk.addEventListener("change", update);
  if (sel) sel.addEventListener("change", update);
  update();
}

function setupDrawer() {
  const close = document.querySelector("#closeDrawer");
  const drawer = document.querySelector("#drawer");
  if (close) close.addEventListener("click", () => drawer?.classList.add("hidden"));
  if (drawer) drawer.addEventListener("click", closeDrawerIfBackdrop);
}

function init() {
  renderCompanies();
  renderJobs();
  setupSort();
  setupPaging();
  setupAutoRefresh();
  setupDrawer();
  saveSearchSelect();

  document.querySelector("#btnDiscover")?.addEventListener("click", discover);
  document.querySelector("#btnScanSelected")?.addEventListener("click", scanSelected);
  document.querySelector("#btnClear")?.addEventListener("click", () => { companies=[]; jobs=[]; renderCompanies(); renderJobs(); });
  document.querySelector("#selectAll")?.addEventListener("change", (e) => { Array.from(document.querySelectorAll(".rowSel")).forEach(cb => cb.checked = e.target.checked); });

  ["#fltProvider","#fltRemote","#fltScore","#fltAge","#fltSalary","#onlyNew"].forEach(id => {
    const el = document.querySelector(id); if (el) el.addEventListener("change", renderJobs);
  });
  document.querySelector("#btnSaveSearch")?.addEventListener("click", saveCurrentSearch);
}

window.addEventListener("load", init);
