// jobfinder/static/app.js
console.log("[jobfinder] app.js loaded");

const qs = (sel) => document.querySelector(sel);
const qsa = (sel) => Array.from(document.querySelectorAll(sel));

let companies = [];
let jobs = [];
let filtered = [];
let page = 1;
let pageSize = 50;
let sortSpec = [{ key: "score", dir: "desc" }];
let lastScanIds = new Set();
let newIds = new Set();
let initialized = false;

function saveLocal(key, val) { localStorage.setItem(key, JSON.stringify(val)); }
function loadLocal(key, def){ try{ return JSON.parse(localStorage.getItem(key)) ?? def }catch{ return def } }

function setDiscoverMsg(text, kind="info") {
  const el = qs("#discoverMsg"); if (!el) return;
  el.textContent = text || "";
  el.className = "mt-3 text-base font-semibold";
  if (kind === "error") el.classList.add("text-red-600");
  else if (kind === "ok") el.classList.add("text-green-700");
  else el.classList.add("text-gray-800");
}

function setScanLoading(isLoading, text="Scanning...") {
  const btn = qs("#btnScanSelected");
  const txt = qs("#scanBtnText");
  const spn = qs("#scanSpinner");
  const msg = qs("#scanMsg");
  if (!btn) return;
  if (isLoading) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.classList.add("opacity-70", "cursor-not-allowed");
    if (txt) txt.textContent = text;
    if (spn) spn.classList.remove("hidden");
    if (msg) { msg.textContent = text; msg.className = "text-sm mt-2 text-gray-800 font-semibold"; }
  } else {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    btn.classList.remove("opacity-70", "cursor-not-allowed");
    if (txt) txt.textContent = "Scan selected";
    if (spn) spn.classList.add("hidden");
    if (msg) { msg.textContent = ""; msg.className = "text-sm text-gray-600 mt-2"; }
  }
}

