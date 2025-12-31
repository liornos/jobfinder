// jobfinder/static/app.js
// Patch: make Discover robust when backend /discover is not implemented (501) or SerpAPI key is missing.
// Also: if #sources is a <select multiple> and user selects nothing, fall back to default provider list.

(() => {
  "use strict";

  const qs = (sel) => document.querySelector(sel);
  const qsa = (sel) => Array.from(document.querySelectorAll(sel));

  const uid = () => Math.random().toString(16).slice(2) + "-" + Date.now().toString(16);

  const isDebug = () => (localStorage.getItem("jobfinder_debug") || "") === "1";
  const isE2eMode = () => new URLSearchParams(window.location.search).has("e2e");
  const log = (...args) => console.log("[jobfinder]", ...args);
  const debug = (...args) => { if (isDebug()) console.debug("[jobfinder:debug]", ...args); };
  const err = (...args) => console.error("[jobfinder:error]", ...args);

  function saveLocal(key, val) { localStorage.setItem(key, JSON.stringify(val)); }
  function loadLocal(key, def) { try { return JSON.parse(localStorage.getItem(key)) ?? def; } catch { return def; } }

  function escapeHtml(s) {
    return (s ?? "").toString().replace(/[&<>"']/g, m => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[m]));
  }

  function sanitizeToText(html) {
    const div = document.createElement("div");
    div.innerHTML = html || "";
    div.querySelectorAll("script,style,iframe,object,embed,link").forEach(n => n.remove());
    return div.textContent || div.innerText || "";
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 10);
  }

  function setText(el, text) { if (el) el.textContent = text ?? ""; }

  function setDiscoverMsg(text, kind = "info") {
    const el = qs("#discoverMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "mt-3 text-base font-semibold";
    if (kind === "error") el.classList.add("text-red-600");
    else if (kind === "ok") el.classList.add("text-green-700");
    else el.classList.add("text-gray-800");
  }

  function setScanMsg(text, kind = "info") {
    const msg = qs("#scanMsg");
    if (!msg) return;
    msg.textContent = text || "";
    msg.className = "text-sm mt-2 font-semibold";
    if (!text) msg.classList.add("text-gray-600");
    else if (kind === "error") msg.classList.add("text-red-600");
    else if (kind === "ok") msg.classList.add("text-green-700");
    else msg.classList.add("text-gray-800");
  }

  function setScanLoading(isLoading, text = "Refreshing...") {
    const btn = qs("#btnScanSelected");
    const txt = qs("#scanBtnText");
    const spn = qs("#scanSpinner");
    if (!btn) return;

    if (isLoading) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
      btn.classList.add("opacity-70", "cursor-not-allowed");
      if (txt) txt.textContent = text;
      if (spn) spn.classList.remove("hidden");
      setScanMsg(text, "info");
    } else {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.classList.remove("opacity-70", "cursor-not-allowed");
      if (txt) txt.textContent = "Refresh jobs";
      if (spn) spn.classList.add("hidden");
      setScanMsg("", "info");
    }
  }

  const state = {
    companies: [],
    jobs: [],
    filtered: [],
    page: 1,
    pageSize: 50,
    sortSpec: [{ key: "score", dir: "desc" }],
    lastScanIds: new Set(loadLocal("lastScanIds", [])),
    newIds: new Set(),
    initialized: false,
    scanInFlight: false,
    scanAbort: null,
    autoRefreshTimer: null,
  };

  const CITY_ALIASES = {
    // Normalize Ra'anana variants and nearby spellings that often appear in postings.
    "raanana": ["raanana", "ra'anana"],
  };

  function expandCities(list) {
    const seen = new Set();
    const out = [];
    (list || []).forEach((raw) => {
      const base = (raw || "").trim();
      if (!base) return;
      const variants = [base, ...(CITY_ALIASES[base.toLowerCase()] || [])];
      variants.forEach((v) => {
        const norm = (v || "").trim();
        if (!norm) return;
        const key = norm.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out.push(norm);
      });
    });
    return out;
  }

  async function fetchJSON(path, { method = "GET", body = undefined, signal = undefined } = {}) {
    const rid = uid();
    const t0 = performance.now();
    debug("request", rid, method, path, body);

    const headers = { "content-type": "application/json", "x-jobfinder-request-id": rid };
    const resp = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });

    let data = null;
    const text = await resp.text();
    try { data = text ? JSON.parse(text) : null; }
    catch { data = { error: text || "Invalid JSON response" }; }

    const dt = Math.round(performance.now() - t0);
    debug("response", rid, resp.status, `${dt}ms`, data);

    return { ok: resp.ok, status: resp.status, data };
  }

  function renderCompanies() {
    const body = qs("#companiesBody");
    if (!body) return;
    body.innerHTML = "";

    state.companies.forEach((c, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="p-2"><input type="checkbox" class="rowSel" data-i="${i}"></td>
        <td class="p-2">${escapeHtml(c.name || "")}</td>
      `;
      body.appendChild(tr);
    });

    const selectAll = qs("#selectAll");
    if (selectAll) selectAll.checked = false;

    // Re-filter jobs when company selection changes
    body.querySelectorAll(".rowSel").forEach(cb => {
      cb.addEventListener("change", () => {
        state.page = 1;
        loadJobsFromDB({ silent: true });
      });
    });
  }

  function badgeWorkMode(job) {
    const wm = (job?.extra?.work_mode || "").toLowerCase();
    if (!wm) return "";
    const label = wm === "remote" ? "Remote" : wm === "hybrid" ? "Hybrid" : "Onsite";
    return `<span class="text-xs bg-gray-100 rounded px-2 py-1 ml-2">${label}</span>`;
  }

  function extractSkills(job) {
    const kwEl = qs("#keywords");
    const kws = (kwEl?.value || "")
      .split(",")
      .map(s => s.trim().toLowerCase())
      .filter(Boolean);

    const text = `${job?.title || ""} ${sanitizeToText(job?.extra?.description || "")}`.toLowerCase();
    const hits = new Set();
    for (const k of kws) if (k && text.includes(k)) hits.add(k);
    return Array.from(hits).slice(0, 20);
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
      <div class="text-sm whitespace-pre-wrap">${escapeHtml(sanitizeToText(job.extra?.description || ""))}</div>
    `;
    el.classList.remove("hidden");
  }

  function matchRemote(job, sel) {
    const wm = (job?.extra?.work_mode || "").toLowerCase();
    if (sel === "any") return true;
    if (sel === "hybrid") return wm === "hybrid";
    if (sel === "true")  return wm ? wm === "remote" : Boolean(job.remote) === true;
    if (sel === "false") return wm ? wm === "onsite" : Boolean(job.remote) === false;
    return true;
  }

  function computeFilteredJobs() {
    const prov = qs("#fltProvider")?.value || "";
    const remoteSel = qs("#fltRemote")?.value || "any";
    const minScore = parseInt(qs("#fltScore")?.value || "0", 10) || 0;
    const minSalary = parseInt(qs("#fltSalary")?.value || "0", 10) || 0;
    const onlyNew = !!qs("#onlyNew")?.checked;

    const list = state.jobs.filter(j => {
      if (prov && (j.provider || "") !== prov) return false;
      if (!matchRemote(j, remoteSel)) return false;
      if ((j.score || 0) < minScore) return false;

      const smin = Number(j?.extra?.salary_min || 0);
      const smax = Number(j?.extra?.salary_max || 0);
      if (minSalary && Math.max(smin, smax) < minSalary) return false;

      if (onlyNew && !state.newIds.has(j.id)) return false;
      return true;
    });

    const spec = state.sortSpec.length ? state.sortSpec : [{ key: "score", dir: "desc" }];
    list.sort((a, b) => {
      for (const s of spec) {
        let av = a[s.key], bv = b[s.key];
        if (s.key === "created_at") { av = av || ""; bv = bv || ""; }
        const cmp = (av > bv) - (av < bv);
        if (cmp !== 0) return s.dir === "asc" ? cmp : -cmp;
      }
      return 0;
    });

    return list;
  }

  function renderJobs() {
    state.filtered = computeFilteredJobs();

    state.pageSize = parseInt(qs("#pageSize")?.value || "50", 10) || 50;
    const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));

    if (state.page < 1) state.page = 1;
    if (state.page > totalPages) state.page = totalPages;

    const start = (state.page - 1) * state.pageSize;
    const rows = state.filtered.slice(start, start + state.pageSize);

    const body = qs("#jobsBody");
    if (!body) return;

    body.innerHTML = "";
    for (const j of rows) {
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
    }

    setText(qs("#jobsCount"), String(state.filtered.length));
    setText(qs("#newCount"), String(state.newIds.size));
    setText(qs("#pageInfo"), `${state.page} / ${totalPages}`);

    const prev = qs("#prevPage");
    const next = qs("#nextPage");
    if (prev) prev.disabled = state.page <= 1;
    if (next) next.disabled = state.page >= totalPages;
  }

  function showPanelsAfterDiscover() {
    const companiesPanel = qs("#companiesPanel");
    const scanFiltersPanel = qs("#scanFiltersPanel");
    if (companiesPanel) companiesPanel.style.display = "";
    if (scanFiltersPanel) scanFiltersPanel.style.display = "";
  }

  async function loadSeedCompanies(reasonText, cities = []) {
    setDiscoverMsg("Loading seed companies...", "info");
    try {
      const r = await fetch("/static/companies.json", { cache: "no-cache" });
      const data = await r.json();
      const list = data?.companies ?? data;

      if (!Array.isArray(list) || !list.length) {
        setDiscoverMsg("Seed file empty or invalid", "error");
        return [];
      }

      let filtered = list;
      if (cities && cities.length > 0) {
        const normalizedCities = expandCities(cities).map(c => c.trim().toLowerCase()).filter(Boolean);
        filtered = list.filter(c => {
          const companyCity = (c.city || "").toLowerCase();
          return normalizedCities.some(city => companyCity.includes(city));
        });
      }

      state.companies = filtered;
      renderCompanies();
      showPanelsAfterDiscover();
      setDiscoverMsg(reasonText || `Loaded ${state.companies.length} seed companies`, "ok");
      return state.companies;
    } catch (e) {
      err("Seed load error", e);
      setDiscoverMsg("Failed to load seed companies", "error");
      return [];
    }
  }

  function parseListInput(sel) {
    return (qs(sel)?.value || "")
      .split(",")
      .map(s => s.trim())
      .filter(Boolean);
  }

  function buildJobsQuery(limitOverride) {
    const params = new URLSearchParams();
    const cities = expandCities(parseListInput("#cities"));
    const keywords = parseListInput("#keywords");

    if (cities.length) params.set("cities", cities.join(","));
    if (keywords.length) params.set("keywords", keywords.join(","));

    const provider = qs("#fltProvider")?.value || "";
    const remote = qs("#fltRemote")?.value || "any";
    const minScore = parseInt(qs("#fltScore")?.value || "0", 10) || 0;
    const maxAge = qs("#fltAge")?.value;

    if (provider) params.set("provider", provider);
    if (remote) params.set("remote", remote);
    if (minScore) params.set("min_score", String(minScore));
    if (maxAge) params.set("max_age_days", maxAge);

    const selected = selectedCompanies();
    if (selected.length) {
      params.set("orgs", selected.map(c => c.org || c.name || "").filter(Boolean).join(","));
    }

    const limit = limitOverride || 500;
    params.set("limit", String(limit));

    return params;
  }

  async function loadJobsFromDB({ afterRefresh = false, silent = false } = {}) {
    const params = buildJobsQuery();
    const url = `/jobs?${params.toString()}`;

    try {
      const { ok, data } = await fetchJSON(url);
      if (!ok) {
        const msg = (data && data.error) ? String(data.error) : "Failed to load jobs";
        setScanMsg(msg, "error");
        return;
      }

      state.jobs = data?.results || [];
      const curIds = new Set(state.jobs.map(j => j?.id).filter(Boolean));
      const prev = new Set(loadLocal("lastScanIds", []));
      state.lastScanIds = prev;

      if (afterRefresh) {
        state.newIds = new Set([...curIds].filter(x => !prev.has(x)));
        saveLocal("lastScanIds", [...curIds]);
      } else {
        state.newIds = new Set([...curIds].filter(x => !prev.has(x)));
      }

      state.page = 1;
      renderJobs();
      if (!silent) setScanMsg(`Loaded ${state.jobs.length} jobs`, "ok");
    } catch (e) {
      err("Jobs fetch error", e);
      if (!silent) setScanMsg("Failed to load jobs", "error");
    }
  }

  async function discover() {
    setDiscoverMsg("Discovering...", "info");
    log("Discover clicked");

    const cities = expandCities(parseListInput("#cities"));
    const keywords = parseListInput("#keywords");

    // Keep aligned with backend pipeline._PROVIDER_HOST
    const DEFAULT_SOURCES = ["greenhouse", "lever", "ashby", "smartrecruiters", "breezy", "comeet", "workday", "recruitee", "jobvite", "icims", "workable"];
    const sourcesEl = qs("#sources");

    let sources =
      sourcesEl?.tagName === "SELECT"
        ? Array.from(sourcesEl.selectedOptions || []).map(o => o.value).filter(Boolean)
        : (sourcesEl?.value || DEFAULT_SOURCES.join(","))
            .split(",").map(s => s.trim()).filter(Boolean);

    // If using multi-select and user selected nothing -> default back
    if (!sources.length) sources = DEFAULT_SOURCES.slice();

    const limit = parseInt(qs("#limit")?.value || "1000", 10) || 1000;

    try {
      const { ok, status, data } = await fetchJSON("/discover", {
        method: "POST",
        body: { cities, keywords, sources, limit }
      });

      if (!ok) {
        const msg = (data && data.error) ? String(data.error) : "Discover failed";

        const missingKey = /SERPAPI.*KEY|MISSING API KEY/i.test(msg);
        const notImplemented = status === 501 || /not implemented/i.test(msg);

        // Robust fallback: if SerpAPI is missing OR discover isn't implemented, use seed file
        if (missingKey) {
          await loadSeedCompanies(null, cities);
          return;
        }

        if (notImplemented) {
          await loadSeedCompanies(`${msg}; loaded seed data.`, cities);
          return;
        }

        setDiscoverMsg(msg, "error");
        return;
      }

      state.companies = data?.companies || [];
      renderCompanies();
      showPanelsAfterDiscover();
      const countMsg = state.companies.length ? `Found ${state.companies.length} companies` : "No companies found";
      const prefix = "RUNNING WITH API KEY - INTERNAL ONLY";
      setDiscoverMsg(
        state.companies.length ? `${prefix}. ${countMsg}` : `${prefix}. ${countMsg}`,
        state.companies.length ? "ok" : "error"
      );
    } catch (e) {
      err("Discover error", e);
      setDiscoverMsg("Network error", "error");
    }
  }

  function selectedCompanies() {
    return qsa(".rowSel:checked")
      .map(cb => state.companies[parseInt(cb.dataset.i, 10)])
      .filter(Boolean);
  }

  async function refreshSelected({ silent = false } = {}) {
    if (state.scanInFlight) {
      debug("refresh: already running, skipping");
      return;
    }

    const selected = selectedCompanies();
    if (!selected.length) {
      if (!silent) setDiscoverMsg("Select at least one company", "error");
      return;
    }

    const cities = parseListInput("#cities");
    const keywords = parseListInput("#keywords");

    const body = {
      cities,
      keywords,
      companies: selected,
      provider: (qs("#fltProvider")?.value || undefined),
    };

    try { state.scanAbort?.abort?.(); } catch {}
    state.scanAbort = new AbortController();
    let timedOut = false;
    const timeoutMs = 120000;
    const timeoutId = setTimeout(() => {
      timedOut = true;
      try { state.scanAbort.abort("timeout"); } catch {}
    }, timeoutMs);

    state.scanInFlight = true;
    setScanLoading(true, "Refreshing jobs...");

    try {
      const { ok, data } = await fetchJSON("/refresh", { method: "POST", body, signal: state.scanAbort.signal });
      if (!ok) {
        const msg = (data && data.error) ? String(data.error) : "Refresh failed";
        setScanMsg(msg, "error");
        return;
      }

      const summary = data?.summary || {};
      await loadJobsFromDB({ afterRefresh: true, silent: true });
      setScanMsg(
        `Refreshed ${summary.jobs_written ?? state.jobs.length} jobs (${state.newIds.size} new)`,
        "ok"
      );
    } catch (e) {
      if (e?.name === "AbortError") {
        if (timedOut) setScanMsg("Refresh timed out, please try again or narrow selection", "error");
        return;
      }
      err("Refresh error", e);
      setScanMsg("Refresh failed (network error)", "error");
    } finally {
      clearTimeout(timeoutId);
      state.scanInFlight = false;
      setScanLoading(false);
    }
  }

  function clearAll() {
    state.companies = [];
    state.jobs = [];
    state.filtered = [];
    state.page = 1;
    state.newIds = new Set();
    renderCompanies();
    renderJobs();
    setDiscoverMsg("", "info");
    setScanMsg("", "info");
  }

  function setupSort() {
    qsa("th.sort").forEach(th => {
      th.addEventListener("click", (e) => {
        const key = th.dataset.key;
        const shift = e.shiftKey;

        const existing = state.sortSpec.find(s => s.key === key);
        if (existing) {
          existing.dir = existing.dir === "asc" ? "desc" : "asc";
        } else {
          if (!shift) state.sortSpec = [];
          state.sortSpec.push({ key, dir: "asc" });
        }
        renderJobs();
      });
    });
  }

  function setupPaging() {
    qs("#prevPage")?.addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      renderJobs();
    });
    qs("#nextPage")?.addEventListener("click", () => {
      state.page = state.page + 1;
      renderJobs();
    });
    qs("#pageSize")?.addEventListener("change", () => {
      state.page = 1;
      renderJobs();
    });
  }

  function setupAutoRefresh() {
    const chk = qs("#autoRefresh");
    const sel = qs("#refreshInterval");
    const update = () => {
      if (state.autoRefreshTimer) {
        clearInterval(state.autoRefreshTimer);
        state.autoRefreshTimer = null;
      }
      if (chk && sel && chk.checked) {
        const seconds = parseInt(sel.value, 10) || 30;
        state.autoRefreshTimer = setInterval(() => refreshSelected({ silent: true }), seconds * 1000);
      }
    };
    chk?.addEventListener("change", update);
    sel?.addEventListener("change", update);
    update();
  }

  function setupDrawer() {
    const close = qs("#closeDrawer");
    const drawer = qs("#drawer");
    close?.addEventListener("click", () => drawer?.classList.add("hidden"));
    drawer?.addEventListener("click", (e) => { if (e.target?.id === "drawer") drawer.classList.add("hidden"); });
  }

  function setupFilters() {
    ["#fltProvider", "#fltRemote", "#fltScore", "#fltAge", "#fltSalary", "#onlyNew"].forEach(id => {
      qs(id)?.addEventListener("change", () => {
        state.page = 1;
        if (id === "#onlyNew") {
          renderJobs();
        } else {
          loadJobsFromDB({ silent: true });
        }
      });
    });
  }

  function extractCities(companies) {
    return Array.from(new Set((companies || []).map(c => (c.city || "").trim()).filter(Boolean)));
  }

  function setCitiesInput(cities) {
    if (!cities?.length) return;
    const input = qs("#cities");
    if (!input) return;
    input.value = cities.join(", ");
  }

  function selectAllCompanies() {
    const selectAll = qs("#selectAll");
    qsa(".rowSel").forEach(cb => cb.checked = true);
    if (selectAll) selectAll.checked = true;
  }

  async function autoRefreshOnStartup() {
    try {
      const companies = await loadSeedCompanies("Auto-loaded seed companies for startup refresh");
      if (!Array.isArray(companies) || !companies.length) {
        debug("Auto refresh skipped: no seed companies found");
        return;
      }

      setCitiesInput(extractCities(companies));
      selectAllCompanies();
      setScanMsg("Auto refreshing all seed companies...", "info");
      await refreshSelected({ silent: true });
    } catch (e) {
      err("Auto refresh on startup failed", e);
      setScanMsg("Auto refresh on startup failed", "error");
    }
  }

  function init() {
    if (state.initialized) return;
    state.initialized = true;

    log("app.js loaded");
    renderCompanies();
    renderJobs();
    setupSort();
    setupPaging();
    setupAutoRefresh();
    setupDrawer();
    setupFilters();

    qs("#btnDiscover")?.addEventListener("click", discover);
    qs("#btnScanSelected")?.addEventListener("click", () => refreshSelected({ silent: false }));
    qs("#btnClear")?.addEventListener("click", clearAll);

    qs("#selectAll")?.addEventListener("change", (e) => {
      const checked = !!e.target.checked;
      qsa(".rowSel").forEach(cb => cb.checked = checked);
      state.page = 1;
      loadJobsFromDB({ silent: true });
    });

    // Load any existing jobs already in the DB so filters/pagination stay fast
    loadJobsFromDB({ silent: true });
    if (!isE2eMode()) autoRefreshOnStartup();
  }

  document.addEventListener("DOMContentLoaded", init);
  window.addEventListener("load", init);
})();
