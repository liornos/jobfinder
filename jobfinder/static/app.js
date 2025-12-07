const qs = (sel) => document.querySelector(sel);
const qsa = (sel) => Array.from(document.querySelectorAll(sel));

let companies = [];
let jobs = [];

function renderCompanies() {
  const body = qs("#companiesBody");
  body.innerHTML = "";
  companies.forEach((c, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="p-2"><input type="checkbox" class="rowSel" data-i="${i}"></td>
      <td class="p-2">${c.name || ""}</td>
      <td class="p-2">${c.provider || ""}</td>
      <td class="p-2">${c.org || ""}</td>
    `;
    body.appendChild(tr);
  });
}

function renderJobs() {
  const body = qs("#jobsBody");
  body.innerHTML = "";
  qs("#jobsCount").textContent = jobs.length;
  jobs.forEach((j) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="p-2">${j.score ?? ""}</td>
      <td class="p-2">${j.title || ""}</td>
      <td class="p-2">${j.company || ""}</td>
      <td class="p-2">${j.location || ""}</td>
      <td class="p-2">${j.provider || ""}</td>
      <td class="p-2"><a class="text-blue-600 underline" target="_blank" rel="noopener" href="${j.url}">open</a></td>
    `;
    body.appendChild(tr);
  });
}

async function discover() {
  const msg = qs("#discoverMsg");
  msg.textContent = "Discovering...";
  const cities = qs("#cities").value.split(",").map(s => s.trim()).filter(Boolean);
  const keywords = qs("#keywords").value.split(",").map(s => s.trim()).filter(Boolean);
  const sources = Array.from(qs("#sources").selectedOptions).map(o => o.value);
  const limit = parseInt(qs("#limit").value || "25", 10);
  try {
    const r = await fetch("/discover", {
      method: "POST",
      headers: {"content-type":"application/json"},
      body: JSON.stringify({cities, keywords, sources, limit})
    });
    const data = await r.json();
    if (!r.ok) {
      msg.textContent = data.error || "Discover failed";
      return;
    }
    companies = data.companies || [];
    renderCompanies();
    msg.textContent = `Found ${companies.length} companies`;
  } catch (e) {
    msg.textContent = "Network error";
  }
}

async function scanSelected() {
  const selected = qsa(".rowSel:checked").map(cb => companies[parseInt(cb.dataset.i, 10)]);
  if (!selected.length) return;
  const cities = qs("#cities").value.split(",").map(s => s.trim()).filter(Boolean);
  const keywords = qs("#keywords").value.split(",").map(s => s.trim()).filter(Boolean);
  const body = { cities, keywords, companies: selected };
  const r = await fetch("/scan", { method:"POST", headers:{"content-type":"application/json"}, body: JSON.stringify(body)});
  const data = await r.json();
  if (!r.ok) { alert(data.error || "Scan failed"); return; }
  jobs = data.results || [];
  renderJobs();
}

qs("#btnDiscover").addEventListener("click", discover);
qs("#btnScanSelected").addEventListener("click", scanSelected);
qs("#btnClear").addEventListener("click", () => { companies=[]; jobs=[]; renderCompanies(); renderJobs(); });
qs("#selectAll").addEventListener("change", (e) => { qsa(".rowSel").forEach(cb => cb.checked = e.target.checked); });

renderCompanies(); renderJobs();
