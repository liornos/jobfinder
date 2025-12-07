# jobfinder — CLI + API + Web UI

Find companies by city and pull open roles from public ATS boards (Greenhouse, Lever). Includes:
- **CLI** (`jobfinder`) for discovery + scanning
- **Flask API** (`jobfinder-api`) with `/discover` and `/scan`
- **Web UI** (served at `/`) to browse companies and jobs

---
<img width="1245" height="925" alt="image" src="https://github.com/user-attachments/assets/52888b52-faf6-4b11-a154-2327e9b8ddf7" />

# 1) Setup 
# For Windows PowerShell

```powershell

py -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -e .

# For Linux\Mac

```bash
# macOS/Linux
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

# 2) If you want "Discover", set SerpAPI key (not needed for "Scan")
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"

# 3) Run the server (API + Web UI)
jobfinder-api         # http://localhost:8000

# 4) Browser UI: open http://localhost:8000
#    Or API: POST /discover, then POST /scan
```

---

## Requirements
- Python **3.10+**
- (Optional) SerpAPI account & API key (for discovery only)

---



---

## Environment variables

- `SERPAPI_API_KEY` — required **only** for `/discover` or `jobfinder discover`.
- `HOST`, `PORT` — (optional) Flask bind, defaults `0.0.0.0:8000`.
- `.env` supported. Example `.env`:
  ```dotenv
  SERPAPI_API_KEY=YOUR_REAL_KEY
  HOST=0.0.0.0
  PORT=8000
  ```

PowerShell quick checks:
```powershell
$env:SERPAPI_API_KEY
dir env: | ? Name -like "*SERPAPI*"
```

---

## Web UI

- Served at `/` by `jobfinder-api`.
- Flow: **Discover** → select companies → **Scan selected** → jobs table.

Run:
```powershell
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"  # only needed for Discover
jobfinder-api
# open http://localhost:8000
```

---

## API

### Start
```powershell
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"  # for /discover
jobfinder-api
```

### `GET /health`
```json
{ "status": "ok", "version": "0.2.0" }
```

### `POST /discover`
Unique `(provider, org)`; names normalized from slugs.

**Request**
```json
{
  "cities": ["Tel Aviv", "New York"],
  "keywords": ["software", "ai"],
  "sources": ["greenhouse", "lever"],
  "limit": 25
}
```

**Response**
```json
{
  "count": 3,
  "companies": [
    {"name":"Acme", "provider":"greenhouse", "org":"acme", "city":null, "careers_url":null}
  ]
}
```

**PowerShell**
```powershell
$resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/discover" `
  -ContentType "application/json" `
  -Body '{"cities":["Tel Aviv"],"keywords":["software"],"sources":["greenhouse","lever"],"limit":10}'
$resp.companies | Select-Object -ExpandProperty name
```

### `POST /scan`
Fetch + rank jobs for provided companies.

**Request (JSON list)**
```json
{
  "cities": ["Tel Aviv","New York"],
  "keywords": ["python","data"],
  "top": 50,
  "companies": [
    {"name":"Acme","city":"New York","provider":"greenhouse","org":"acme"},
    {"name":"Contoso","city":"Tel Aviv","provider":"lever","org":"contoso"}
  ]
}
```

**Request (CSV string)**
```json
{
  "cities": ["Tel Aviv"],
  "keywords": ["python"],
  "companies_csv": "name,city,provider,org,careers_url\nAcme,New York,greenhouse,acme,\n"
}
```

**Response**
```json
{
  "count": 42,
  "results": [
    {
      "id": "greenhouse:acme:12345",
      "title": "Data Engineer",
      "company": "Acme",
      "url": "https://...",
      "location": "New York, NY",
      "remote": false,
      "created_at": "2025-10-10T12:34:56+00:00",
      "provider": "greenhouse",
      "extra": {"description": "..."},
      "score": 73,
      "reasons": "title:data,city,fresh-5d"
    }
  ]
}
```

---

## CLI

### Help
```bash
jobfinder --help
jobfinder discover --help
jobfinder scan --help
```

### Discover
```bash
jobfinder discover --cities "Tel Aviv,New York" --keywords "software,ai" \
  --sources greenhouse,lever --limit 50 --out companies.csv
```

### Scan
```bash
jobfinder scan --companies-file data/companies.example.csv \
  --cities "Tel Aviv,New York" --keywords "python,data" \
  --out jobs.csv --save_sqlite jobs.db
```

**Companies CSV header:** `name,city,provider,org,careers_url`

---

## Configuration (`config.yaml`)

Optional file in project root:
```yaml
defaults:
  cities: ["Tel Aviv", "New York"]
  keywords: ["python", "data"]
output:
  csv: jobs.csv
  sqlite: jobs.db
discovery:
  sources: ["greenhouse", "lever"]
  limit: 50
```

---

## Discovery pipeline (dedupe + normalize)

- Query SerpAPI for `site:boards.greenhouse.io` / `site:jobs.lever.co` with city/keywords.
- Canonicalize URLs (strip query/fragment), extract first path segment as org.
- De-duplicate by `(provider, org)`; normalize names from slug (`my-company` → `My Company`).

---

## Extend providers

1. Create `jobfinder/providers/<new>.py` with:
   ```python
   async def jobs(self, company: Company) -> AsyncIterator[Job]: ...
   ```
2. Register in `jobfinder/providers/__init__.py`:
   ```python
   PROVIDERS["new"] = NewProvider()
   ```

---

## Data formats

**Companies CSV**: `name,city,provider,org,careers_url`  
**Jobs CSV**: `id,title,company,url,location,remote,created_at,provider,extra,score,reasons`

---

## Troubleshooting

- **`SERPAPI_API_KEY missing`** → set it **before** starting `jobfinder-api` or running `jobfinder discover`.  
- **PowerShell `export` error** → use `$env:VAR="value"`.  
- **Empty /scan results** → verify `provider` ∈ `{greenhouse, lever}` and `org` is the board slug.  

---

## License
MIT

---


## Changelog
- **0.2.0** — Web UI added; API mounts UI at `/`.
- **0.1.2** — Canonicalized discovery, de-dup, normalized names.
- **0.1.0** — Initial CLI + API.
