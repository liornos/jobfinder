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
  const serverAutoRefreshEnabled = () => document.body?.dataset?.autoRefreshOnStart === "1";
  const refreshEnabled = () => document.body?.dataset?.refreshEnabled === "1";
  const refreshEndpoint = () => document.body?.dataset?.refreshEndpoint || "/refresh";
  const log = (...args) => console.log("[jobfinder]", ...args);
  const debug = (...args) => { if (isDebug()) console.debug("[jobfinder:debug]", ...args); };
  const err = (...args) => console.error("[jobfinder:error]", ...args);

  function saveLocal(key, val) { localStorage.setItem(key, JSON.stringify(val)); }
  function loadLocal(key, def) { try { return JSON.parse(localStorage.getItem(key)) ?? def; } catch { return def; } }

  function debounce(fn, delayMs) {
    let timer = null;
    return (...args) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delayMs);
    };
  }

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

  function normalizeText(value) {
    return (value ?? "").toString().toLowerCase().replace(/\s+/g, " ").trim();
  }

  function parseTitleKeywords(value) {
    const raw = (value ?? "").toString().trim();
    if (!raw) return [];
    const parts = raw.includes(",") ? raw.split(",") : raw.split(/\s+/);
    return parts.map(p => normalizeText(p)).filter(Boolean);
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

  function fmtDuration(ms) {
    if (ms === null || ms === undefined) return "";
    const val = Number(ms);
    if (!Number.isFinite(val)) return "";
    if (val < 1000) return `${Math.round(val)} ms`;
    return `${(val / 1000).toFixed(1)}s`;
  }

  function renderRefreshReport(payload) {
    const panel = qs("#refreshReportPanel");
    if (!panel) return;

    const summary = payload?.summary || {};
    const rows = Array.isArray(payload?.companies) ? payload.companies : [];
    if (!rows.length && !Object.keys(summary).length) {
      panel.style.display = "none";
      return;
    }

    panel.style.display = "";
    const now = new Date();
    setText(qs("#refreshReportTime"), now.toLocaleString());
    setText(qs("#reportLastRun"), now.toLocaleTimeString());

    const total = summary.companies_total ?? rows.length ?? 0;
    setText(qs("#reportCompaniesTotal"), String(total));
    setText(qs("#reportCompaniesOk"), String(summary.companies_ok ?? 0));
    setText(qs("#reportCompaniesFailed"), String(summary.companies_failed ?? 0));
    setText(qs("#reportJobsFetched"), String(summary.jobs_fetched ?? 0));
    setText(qs("#reportJobsWritten"), String(summary.jobs_written ?? 0));
    setText(qs("#reportElapsed"), fmtDuration(summary.elapsed_ms ?? 0));

    const body = qs("#refreshReportBody");
    if (!body) return;
    body.innerHTML = "";

    const orderedRows = rows
      .map((r) => ({
        row: r,
        status: (r?.status || "").toLowerCase(),
        fetched: Number(r?.jobs_fetched ?? 0),
      }))
      .sort((a, b) => {
        const aOk = a.status === "ok";
        const bOk = b.status === "ok";
        if (aOk !== bOk) return aOk ? 1 : -1;
        return b.fetched - a.fetched;
      })
      .map((entry) => entry.row);

    orderedRows.forEach((r) => {
      const status = (r?.status || "error").toLowerCase();
      const isOk = status === "ok";
      const name = r?.name || r?.org || "unknown";
      const provider = r?.provider || "";
      const org = r?.org || "";
      const metaParts = [];
      if (provider) metaParts.push(`provider: ${provider}`);
      if (org) metaParts.push(`org: ${org}`);
      if (r?.elapsed_ms !== undefined && r?.elapsed_ms !== null) {
        metaParts.push(`time: ${fmtDuration(r.elapsed_ms)}`);
      }
      const meta = metaParts.join(" | ");
      const errText = r?.error ? String(r.error) : "";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="p-2">
          <div class="font-medium">${escapeHtml(name)}</div>
          <div class="text-xs text-slate-500">${escapeHtml(meta)}</div>
        </td>
        <td class="p-2">
          <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${
            isOk
              ? "border-emerald-100 bg-emerald-50 text-emerald-700"
              : "border-red-100 bg-red-50 text-red-700"
          }">${isOk ? "OK" : "ERROR"}</span>
        </td>
        <td class="p-2 text-right">${escapeHtml(String(r?.jobs_fetched ?? 0))}</td>
        <td class="p-2 text-right">${escapeHtml(String(r?.jobs_written ?? 0))}</td>
        <td class="p-2 text-left text-xs ${isOk ? "text-slate-400" : "text-red-600"}">
          ${isOk ? "-" : escapeHtml(errText)}
        </td>
      `;
      body.appendChild(tr);
    });
  }

  const state = {
    companies: [],
    jobs: [],
    filtered: [],
    page: 1,
    pageSize: 50,
    sortSpec: [{ key: "score", dir: "desc" }],
    jobsReqId: 0,
    jobsAbort: null,
    lastScanIds: new Set(loadLocal("lastScanIds", [])),
    newIds: new Set(),
    initialized: false,
    scanInFlight: false,
    scanAbort: null,
  };

  const CITY_ALL_VALUE = "__all__";
  const CITY_ALL_LABEL = "Israel - All";

  const cityState = {
    selected: [],
    allIsrael: false,
  };

  const CITY_ALIASES = {
    // Normalize common spelling variations for city selection + filtering.
    "tel aviv": ["tel aviv", "tel-aviv", "tel aviv-yafo", "tel aviv yafo"],
    "tel aviv-yafo": ["tel aviv-yafo", "tel aviv yafo", "tel aviv"],
    "herzliya": ["herzliya", "hertzliya", "herzlia"],
    "kfar saba": ["kfar saba", "kfar sava"],
    "raanana": ["raanana", "ra'anana", "ra-anana", "ra anana"],
    "petach tikva": ["petach tikva", "petah tikva", "petach tikvah", "petah tikvah"],
    "petah tikva": ["petach tikva", "petah tikva", "petach tikvah", "petah tikvah"],
    "hod hasharon": ["hod hasharon", "hod ha-sharon", "hod ha sharon"],
    "netanya": ["netanya", "netnaya"],
    "ramat gan": ["ramat gan", "ramat-gan"],
    "bnei brak": ["bnei brak", "bnei-brak"],
    "givatayim": ["givatayim", "giv'atayim", "givataym"],
    "airport city": ["airport city", "airport-city"],
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
      tr.setAttribute("data-testid", "company-row");
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

  function computeFilteredJobs() {
    const prov = qs("#fltProvider")?.value || "";
    const minScore = parseInt(qs("#fltScore")?.value || "0", 10) || 0;
    const titleKeywords = parseTitleKeywords(qs("#fltTitle")?.value || "");

    const list = state.jobs.filter(j => {
      if (prov && (j.provider || "") !== prov) return false;
      if ((j.score || 0) < minScore) return false;

      if (titleKeywords.length) {
        const title = normalizeText(j?.title || "");
        if (!titleKeywords.some(k => title.includes(k))) return false;
      }
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
      tr.setAttribute("data-testid", "job-row");
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

  function isAllValue(value) {
    const normalized = (value ?? "").toString().trim().toLowerCase();
    return normalized === CITY_ALL_VALUE
      || normalized === CITY_ALL_LABEL.toLowerCase()
      || normalized === "israel all";
  }

  function parseCityValues(values) {
    const seen = new Set();
    const out = [];
    let all = false;
    (values || []).forEach((value) => {
      (value ?? "")
        .toString()
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach((city) => {
          if (isAllValue(city)) {
            all = true;
            return;
          }
          const key = city.toLowerCase();
          if (seen.has(key)) return;
          seen.add(key);
          out.push(city);
        });
    });
    return { cities: out, all };
  }

  function createCityChip(label, onRemove) {
    const chip = document.createElement("span");
    chip.className = "inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700";

    const text = document.createElement("span");
    text.textContent = label;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "text-slate-500 hover:text-slate-700";
    btn.textContent = "x";
    btn.setAttribute("aria-label", `Remove ${label}`);
    btn.addEventListener("click", onRemove);

    chip.appendChild(text);
    chip.appendChild(btn);
    return chip;
  }

  function renderSelectedCities() {
    const container = qs("#citiesSelected");
    if (!container) return;
    container.innerHTML = "";

    if (cityState.allIsrael) {
      container.appendChild(createCityChip(CITY_ALL_LABEL, () => clearSelectedCities()));
      return;
    }

    if (!cityState.selected.length) {
      const empty = document.createElement("span");
      empty.className = "text-xs text-slate-400";
      empty.textContent = "No cities selected.";
      container.appendChild(empty);
      return;
    }

    cityState.selected.forEach((city) => {
      container.appendChild(createCityChip(city, () => removeSelectedCity(city)));
    });
  }

  function addCitiesToSelection(values) {
    const parsed = parseCityValues(Array.isArray(values) ? values : [values]);
    if (parsed.all) {
      cityState.selected = [];
      cityState.allIsrael = true;
      renderSelectedCities();
      return;
    }

    if (!parsed.cities.length) return;
    const existing = new Set(cityState.selected.map((city) => city.toLowerCase()));
    parsed.cities.forEach((city) => {
      const key = city.toLowerCase();
      if (existing.has(key)) return;
      existing.add(key);
      cityState.selected.push(city);
    });
    cityState.allIsrael = false;
    renderSelectedCities();
  }

  function setSelectedCities(values) {
    const parsed = parseCityValues(Array.isArray(values) ? values : [values]);
    if (parsed.all) {
      cityState.selected = [];
      cityState.allIsrael = true;
    } else {
      cityState.selected = parsed.cities;
      cityState.allIsrael = false;
    }
    renderSelectedCities();
  }

  function clearSelectedCities() {
    cityState.selected = [];
    cityState.allIsrael = false;
    renderSelectedCities();
  }

  function removeSelectedCity(city) {
    const key = city.toLowerCase();
    cityState.selected = cityState.selected.filter((item) => item.toLowerCase() !== key);
    renderSelectedCities();
    state.page = 1;
    loadJobsFromDB({ silent: true });
  }

  function getSelectedCities() {
    return cityState.allIsrael ? [] : [...cityState.selected];
  }

  function setupCitySelect() {
    const select = qs("#citiesSelect");
    if (!select) return;

    const defaults = select.getAttribute("data-default-cities");
    if (defaults) setSelectedCities(defaults.split(","));
    else renderSelectedCities();

    select.addEventListener("change", () => {
      const value = select.value || "";
      if (!value) return;
      if (isAllValue(value)) {
        cityState.selected = [];
        cityState.allIsrael = true;
        renderSelectedCities();
      } else {
        addCitiesToSelection(value);
      }
      select.value = "";
      state.page = 1;
      loadJobsFromDB({ silent: true });
    });

    qs("#citiesClear")?.addEventListener("click", () => {
      clearSelectedCities();
      select.focus();
      state.page = 1;
      loadJobsFromDB({ silent: true });
    });
  }

  function buildJobsQuery(limitOverride) {
    const params = new URLSearchParams();
    const cities = expandCities(getSelectedCities());
    const keywords = parseListInput("#keywords");
    const titleKeywords = parseTitleKeywords(qs("#fltTitle")?.value || "");

    if (cities.length) params.set("cities", cities.join(","));
    if (keywords.length) params.set("keywords", keywords.join(","));
    if (titleKeywords.length) params.set("title_keywords", titleKeywords.join(","));

    const provider = qs("#fltProvider")?.value || "";
    const minScore = parseInt(qs("#fltScore")?.value || "0", 10) || 0;
    const maxAge = qs("#fltAge")?.value;

    if (provider) params.set("provider", provider);
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

    const reqId = ++state.jobsReqId;
    try { state.jobsAbort?.abort?.(); } catch {}
    state.jobsAbort = new AbortController();

    try {
      const { ok, data } = await fetchJSON(url, { signal: state.jobsAbort.signal });
      if (reqId !== state.jobsReqId) return;
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
      if (reqId !== state.jobsReqId) return;
      if (e?.name === "AbortError") return;
      if (state.jobsAbort?.signal?.aborted) return;
      err("Jobs fetch error", e);
      if (!silent) setScanMsg("Failed to load jobs", "error");
    }
  }

  async function discover() {
    setDiscoverMsg("Discovering...", "info");
    log("Discover clicked");

    const cities = expandCities(getSelectedCities());
    const keywords = parseListInput("#keywords");

    // Keep aligned with backend pipeline._PROVIDER_HOST
    const DEFAULT_SOURCES = ["greenhouse", "lever", "smartrecruiters", "breezy", "comeet", "workday", "recruitee", "jobvite", "icims", "workable"];
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

    if (!refreshEnabled()) {
      if (!silent) {
        setScanMsg("Refresh disabled in this service. Use a scheduled refresh job.", "info");
      }
      return;
    }

    const selected = selectedCompanies();
    if (!selected.length) {
      if (!silent) setDiscoverMsg("Select at least one company", "error");
      return;
    }

    const cities = expandCities(getSelectedCities());
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
      const endpoint = refreshEndpoint();
      const { ok, data } = await fetchJSON(endpoint, { method: "POST", body, signal: state.scanAbort.signal });
      if (!ok) {
        const msg = (data && data.error) ? String(data.error) : "Refresh failed";
        setScanMsg(msg, "error");
        return;
      }

      const summary = data?.summary || {};
      renderRefreshReport(data);
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
    renderRefreshReport(null);
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

  function setupDrawer() {
    const close = qs("#closeDrawer");
    const drawer = qs("#drawer");
    close?.addEventListener("click", () => drawer?.classList.add("hidden"));
    drawer?.addEventListener("click", (e) => { if (e.target?.id === "drawer") drawer.classList.add("hidden"); });
  }

  function setupFilters() {
    ["#fltProvider", "#fltScore", "#fltAge"].forEach(id => {
      qs(id)?.addEventListener("change", () => {
        state.page = 1;
        loadJobsFromDB({ silent: true });
      });
    });

    const titleInput = qs("#fltTitle");
    if (titleInput) {
      const debouncedReload = debounce(() => loadJobsFromDB({ silent: true }), 300);
      titleInput.addEventListener("input", () => {
        state.page = 1;
        renderJobs();
        debouncedReload();
      });
    }
  }

  function extractCities(companies) {
    return Array.from(new Set((companies || []).map(c => (c.city || "").trim()).filter(Boolean)));
  }

  function setCitiesInput(cities) {
    if (!cities?.length) {
      clearSelectedCities();
      return;
    }
    setSelectedCities(cities);
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
    setupDrawer();
    setupFilters();
    setupCitySelect();

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
    if (!refreshEnabled()) {
      const btn = qs("#btnScanSelected");
      if (btn) {
        btn.disabled = true;
        btn.setAttribute("aria-disabled", "true");
      }
      setScanMsg("Refresh disabled in this service. Use a scheduled refresh job.", "info");
    }

    if (!isE2eMode() && refreshEnabled() && !serverAutoRefreshEnabled()) {
      autoRefreshOnStartup();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
  window.addEventListener("load", init);
})();
