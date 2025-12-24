# jobfinder - CLI + API + Web UI

Jobfinder helps you find open roles by location: discover companies by city/keywords, scan their ATS boards, and filter jobs by publish date or remote/hybrid/onsite status.

Includes:
- **CLI** (`jobfinder`) for discovery + scanning
- **Flask API** (`jobfinder-api`) with `POST /discover` and `POST /scan`
- **Web UI** (served at `/`) to browse companies and jobs

---

## Quick start

### Windows (PowerShell)
```powershell
py -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -e .
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"   # needed for /discover (SerpAPI)
jobfinder-api                            # serves UI+API at http://localhost:8000
```

### macOS / Linux
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
export SERPAPI_API_KEY="YOUR_REAL_KEY"   # needed for /discover (SerpAPI)
jobfinder-api                            # serves UI+API at http://localhost:8000
```

Without a SerpAPI key, the UI still works using the bundled seed `static/companies.json` (Discover falls back to that file).

---

## Requirements

- Python **3.10+**
- (Optional) SerpAPI account & API key (for **discovery only**)

---

## Environment variables

- `SERPAPI_API_KEY` - required **only** for `/discover` or `jobfinder discover`
- `HOST`, `PORT` - optional Flask bind (defaults to `0.0.0.0:8000`)
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
- Flow: **Discover -> select companies -> Scan jobs -> jobs table**

Run:
```powershell
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"
jobfinder-api
# open http://localhost:8000
```

---

## API

- Endpoints: `GET /health`, `POST /discover` (requires `SERPAPI_API_KEY`), `POST /scan`.
- Start locally: `jobfinder-api` (after installing + setting `SERPAPI_API_KEY` as shown above).
- Quick curls:
  - Health: `curl -s http://localhost:8000/health`
  - Discover: `curl -s -X POST http://localhost:8000/discover -H "Content-Type: application/json" -d '{"cities":["Tel Aviv"],"keywords":["software"],"sources":["greenhouse","lever"],"limit":10}'`
  - Scan: `curl -s -X POST http://localhost:8000/scan -H "Content-Type: application/json" -d '{"keywords":["python"],"companies":[{"name":"Acme","provider":"greenhouse","org":"acme"}]}'`

---

## CLI

- `jobfinder --help` (and subcommands) for options.
- Discover example: `jobfinder discover --cities "Tel Aviv,New York" --keywords "software,ai" --sources greenhouse,lever --limit 50 --out companies.csv`
- Scan example: `jobfinder scan --companies-file data/companies.example.csv --keywords "python,data" --cities "Tel Aviv,New York" --out jobs.csv`

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
- Normalize names from slug (`my-company` -> `My Company`)

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

- `SERPAPI_API_KEY missing` -> set it before starting `jobfinder-api` or running `jobfinder discover`
- PowerShell `export` error -> use `$env:VAR="value"`
- Empty `/scan` results -> verify:
  - `provider` in `{greenhouse, lever}`
  - `org` is the board slug

---

## License

MIT