function renderCompanies() {
  const body = qs("#companiesBody");
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
  const kwEl = qs("#keywords");
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
  const el = qs("#drawer");
  const d = qs("#drawerContent");
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

function matchRemote(job, sel) {
  const wm = (job.extra?.work_mode || "").toLowerCase();
  if (sel === "any") return true;
  if (sel === "hybrid") return wm === "hybrid";
  if (sel === "true")  return wm ? wm === "remote" : Boolean(job.remote) === true;
  if (sel === "false") return wm ? wm === "onsite" : Boolean(job.remote) === false;
  return true;
}

function renderJobs() {
  const prov = qs("#fltProvider")?.value || "";
  const remoteSel = qs("#fltRemote")?.value || "any";
  const minScore = parseInt(qs("#fltScore")?.value || "0");
  const maxAgeDays = parseInt(qs("#fltAge")?.value || "0");
  const minSalary = parseInt(qs("#fltSalary")?.value || "0");
  const onlyNew = !!qs("#onlyNew")?.checked;

  filtered = jobs.filter(j => {
    if (prov && (j.provider||"") !== prov) return false;
    if (!matchRemote(j, remoteSel)) return false;
    if ((j.score||0) < minScore) return false;
    if (maxAgeDays > 0 && j.created_at) {
      const created = new Date(j.created_at);
      if (!isNaN(created.getTime())) {
        const age = Math.floor((Date.now() - created.getTime()) / 86400000);
        if (age > maxAgeDays) return false;
      }
    }
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

  pageSize = parseInt(qs("#pageSize")?.value || "50");
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  if (page > totalPages) page = totalPages;
  const start = (page-1)*pageSize;
  const rows = filtered.slice(start, start+pageSize);

  const body = qs("#jobsBody");
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

  qs("#jobsCount") && (qs("#jobsCount").textContent = String(filtered.length));
  qs("#newCount") && (qs("#newCount").textContent = String(newIds.size));
  qs("#pageInfo") && (qs("#pageInfo").textContent = `${page} / ${totalPages}`);
}

async function discover() {
  setDiscoverMsg("Discovering...", "info");
  console.log("[jobfinder] Discover clicked");
  const cities = (qs("#cities")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const keywords = (qs("#keywords")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const sources = Array.from(qs("#sources")?.selectedOptions || []).map(o => o.value);
  const limit = parseInt(qs("#limit")?.value || "50", 10);
  try {
    const r = await fetch("/discover", {
      method: "POST",
      headers: {"content-type":"application/json"},
      body: JSON.stringify({cities, keywords, sources, limit})
    });
    const data = await r.json();
    if (!r.ok) { setDiscoverMsg(data.error || "Discover failed", "error"); return; }
    companies = data.companies || [];
    renderCompanies();
    setDiscoverMsg(`Found ${companies.length} companies`, "ok");
  } catch (e) {
    console.error("[jobfinder] Discover error", e);
    setDiscoverMsg("Network error", "error");
  }
}

function selectedCompanies() {
  return qsa(".rowSel:checked").map(cb => companies[parseInt(cb.dataset.i, 10)]);
}

async function scanSelected() {
  console.log("[jobfinder] Scan clicked");
  const selected = selectedCompanies();
  if (!selected.length) { setDiscoverMsg("Select at least one company", "error"); return; }
  const cities = (qs("#cities")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const keywords = (qs("#keywords")?.value || "").split(",").map(s => s.trim()).filter(Boolean);
  const radius_km = parseFloat(qs("#radius")?.value || "0");
  const body = {
    cities, keywords, companies: selected,
    geo: radius_km > 0 ? { cities, radius_km } : undefined,
    provider: (qs("#fltProvider")?.value || undefined),
    remote: qs("#fltRemote")?.value || "any",
    min_score: parseInt(qs("#fltScore")?.value || "0"),
    max_age_days: (qs("#fltAge")?.value ? parseInt(qs("#fltAge").value) : undefined)
  };
  setScanLoading(true);
  try {
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
  } catch (e) {
    console.error("[jobfinder] Scan error", e);
  } finally {
    setScanLoading(false);
  }
}

function saveCurrentSearch() {
  const key = prompt("Save search as name:", "");
  if (!key) return;
  const val = {
    cities: qs("#cities")?.value, keywords: qs("#keywords")?.value,
    sources: Array.from(qs("#sources")?.selectedOptions || []).map(o=>o.value), limit: qs("#limit")?.value,
    radius: qs("#radius")?.value,
    fltProvider: qs("#fltProvider")?.value, fltRemote: qs("#fltRemote")?.value,
    fltScore: qs("#fltScore")?.value, fltAge: qs("#fltAge")?.value, fltSalary: qs("#fltSalary")?.value
  };
  const all = loadLocal("savedSearches", {});
  all[key] = val; saveLocal("savedSearches", all);
  saveSearchSelect();
}

function saveSearchSelect() {
  const sel = qs("#savedSearches"); if (!sel) return;
  const all = loadLocal("savedSearches", {});
  sel.innerHTML = `<option value="">-- Saved searches --</option>` + Object.keys(all).map(k=>`<option>${escapeHtml(k)}</option>`).join("");
  sel.onchange = () => {
    const v = sel.value; if (!v) return;
    const s = loadLocal("savedSearches", {})[v];
    if (!s) return;
    qs("#cities") && (qs("#cities").value = s.cities || "");
    qs("#keywords") && (qs("#keywords").value = s.keywords || "");
    const src = qs("#sources"); if (src) Array.from(src.options).forEach(o => o.selected = (s.sources||[]).includes(o.value));
    qs("#limit") && (qs("#limit").value = s.limit || "50");
    qs("#radius") && (qs("#radius").value = s.radius || "0");
    qs("#fltProvider") && (qs("#fltProvider").value = s.fltProvider || "");
    qs("#fltRemote") && (qs("#fltRemote").value = s.fltRemote || "any");
    qs("#fltScore") && (qs("#fltScore").value = s.fltScore || "0");
    qs("#fltAge") && (qs("#fltAge").value = s.fltAge || "");
    qs("#fltSalary") && (qs("#fltSalary").value = s.fltSalary || "");
  };
}

function setupSort() {
  qsa("th.sort").forEach(th => {
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
  qs("#prevPage")?.addEventListener("click", () => { if (page>1){ page--; renderJobs(); }});
  qs("#nextPage")?.addEventListener("click", () => { page++; renderJobs(); });
  qs("#pageSize")?.addEventListener("change", () => { page=1; renderJobs(); });
}

function setupAutoRefresh() {
  const chk = qs("#autoRefresh");
  const sel = qs("#refreshInterval");
  let timer = null;
  const update = () => {
    if (timer) { clearInterval(timer); timer = null; }
    if (chk && sel && chk.checked) {
      timer = setInterval(() => { scanSelected(); }, parseInt(sel.value,10)*1000);
    }
  };
  chk && chk.addEventListener("change", update);
  sel && sel.addEventListener("change", update);
  update();
}

function setupDrawer() {
  const close = qs("#closeDrawer");
  const drawer = qs("#drawer");
  close && close.addEventListener("click", () => drawer?.classList.add("hidden"));
  drawer && drawer.addEventListener("click", (e) => { if (e.target.id === "drawer") drawer.classList.add("hidden"); });
}

function init() {
  if (initialized) return;
  initialized = true;
  console.log("[jobfinder] init");
  renderCompanies();
  renderJobs();
  setupSort();
  setupPaging();
  setupAutoRefresh();
  setupDrawer();
  saveSearchSelect();

  qs("#btnDiscover")?.addEventListener("click", discover);
  qs("#btnScanSelected")?.addEventListener("click", scanSelected);
  qs("#btnClear")?.addEventListener("click", () => { companies=[]; jobs=[]; renderCompanies(); renderJobs(); });
  qs("#selectAll")?.addEventListener("change", (e) => { qsa(".rowSel").forEach(cb => cb.checked = e.target.checked); });

  ["#fltProvider","#fltRemote","#fltScore","#fltAge","#fltSalary","#onlyNew"].forEach(id => {
    const el = qs(id); if (el) el.addEventListener("change", renderJobs);
  });
  qs("#btnSaveSearch")?.addEventListener("click", saveCurrentSearch);
}

document.addEventListener("DOMContentLoaded", init);
window.addEventListener("load", init);
