# jobfinder — CLI + API + Web UI

Find companies by **city** and pull **open roles** from public ATS boards (**Greenhouse**, **Lever**).

Includes:
- **CLI** (`jobfinder`) for discovery + scanning
- **Flask API** (`jobfinder-api`) with `POST /discover` and `POST /scan`
- **Web UI** (served at `/`) to browse companies and jobs

---

## Quick start

### 1) Setup

#### Windows (PowerShell)
```powershell
py -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -e .
```

#### macOS / Linux
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```


#### PowerShell
```powershell
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"
```

#### macOS/Linux
```bash
export SERPAPI_API_KEY="YOUR_REAL_KEY"
```

### 2) Run the server (API + Web UI)
```bash
jobfinder-api
```

Open the UI:
```text
http://localhost:8000
```

---

## Requirements

- Python **3.10+**
- (Optional) SerpAPI account & API key (for **discovery only**)

---

## Environment variables

- `SERPAPI_API_KEY` — required **only** for `/discover` or `jobfinder discover`
- `HOST`, `PORT` — optional Flask bind (defaults to `0.0.0.0:8000`)
- `.env` supported

Example `.env`:
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

- Served at `/` by `jobfinder-api`
- Flow: **Discover → select companies → Scan jobs → jobs table**

Run:
```powershell
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"
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
Response:
```json
{ "status": "ok", "version": "0.2.0" }
```

#### curl
```bash
curl -s http://localhost:8000/health
```

---

### `POST /discover`

Find companies by city/keywords using SerpAPI.  
Dedupes by unique `(provider, org)` and normalizes names from slugs.

Request:
```json
{
  "cities": ["Tel Aviv", "New York"],
  "keywords": ["software", "ai"],
  "sources": ["greenhouse", "lever"],
  "limit": 25
}
```

Response:
```json
{
  "count": 3,
  "companies": [
    { "name": "Acme", "provider": "greenhouse", "org": "acme", "city": null, "careers_url": null }
  ]
}
```

#### PowerShell
```powershell
$resp = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/discover" `
  -ContentType "application/json" `
  -Body '{"cities":["Tel Aviv"],"keywords":["software"],"sources":["greenhouse","lever"],"limit":10}'

$resp.companies | Select-Object -ExpandProperty name
```

#### curl
```bash
curl -s -X POST "http://localhost:8000/discover" \
  -H "Content-Type: application/json" \
  -d '{"cities":["Tel Aviv"],"keywords":["software"],"sources":["greenhouse","lever"],"limit":10}'
```

---

### `POST /scan`

Fetch + rank jobs for provided companies.

Request (JSON list):
```json
{
  "cities": ["Tel Aviv", "New York"],
  "keywords": ["python", "data"],
  "top": 50,
  "companies": [
    { "name": "Acme", "city": "New York", "provider": "greenhouse", "org": "acme" },
    { "name": "Contoso", "city": "Tel Aviv", "provider": "lever", "org": "contoso" }
  ]
}
```

Request (CSV string):
```json
{
  "cities": ["Tel Aviv"],
  "keywords": ["python"],
  "companies_csv": "name,city,provider,org,careers_url\nAcme,New York,greenhouse,acme,\n"
}
```

Response:
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
      "extra": { "description": "..." },
      "score": 73,
      "reasons": "title:data,city,fresh-5d"
    }
  ]
}
```

#### curl
```bash
curl -s -X POST "http://localhost:8000/scan" \
  -H "Content-Type: application/json" \
  -d '{"cities":["Tel Aviv"],"keywords":["python"],"top":20,"companies":[{"name":"Acme","city":"Tel Aviv","provider":"greenhouse","org":"acme"}]}'
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

Companies CSV header:
```text
name,city,provider,org,careers_url
```

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

- Query SerpAPI for:
  - `site:boards.greenhouse.io` and/or
  - `site:jobs.lever.co`
- Canonicalize URLs (strip query/fragment), extract first path segment as `org`
- De-duplicate by `(provider, org)`
- Normalize names from slug (`my-company` → `My Company`)

---

## Extend providers

1) Create `jobfinder/providers/<new>.py` with:
```python
async def jobs(self, company: Company):
    ...
```

2) Register in `jobfinder/providers/__init__.py`:
```python
PROVIDERS["new"] = NewProvider()
```

---

## Data formats

Companies CSV:
```text
name,city,provider,org,careers_url
```

Jobs CSV:
```text
id,title,company,url,location,remote,created_at,provider,extra,score,reasons
```

---

## Troubleshooting

- `SERPAPI_API_KEY missing` → set it before starting `jobfinder-api` or running `jobfinder discover`
- PowerShell `export` error → use `$env:VAR="value"`
- Empty `/scan` results → verify:
  - `provider` ∈ `{greenhouse, lever}`
  - `org` is the board slug

---

## License

MIT
