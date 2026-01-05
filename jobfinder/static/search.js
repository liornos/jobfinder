(() => {
  "use strict";

  const qs = (sel) => document.querySelector(sel);

  const state = {
    jobs: [],
    inFlight: false,
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

  function parseCities(value) {
    return (value ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function parseTitleKeywords(value) {
    const raw = (value ?? "").toString().trim();
    if (!raw) return [];
    const parts = raw.includes(",") ? raw.split(",") : raw.split(/\s+/);
    return parts.map((s) => s.trim()).filter(Boolean);
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const cities = parseCities(qs("#cityInput")?.value || "");
    const titleKeywords = parseTitleKeywords(qs("#titleInput")?.value || "");

    if (cities.length) params.set("cities", cities.join(","));
    if (titleKeywords.length) params.set("title_keywords", titleKeywords.join(","));
    params.set("limit", "200");

    return params;
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
    state.inFlight = true;
    setLoading(true);
    setStatus("Loading jobs...", "info");

    const params = buildQuery();
    const url = `/jobs?${params.toString()}`;

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

      state.jobs = data?.results || [];
      renderResults();
      setStatus(
        state.jobs.length ? `Loaded ${state.jobs.length} jobs` : "No jobs found",
        state.jobs.length ? "ok" : "info"
      );
    } catch (e) {
      setStatus("Failed to load jobs", "error");
    } finally {
      state.inFlight = false;
      setLoading(false);
    }
  }

  function loadFromQuery() {
    const params = new URLSearchParams(window.location.search);
    const city = params.get("city") || params.get("cities");
    const title = params.get("title") || params.get("title_keywords");

    if (city) {
      const input = qs("#cityInput");
      if (input) input.value = city;
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
    renderResults();
    loadFromQuery();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
