(() => {
  "use strict";

  const qs = (sel) => document.querySelector(sel);

  const state = {
    jobs: [],
    baseJobs: [],
    baseCitiesKey: "",
    baseLimit: 0,
    baseFetched: false,
    inFlight: false,
    pendingSearch: false,
    pendingForce: false,
  };

  const CITY_ALL_VALUE = "__all__";
  const CITY_ALL_LABEL = "Israel - All";
  const DEFAULT_LIMIT = 200;
  const BASE_LIMITS = [600, 1200, 2000];
  const TARGET_RESULTS = 40;

  const cityState = {
    selected: [],
    allIsrael: false,
  };

  const titleState = {
    selected: [],
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

  function createChip(label, onRemove) {
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
      container.appendChild(createChip(CITY_ALL_LABEL, () => {
        clearSelectedCities();
        triggerAutoSearch();
      }));
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
      container.appendChild(createChip(city, () => removeSelectedCity(city)));
    });
  }

  function renderSelectedTitles() {
    const container = qs("#titleSelected");
    if (!container) return;
    container.innerHTML = "";

    if (!titleState.selected.length) {
      const empty = document.createElement("span");
      empty.className = "text-xs text-slate-400";
      empty.textContent = "No titles selected.";
      container.appendChild(empty);
      return;
    }

    titleState.selected.forEach((title) => {
      container.appendChild(createChip(title, () => removeSelectedTitle(title)));
    });
  }

  function triggerAutoSearch() {
    fetchJobs();
    fetchJobs({ forceServer: true });
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
    triggerAutoSearch();
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
      triggerAutoSearch();
    });

    qs("#cityClear")?.addEventListener("click", () => {
      clearSelectedCities();
      triggerAutoSearch();
      select.focus();
    });
  }

  function parseTitleValues(values) {
    const seen = new Set();
    const out = [];
    (Array.isArray(values) ? values : [values]).forEach((value) => {
      (value ?? "")
        .toString()
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach((title) => {
          const key = title.toLowerCase();
          if (seen.has(key)) return;
          seen.add(key);
          out.push(title);
        });
    });
    return out;
  }

  function addTitlesToSelection(values) {
    const titles = parseTitleValues(Array.isArray(values) ? values : [values]);
    if (!titles.length) return;
    const existing = new Set(titleState.selected.map((title) => title.toLowerCase()));
    titles.forEach((title) => {
      const key = title.toLowerCase();
      if (existing.has(key)) return;
      existing.add(key);
      titleState.selected.push(title);
    });
    renderSelectedTitles();
  }

  function setSelectedTitles(values) {
    titleState.selected = parseTitleValues(values);
    renderSelectedTitles();
  }

  function clearSelectedTitles() {
    titleState.selected = [];
    renderSelectedTitles();
  }

  function removeSelectedTitle(title) {
    const key = title.toLowerCase();
    titleState.selected = titleState.selected.filter((item) => item.toLowerCase() !== key);
    renderSelectedTitles();
    triggerAutoSearch();
  }

  function getSelectedTitles() {
    return [...titleState.selected];
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

  function buildQuery({
    includeTitle = true,
    limit = DEFAULT_LIMIT,
    cities,
    titleKeywords,
  } = {}) {
    const params = new URLSearchParams();
    const citiesVal = Array.isArray(cities) ? cities : getSelectedCities();
    const titleVal = Array.isArray(titleKeywords)
      ? titleKeywords
      : getSelectedTitles();

    if (citiesVal.length) params.set("cities", citiesVal.join(","));
    if (includeTitle && titleVal.length) params.set("title_keywords", titleVal.join(","));
    params.set("fast", "1");
    params.set("lite", "1");
    params.set("limit", String(limit));

    return { params, cities: citiesVal, titleKeywords: titleVal };
  }

  function getSearchContext() {
    const cities = getSelectedCities();
    const titleKeywords = getSelectedTitles();
    const hasCityFilter = cities.length > 0;
    const citiesKey = hasCityFilter ? buildCitiesKey(cities) : "";
    return { cities, titleKeywords, hasCityFilter, citiesKey };
  }

  function applyCachedFilter(ctx, { updateStatus = true } = {}) {
    if (!state.baseFetched || state.baseCitiesKey !== ctx.citiesKey) return false;
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

  function nextBaseLimit(current) {
    for (const lim of BASE_LIMITS) {
      if (lim > current) return lim;
    }
    return null;
  }

  async function fetchBaseJobs(ctx, limit) {
    const query = buildQuery({
      includeTitle: false,
      limit,
      cities: ctx.cities,
      titleKeywords: ctx.titleKeywords,
    });
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
        return false;
      }

      state.baseJobs = data?.results || [];
      state.baseCitiesKey = ctx.citiesKey;
      state.baseLimit = limit;
      state.baseFetched = true;
      return true;
    } catch (e) {
      setStatus("Failed to load jobs", "error");
      return false;
    }
  }

  async function fetchJobs({ forceServer = false } = {}) {
    if (state.inFlight) {
      state.pendingSearch = true;
      state.pendingForce = state.pendingForce || forceServer;
      return;
    }
    const ctx = getSearchContext();

    if (state.baseCitiesKey !== ctx.citiesKey) {
      state.baseJobs = [];
      state.baseLimit = 0;
      state.baseFetched = false;
      state.baseCitiesKey = ctx.citiesKey;
    }

    const initialLimit = ctx.titleKeywords.length ? BASE_LIMITS[0] : DEFAULT_LIMIT;
    const cachedApplied = applyCachedFilter(ctx, { updateStatus: !forceServer });
    if (cachedApplied && !forceServer && state.baseLimit >= initialLimit) {
      return;
    }

    state.inFlight = true;
    setLoading(true);

    try {
      if (!state.baseFetched || state.baseLimit < initialLimit || forceServer) {
        setStatus("Loading jobs...", "info");
        const ok = await fetchBaseJobs(ctx, initialLimit);
        if (!ok) return;
      }

      applyCachedFilter(ctx, { updateStatus: true });

      if (forceServer && ctx.titleKeywords.length) {
        let nextLimit = nextBaseLimit(state.baseLimit);
        while (nextLimit && state.jobs.length < TARGET_RESULTS) {
          setStatus("Searching more jobs...", "info");
          const ok = await fetchBaseJobs(ctx, nextLimit);
          if (!ok) break;
          applyCachedFilter(ctx, { updateStatus: true });
          nextLimit = nextBaseLimit(state.baseLimit);
        }
      }
    } finally {
      state.inFlight = false;
      setLoading(false);
      if (state.pendingSearch) {
        const pendingForce = state.pendingForce;
        state.pendingSearch = false;
        state.pendingForce = false;
        void fetchJobs({ forceServer: pendingForce });
      }
    }
  }

  function setupTitleSelect() {
    const select = qs("#titleSelect");
    if (!select) return;
    select.addEventListener("change", () => {
      const value = select.value || "";
      if (!value) return;
      addTitlesToSelection(value);
      select.value = "";
      triggerAutoSearch();
    });

    qs("#titleClear")?.addEventListener("click", () => {
      clearSelectedTitles();
      triggerAutoSearch();
      select.focus();
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
      const values = Array.isArray(title) ? title : String(title).split(",");
      setSelectedTitles(values);
    }
    if (!title) {
      clearSelectedTitles();
    }

    if (city || title) fetchJobs({ forceServer: true });
  }

  function init() {
    qs("#searchForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      fetchJobs({ forceServer: true });
    });
    setupCitySelect();
    setupTitleSelect();
    renderSelectedCities();
    renderSelectedTitles();
    renderResults();
    loadFromQuery();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
