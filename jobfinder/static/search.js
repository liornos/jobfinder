(() => {
  "use strict";

  const qs = (sel) => document.querySelector(sel);

  const state = {
    jobs: [],
    baseJobs: [],
    baseQueryKey: "",
    baseLimit: 0,
    baseFetched: false,
    inFlight: false,
    pendingSearch: false,
    pendingForce: false,
    startupRetryCount: 0,
    startupRetryTimer: null,
    startupRefreshPending: false,
  };

  const cityState = {
    selected: [],
    allIsrael: false,
  };

  const titleState = {
    selected: [],
  };

  const CITY_ALL_VALUE = "__all__";
  const CITY_ALL_LABEL = "Israel - All";
  const DEFAULT_LIMIT = 200;
  const BASE_LIMITS = [400, 800, 1200];
  const TARGET_RESULTS = 40;
  const STARTUP_RETRY_DELAYS_MS = [1000, 1500, 2500, 4000, 6000, 10000, 15000];

  function debounce(fn, delayMs) {
    let timer = null;
    return (...args) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delayMs);
    };
  }

  function escapeHtml(value) {
    return (value ?? "").toString().replace(/[&<>"']/g, (m) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[m]));
  }

  function normalizeText(value) {
    return (value ?? "").toString().toLowerCase().replace(/\s+/g, " ").trim();
  }

  function textFromHtml(value) {
    const div = document.createElement("div");
    div.innerHTML = (value ?? "").toString();
    return div.textContent || div.innerText || "";
  }

  function trimText(value, maxLen = 120) {
    const text = (value ?? "").toString().trim();
    if (!text) return "";
    if (text.length <= maxLen) return text;
    return `${text.slice(0, maxLen - 1).trimEnd()}...`;
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 10);
  }

  function formatProvider(value) {
    const provider = (value ?? "").toString().trim().toLowerCase();
    const labels = {
      ashby: "Ashby",
      breezy: "Breezy",
      comeet: "Comeet",
      greenhouse: "Greenhouse",
      icims: "iCIMS",
      jobvite: "Jobvite",
      lever: "Lever",
      recruitee: "Recruitee",
      smartrecruiters: "SmartRecruiters",
      workable: "Workable",
      workday: "Workday",
    };
    return labels[provider] || provider;
  }

  function remoteLabel(value) {
    const remote = (value ?? "").toString().trim().toLowerCase();
    if (remote === "true") return "Remote";
    if (remote === "false") return "On-site";
    if (remote === "hybrid") return "Hybrid";
    return "Any";
  }

  function setStatus(text, kind = "info") {
    const el = qs("#statusMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "text-sm font-semibold mt-4";
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
    if (text) text.textContent = isLoading ? "Searching..." : "Search Jobs";
    if (spinner) spinner.classList.toggle("hidden", !isLoading);
  }

  function setResultsSummary(text) {
    const el = qs("#resultsSummary");
    if (!el) return;
    el.textContent = text || "Live query";
  }

  function parseKeywordValues(value) {
    return (value ?? "")
      .toString()
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function getKeywordTerms() {
    return parseKeywordValues(qs("#keywordInput")?.value || "");
  }

  function createChip(label, onRemove) {
    const chip = document.createElement("span");
    chip.className = "inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm";

    const text = document.createElement("span");
    text.textContent = label;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-200 text-slate-600 hover:bg-slate-300 hover:text-slate-700";
    btn.textContent = "x";
    btn.setAttribute("aria-label", `Remove ${label}`);
    btn.addEventListener("click", onRemove);

    chip.appendChild(text);
    chip.appendChild(btn);
    return chip;
  }

  function renderEmptyChipState(container, text) {
    if (!container) return;
    const empty = document.createElement("span");
    empty.className = "chip-empty";
    empty.textContent = text;
    container.appendChild(empty);
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

  function renderSelectedCities() {
    const container = qs("#citySelected");
    if (!container) return;
    container.innerHTML = "";

    if (cityState.allIsrael) {
      container.appendChild(createChip(CITY_ALL_LABEL, () => {
        clearSelectedCities();
        triggerSearch({ forceServer: true });
      }));
      return;
    }

    if (!cityState.selected.length) {
      renderEmptyChipState(container, "No cities selected.");
      return;
    }

    cityState.selected.forEach((city) => {
      container.appendChild(createChip(city, () => removeSelectedCity(city)));
    });
  }

  function addCitiesToSelection(values) {
    const parsed = parseCityValues(Array.isArray(values) ? values : [values]);
    if (parsed.all) {
      cityState.selected = [];
      cityState.allIsrael = true;
      renderSelectedCities();
      renderActiveFilters();
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
    renderActiveFilters();
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
    renderActiveFilters();
  }

  function clearSelectedCities() {
    cityState.selected = [];
    cityState.allIsrael = false;
    renderSelectedCities();
    renderActiveFilters();
  }

  function removeSelectedCity(city) {
    const key = city.toLowerCase();
    cityState.selected = cityState.selected.filter((item) => item.toLowerCase() !== key);
    renderSelectedCities();
    renderActiveFilters();
    triggerSearch({ forceServer: true });
  }

  function getSelectedCities() {
    return cityState.allIsrael ? [] : [...cityState.selected];
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

  function renderSelectedTitles() {
    const container = qs("#titleSelected");
    if (!container) return;
    container.innerHTML = "";

    if (!titleState.selected.length) {
      renderEmptyChipState(container, "No job titles selected.");
      return;
    }

    titleState.selected.forEach((title) => {
      container.appendChild(createChip(title, () => removeSelectedTitle(title)));
    });
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
    renderActiveFilters();
  }

  function setSelectedTitles(values) {
    titleState.selected = parseTitleValues(values);
    renderSelectedTitles();
    renderActiveFilters();
  }

  function clearSelectedTitles() {
    titleState.selected = [];
    renderSelectedTitles();
    renderActiveFilters();
  }

  function removeSelectedTitle(title) {
    const key = title.toLowerCase();
    titleState.selected = titleState.selected.filter((item) => item.toLowerCase() !== key);
    renderSelectedTitles();
    renderActiveFilters();
    triggerSearch({ forceServer: true });
  }

  function getSelectedTitles() {
    return [...titleState.selected];
  }

  function getSearchContext() {
    const cities = getSelectedCities();
    const titleKeywords = getSelectedTitles();
    const keywords = getKeywordTerms();
    const provider = (qs("#providerSelect")?.value || "").trim();
    const remote = (qs("#remoteSelect")?.value || "any").trim();
    const onlyNew = !!qs("#onlyNewToggle")?.checked;

    const serverKey = JSON.stringify({
      cities: [...cities].map(normalizeText).sort(),
      titleKeywords: [...titleKeywords].map(normalizeText).sort(),
      provider,
      remote,
      onlyNew,
    });

    return {
      cities,
      titleKeywords,
      keywords,
      provider,
      remote,
      onlyNew,
      serverKey,
    };
  }

  function buildResultsSummary(ctx) {
    const parts = [];
    if (ctx.cities.length) parts.push(ctx.cities.join(", "));
    if (ctx.titleKeywords.length) parts.push(`Titles: ${ctx.titleKeywords.join(", ")}`);
    if (ctx.keywords.length) parts.push(`Keywords: ${ctx.keywords.join(", ")}`);
    if (ctx.remote !== "any") parts.push(remoteLabel(ctx.remote));
    if (ctx.provider) parts.push(`Provider: ${formatProvider(ctx.provider)}`);
    if (ctx.onlyNew) parts.push("Only new jobs");
    return parts.join(" • ") || "Live query";
  }

  function renderActiveFilters() {
    const container = qs("#activeFilterChips");
    if (!container) return;
    container.innerHTML = "";

    const ctx = getSearchContext();
    const chips = [];

    if (ctx.keywords.length) {
      chips.push({
        label: ctx.keywords.join(" + "),
        onRemove: () => {
          const input = qs("#keywordInput");
          if (input) input.value = "";
          renderActiveFilters();
          triggerSearch({ forceServer: false });
        },
      });
    }

    if (ctx.provider) {
      chips.push({
        label: formatProvider(ctx.provider),
        onRemove: () => {
          const select = qs("#providerSelect");
          if (select) select.value = "";
          renderActiveFilters();
          triggerSearch({ forceServer: true });
        },
      });
    }

    if (ctx.remote !== "any") {
      chips.push({
        label: remoteLabel(ctx.remote),
        onRemove: () => {
          const select = qs("#remoteSelect");
          if (select) select.value = "any";
          renderActiveFilters();
          triggerSearch({ forceServer: true });
        },
      });
    }

    if (ctx.onlyNew) {
      chips.push({
        label: "Only new jobs",
        onRemove: () => {
          const toggle = qs("#onlyNewToggle");
          if (toggle) toggle.checked = false;
          renderActiveFilters();
          triggerSearch({ forceServer: true });
        },
      });
    }

    if (!chips.length) {
      renderEmptyChipState(container, "No quick filters selected.");
      return;
    }

    chips.forEach((chip) => {
      container.appendChild(createChip(chip.label, chip.onRemove));
    });
  }

  function buildQuery({
    cities,
    titleKeywords,
    provider,
    remote,
    onlyNew,
    limit = DEFAULT_LIMIT,
  } = {}) {
    const params = new URLSearchParams();
    const cityValues = Array.isArray(cities) ? cities : getSelectedCities();
    const titleValues = Array.isArray(titleKeywords) ? titleKeywords : getSelectedTitles();
    const providerValue = provider ?? (qs("#providerSelect")?.value || "");
    const remoteValue = remote ?? (qs("#remoteSelect")?.value || "any");
    const onlyNewValue = typeof onlyNew === "boolean" ? onlyNew : !!qs("#onlyNewToggle")?.checked;

    if (cityValues.length) params.set("cities", cityValues.join(","));
    if (titleValues.length) params.set("title_keywords", titleValues.join(","));
    if (providerValue) params.set("provider", providerValue);
    if (remoteValue && remoteValue !== "any") params.set("remote", remoteValue);
    if (onlyNewValue) params.set("only_new", "1");
    params.set("limit", String(limit));

    return {
      params,
      cities: cityValues,
      titleKeywords: titleValues,
      provider: providerValue,
      remote: remoteValue,
      onlyNew: onlyNewValue,
    };
  }

  function filterByKeywords(rows, keywords) {
    const needles = (keywords || []).map(normalizeText).filter(Boolean);
    if (!needles.length) return rows || [];

    return (rows || []).filter((row) => {
      const haystack = normalizeText([
        row?.title,
        row?.company,
        row?.company_city,
        row?.location,
        row?.provider,
        textFromHtml(row?.extra?.description || ""),
      ].join(" "));
      return needles.every((needle) => haystack.includes(needle));
    });
  }

  function nextBaseLimit(current) {
    for (const limit of BASE_LIMITS) {
      if (limit > current) return limit;
    }
    return null;
  }

  function getWorkMode(job) {
    const mode = normalizeText(job?.extra?.work_mode || "");
    if (mode === "remote") return "Remote";
    if (mode === "hybrid") return "Hybrid";
    if (mode === "onsite") return "On-site";
    if (job?.remote === true) return "Remote";
    if (job?.remote === false) return "On-site";
    return "";
  }

  function isNewJob(job) {
    const iso = job?.created_at;
    if (!iso) return false;
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return false;
    const days = (Date.now() - date.getTime()) / (1000 * 60 * 60 * 24);
    return days <= 7;
  }

  function renderResults() {
    const body = qs("#resultsBody");
    const countEl = qs("#resultsCount");
    if (!body) return;

    body.innerHTML = "";
    const ctx = getSearchContext();

    if (!state.jobs.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td colspan="6" class="p-10 text-center">
          <div class="mx-auto max-w-xl">
            <div class="text-xl font-extrabold text-slate-800">No matching jobs found</div>
            <div class="mt-2 text-sm text-slate-500">Try removing one filter, broadening the city selection, or switching work mode back to Any.</div>
          </div>
        </td>
      `;
      body.appendChild(tr);
      if (countEl) countEl.textContent = "0";
      setResultsSummary(buildResultsSummary(ctx));
      return;
    }

    for (const job of state.jobs) {
      const url = (job?.url || "").toString();
      const provider = formatProvider(job?.provider || "");
      const location = (job?.location || job?.company_city || "Unknown").toString();
      const desc = trimText(textFromHtml(job?.extra?.description || ""), 120)
        || trimText(job?.reasons || "", 120)
        || "Open the post for the full description.";
      const workMode = getWorkMode(job);
      const badges = [];

      if (workMode) badges.push(`<span class="mini-badge">${escapeHtml(workMode)}</span>`);
      if (isNewJob(job)) badges.push('<span class="mini-badge new">New</span>');
      if (ctx.keywords.length && job?.score) {
        badges.push(`<span class="mini-badge">Score ${escapeHtml(job.score)}</span>`);
      }

      const tr = document.createElement("tr");
      if (url) {
        tr.addEventListener("click", () => window.open(url, "_blank", "noopener"));
      }

      tr.innerHTML = `
        <td>
          <div class="job-title">${escapeHtml(job?.title || "")}</div>
          <div class="job-subtitle">${escapeHtml(desc)}</div>
          <div class="mini-badges">${badges.join("")}</div>
        </td>
        <td>
          <div class="font-semibold text-slate-800">${escapeHtml(job?.company || "")}</div>
          <div class="job-subtitle">${escapeHtml(job?.company_city || "")}</div>
        </td>
        <td>${escapeHtml(location)}</td>
        <td>${escapeHtml(provider)}</td>
        <td>${escapeHtml(fmtDate(job?.created_at))}</td>
        <td>${url
          ? `<a class="link-pill" target="_blank" rel="noopener" href="${escapeHtml(url)}" onclick="event.stopPropagation()">Open</a>`
          : ""}</td>
      `;
      body.appendChild(tr);
    }

    if (countEl) countEl.textContent = String(state.jobs.length);
    setResultsSummary(buildResultsSummary(ctx));
  }

  function clearStartupRetry() {
    if (state.startupRetryTimer) clearTimeout(state.startupRetryTimer);
    state.startupRetryTimer = null;
    state.startupRetryCount = 0;
  }

  function scheduleStartupRetry() {
    if (state.startupRetryTimer) return;
    if (state.startupRetryCount >= STARTUP_RETRY_DELAYS_MS.length) return;
    const delay = STARTUP_RETRY_DELAYS_MS[state.startupRetryCount];
    state.startupRetryCount += 1;
    state.startupRetryTimer = setTimeout(() => {
      state.startupRetryTimer = null;
      void fetchJobs({ forceServer: true });
    }, delay);
  }

  async function fetchBaseJobs(ctx, limit) {
    const query = buildQuery({
      cities: ctx.cities,
      titleKeywords: ctx.titleKeywords,
      provider: ctx.provider,
      remote: ctx.remote,
      onlyNew: ctx.onlyNew,
      limit,
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
      state.baseQueryKey = ctx.serverKey;
      state.baseLimit = limit;
      state.baseFetched = true;
      const startupRefresh = data?.startup_refresh || {};
      state.startupRefreshPending = startupRefresh?.pending === true;

      if (state.baseJobs.length || !state.startupRefreshPending) {
        clearStartupRetry();
      } else {
        setStatus("Startup refresh is still running. Retrying shortly...", "info");
        scheduleStartupRetry();
      }

      return true;
    } catch {
      state.startupRefreshPending = false;
      clearStartupRetry();
      setStatus("Failed to load jobs", "error");
      return false;
    }
  }

  function applyCachedFilter(ctx, { updateStatus = true } = {}) {
    if (!state.baseFetched || state.baseQueryKey !== ctx.serverKey) return false;

    state.jobs = filterByKeywords(state.baseJobs, ctx.keywords);
    renderActiveFilters();
    renderResults();

    if (!updateStatus) return true;

    if (state.jobs.length) {
      const msg = ctx.keywords.length
        ? `Filtered ${state.jobs.length} jobs`
        : `Loaded ${state.jobs.length} jobs`;
      setStatus(msg, "ok");
    } else if (state.startupRefreshPending) {
      setStatus("Startup refresh is still running. Retrying shortly...", "info");
    } else {
      setStatus("No jobs found", "info");
    }

    return true;
  }

  async function fetchJobs({ forceServer = false } = {}) {
    if (state.inFlight) {
      state.pendingSearch = true;
      state.pendingForce = state.pendingForce || forceServer;
      return;
    }

    const ctx = getSearchContext();

    if (state.baseQueryKey !== ctx.serverKey) {
      state.baseJobs = [];
      state.baseLimit = 0;
      state.baseFetched = false;
      state.baseQueryKey = ctx.serverKey;
    }

    const initialLimit = ctx.keywords.length ? BASE_LIMITS[0] : DEFAULT_LIMIT;
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

      if (forceServer && ctx.keywords.length) {
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

  function triggerSearch({ forceServer = false } = {}) {
    void fetchJobs({ forceServer });
  }

  function clearAllFilters() {
    clearSelectedCities();
    clearSelectedTitles();
    const keywordInput = qs("#keywordInput");
    const providerSelect = qs("#providerSelect");
    const remoteSelect = qs("#remoteSelect");
    const onlyNewToggle = qs("#onlyNewToggle");

    if (keywordInput) keywordInput.value = "";
    if (providerSelect) providerSelect.value = "";
    if (remoteSelect) remoteSelect.value = "any";
    if (onlyNewToggle) onlyNewToggle.checked = false;

    renderActiveFilters();
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
        renderActiveFilters();
      } else {
        addCitiesToSelection(value);
      }
      select.value = "";
      triggerSearch({ forceServer: true });
    });

    qs("#cityClear")?.addEventListener("click", () => {
      clearSelectedCities();
      select.focus();
      triggerSearch({ forceServer: true });
    });
  }

  function setupTitleSelect() {
    const select = qs("#titleSelect");
    if (!select) return;

    select.addEventListener("change", () => {
      const value = select.value || "";
      if (!value) return;
      addTitlesToSelection(value);
      select.value = "";
      triggerSearch({ forceServer: true });
    });

    qs("#titleClear")?.addEventListener("click", () => {
      clearSelectedTitles();
      select.focus();
      triggerSearch({ forceServer: true });
    });
  }

  function setupQuickFilters() {
    const debouncedKeywordSearch = debounce(() => {
      triggerSearch({ forceServer: false });
    }, 250);

    qs("#keywordInput")?.addEventListener("input", () => {
      renderActiveFilters();
      debouncedKeywordSearch();
    });

    qs("#providerSelect")?.addEventListener("change", () => {
      renderActiveFilters();
      triggerSearch({ forceServer: true });
    });

    qs("#remoteSelect")?.addEventListener("change", () => {
      renderActiveFilters();
      triggerSearch({ forceServer: true });
    });

    qs("#onlyNewToggle")?.addEventListener("change", () => {
      renderActiveFilters();
      triggerSearch({ forceServer: true });
    });

    qs("#clearAllFilters")?.addEventListener("click", () => {
      clearAllFilters();
      triggerSearch({ forceServer: true });
    });
  }

  function loadFromQuery() {
    const params = new URLSearchParams(window.location.search);
    let hasFilters = false;

    const cityList = params.getAll("cities");
    const city = cityList.length ? cityList : params.get("city") || params.get("cities");
    if (city) {
      const values = Array.isArray(city) ? city : String(city).split(",");
      setSelectedCities(values);
      hasFilters = true;
    }

    const title = params.get("title") || params.get("title_keywords");
    if (title) {
      const values = Array.isArray(title) ? title : String(title).split(",");
      setSelectedTitles(values);
      hasFilters = true;
    }

    const keywords = params.get("keywords");
    if (keywords) {
      const input = qs("#keywordInput");
      if (input) input.value = keywords;
      hasFilters = true;
    }

    const provider = params.get("provider");
    if (provider) {
      const select = qs("#providerSelect");
      if (select) select.value = provider;
      hasFilters = true;
    }

    const remote = params.get("remote");
    if (remote) {
      const select = qs("#remoteSelect");
      if (select) select.value = remote;
      hasFilters = true;
    }

    const onlyNew = params.get("only_new");
    if (onlyNew && !["0", "false", "no"].includes(normalizeText(onlyNew))) {
      const toggle = qs("#onlyNewToggle");
      if (toggle) toggle.checked = true;
      hasFilters = true;
    }

    renderActiveFilters();
    return hasFilters;
  }

  function init() {
    qs("#searchForm")?.addEventListener("submit", (e) => {
      e.preventDefault();
      triggerSearch({ forceServer: true });
    });

    setupCitySelect();
    setupTitleSelect();
    setupQuickFilters();
    renderSelectedCities();
    renderSelectedTitles();
    renderActiveFilters();
    renderResults();

    const loadedFromQuery = loadFromQuery();
    if (loadedFromQuery) {
      triggerSearch({ forceServer: true });
    } else {
      triggerSearch({ forceServer: true });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
