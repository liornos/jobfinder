(() => {
  "use strict";

  const qs = (sel) => document.querySelector(sel);

  const state = {
    jobs: [],
    baseJobs: [],
    baseCitiesKey: "",
    inFlight: false,
  };

  const CITY_ALL_VALUE = "__all__";
  const CITY_ALL_LABEL = "Israel - All";
  const DEFAULT_LIMIT = 200;
  const BASE_LIMIT = 200;

  const cityState = {
    selected: [],
    allIsrael: false,
  };

  function escapeHtml(value) {
    return (value ?? "").toString().replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[m]));
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 10);
  }

  function setStatus(text, kind = "info") {
    const el = qs("#statusMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "text-sm font-semibold mt-2";
    if (!text) el.classList.add("text-slate-600");
    else if (kind === "error") el.classList.add("text-red-600");
    else if (kind === "ok") el.classList.add("text-emerald-700");
    else el.classList.add("text-slate-700");
  }

  function setLoading(isLoading) {
    const btn = qs("#searchBtn");
    const text = qs("#searchBtnText");
    const spinner = qs("#searchSpinner");
    if (!btn) return;

    btn.disabled = isLoading;
    btn.classList.toggle("opacity-70", isLoading);
    btn.classList.toggle("cursor-not-allowed", isLoading);
    if (text) text.textContent = isLoading ? "Searching..." : "Search";
    if (spinner) spinner.classList.toggle("hidden", !isLoading);
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
    const container = qs("#citySelected");
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
  }

  function getSelectedCities() {
    return cityState.allIsrael ? [] : [...cityState.selected];
  }

  function setupCitySelect() {
    const select = qs("#citySelect");
    if (!select) return;
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
    });

    qs("#cityClear")?.addEventListener("click", () => {
      clearSelectedCities();
      select.focus();
    });
  }

  function parseTitleKeywords(value) {
    const raw = (value ?? "").toString().trim();
    if (!raw) return [];
    const parts = raw.includes(",") ? raw.split(",") : raw.split(/\s+/);
    return parts.map((s) => s.trim()).filter(Boolean);
  }

  function normalizeText(value) {
    return (value ?? "").toString().toLowerCase().replace(/\s+/g, " ").trim();
  }

  function filterByTitleKeywords(rows, keywords) {
    const needles = (keywords || []).map(normalizeText).filter(Boolean);
    if (!needles.length) return rows || [];
    return (rows || []).filter((row) => {
      const title = normalizeText(row?.title || "");
      return needles.some((needle) => title.includes(needle));
    });
  }

  function buildCitiesKey(cities) {
    return (cities || [])
      .map((city) => normalizeText(city))
      .filter(Boolean)
      .sort()
      .join("|");
  }

  function buildQuery({ includeTitle = true, limit = DEFAULT_LIMIT } = {}) {
    const params = new URLSearchParams();
    const cities = getSelectedCities();
    const titleKeywords = parseTitleKeywords(qs("#titleInput")?.value || "");

    if (cities.length) params.set("cities", cities.join(","));
    if (includeTitle && titleKeywords.length) params.set("title_keywords", titleKeywords.join(","));
    params.set("fast", "1");
    params.set("limit", String(limit));

    return { params, cities, titleKeywords };
  }

  function getSearchContext() {
    const { cities, titleKeywords } = buildQuery({ includeTitle: false, limit: BASE_LIMIT });
    const hasCityFilter = cities.length > 0;
    const citiesKey = hasCityFilter ? buildCitiesKey(cities) : "";
    return { cities, titleKeywords, hasCityFilter, citiesKey };
  }

  function applyCachedFilter(ctx, { updateStatus = true } = {}) {
    if (!ctx.hasCityFilter || state.baseCitiesKey !== ctx.citiesKey) return false;
    state.jobs = filterByTitleKeywords(state.baseJobs, ctx.titleKeywords);
    renderResults();
    if (!updateStatus) return true;

    if (state.jobs.length) {
      const msg = ctx.titleKeywords.length
        ? `Filtered ${state.jobs.length} jobs`
        : `Loaded ${state.jobs.length} jobs`;
      setStatus(msg, "ok");
    } else {
      setStatus("No jobs found", "info");
    }
    return true;
  }

  function renderResults() {
    const body = qs("#resultsBody");
    const countEl = qs("#resultsCount");
    if (!body) return;

    body.innerHTML = "";

    if (!state.jobs.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="p-3 text-sm text-gray-500" colspan="6">No jobs found.</td>`;
      body.appendChild(tr);
      if (countEl) countEl.textContent = "0";
      return;
    }

    for (const job of state.jobs) {
      const url = (job?.url || "").toString();
      const tr = document.createElement("tr");
      tr.className = "hover:bg-gray-50";

      if (url) {
        tr.classList.add("cursor-pointer");
        tr.addEventListener("click", () => window.open(url, "_blank", "noopener"));
      }

      const link = url
        ? `<a class="text-blue-600 underline" target="_blank" rel="noopener" href="${escapeHtml(url)}" onclick="event.stopPropagation()">open</a>`
        : "";

      tr.innerHTML = `
        <td class="p-2">${escapeHtml(job?.title || "")}</td>
        <td class="p-2">${escapeHtml(job?.company || "")}</td>
        <td class="p-2">${escapeHtml(job?.location || "")}</td>
        <td class="p-2">${escapeHtml(job?.provider || "")}</td>
        <td class="p-2">${fmtDate(job?.created_at)}</td>
        <td class="p-2">${link}</td>
      `;
      body.appendChild(tr);
    }

    if (countEl) countEl.textContent = String(state.jobs.length);
  }

  async function fetchJobs() {
    if (state.inFlight) return;
    const ctx = getSearchContext();

    if (applyCachedFilter(ctx, { updateStatus: true })) return;

    if (!ctx.hasCityFilter) {
      state.baseJobs = [];
      state.baseCitiesKey = "";
    }

    state.inFlight = true;
    setLoading(true);
    setStatus("Loading jobs...", "info");

    const query = ctx.hasCityFilter
      ? buildQuery({ includeTitle: false, limit: BASE_LIMIT })
      : buildQuery({ includeTitle: true, limit: DEFAULT_LIMIT });
    const url = `/jobs?${query.params.toString()}`;

    try {
      const resp = await fetch(url);
      const text = await resp.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = { error: text || "Invalid response" };
      }

      if (!resp.ok) {
        const msg = data?.error ? String(data.error) : "Failed to load jobs";
        setStatus(msg, "error");
        return;
      }

      const results = data?.results || [];
      if (ctx.hasCityFilter) {
        state.baseJobs = results;
        state.baseCitiesKey = ctx.citiesKey;
        state.jobs = filterByTitleKeywords(state.baseJobs, ctx.titleKeywords);
      } else {
        state.jobs = results;
      }

      renderResults();
      const count = state.jobs.length;
      const msg = count
        ? (ctx.hasCityFilter && ctx.titleKeywords.length ? `Filtered ${count} jobs` : `Loaded ${count} jobs`)
        : "No jobs found";
      setStatus(msg, count ? "ok" : "info");
    } catch (e) {
      setStatus("Failed to load jobs", "error");
    } finally {
      state.inFlight = false;
      setLoading(false);
    }
  }

  function setupTitleInput() {
    const input = qs("#titleInput");
    if (!input) return;
    input.addEventListener("input", () => {
      if (state.inFlight) return;
      const ctx = getSearchContext();
      applyCachedFilter(ctx, { updateStatus: true });
    });
  }

  function loadFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const cityList = params.getAll("cities");
    const city = cityList.length ? cityList : params.get("city") || params.get("cities");
    const title = params.get("title") || params.get("title_keywords");

    if (city) {
      const values = Array.isArray(city) ? city : String(city).split(",");
      setSelectedCities(values);
    }
    if (!city) {
      clearSelectedCities();
    }
    if (title) {
      const input = qs("#titleInput");
      if (input) input.value = title;
    }

    if (city || title) fetchJobs();
  }

  function init() {
    qs("#searchForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      fetchJobs();
    });
    setupCitySelect();
    setupTitleInput();
    renderSelectedCities();
    renderResults();
    loadFromQuery();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
