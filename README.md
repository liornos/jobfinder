# jobfinder - CLI + API + Web UI

![JobFinder logo](jobfinder/static/jobfinder-image.png)

Jobfinder helps you find open roles by location: discover companies by city/keywords, scan their ATS boards, and filter jobs by publish date or remote/hybrid/onsite status.

Includes:
- **CLI** (`jobfinder`) for scanning, refresh, and diagnostics
- **Flask API** (`jobfinder-api`) with `/discover`, `/refresh`, `/scan`, `/jobs`
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

- `SERPAPI_API_KEY` - required **only** for `/discover` (UI/API)
- `SERPAPI_NUM_RESULTS` - optional SerpAPI results per query (10-100, default 100)
- `SERPAPI_CITY_MODE` - optional: `or` (default) combines cities; `split` runs per city
- `SERPAPI_PROVIDER_MODE` - optional: `or` (default) combines providers into one query; `split` runs per provider
- `SERPAPI_NO_CACHE` - optional: set `true` to bypass SerpAPI cache (costs credits)
- `SERPAPI_CACHE_TTL_SECONDS` - optional local cache TTL for SerpAPI responses (default 86400; set 0 to disable)
- `SERPAPI_CACHE_DIR` - optional local cache directory (default `.serpapi_cache` in cwd)
- `HOST`, `PORT` - optional Flask bind (defaults to `0.0.0.0:8000`)
- `AUTO_REFRESH_ON_START` - optional: server-side startup refresh (default true)
- `ALLOW_REFRESH_ENDPOINT` - optional: enable `POST /refresh` and `POST /debug/refresh` (default false)
- `.env` supported

Local SerpAPI cache is enabled by default unless `SERPAPI_CACHE_TTL_SECONDS=0` or `SERPAPI_NO_CACHE=true`.

Example `.env`:
```dotenv
SERPAPI_API_KEY=YOUR_REAL_KEY
SERPAPI_NUM_RESULTS=100
SERPAPI_CITY_MODE=or
SERPAPI_PROVIDER_MODE=or
SERPAPI_NO_CACHE=false
SERPAPI_CACHE_TTL_SECONDS=86400
# SERPAPI_CACHE_DIR=.serpapi_cache
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
- Flow: **Discover -> select companies -> Refresh jobs -> jobs table**

Run:
```powershell
$env:SERPAPI_API_KEY = "YOUR_REAL_KEY"
jobfinder-api
# open http://localhost:8000
```

---

## E2E tests (Playwright)

Install:
```powershell
pip install -e .[dev,e2e]
playwright install chromium
```

Run:
```powershell
pytest -q tests/e2e
```

The UI test opens `/?e2e=1` to disable auto refresh on startup for deterministic runs.

---

## API

- Endpoints:
  - `POST /discover` (requires `SERPAPI_API_KEY`)
  - `POST /refresh` -> fetch from providers and upsert into the DB (disabled unless `ALLOW_REFRESH_ENDPOINT=1`)
  - `GET /jobs` -> query jobs from the DB with filters (provider/remote/min_score/max_age_days/cities/keywords/active/limit/offset)
  - `POST /scan` (legacy passthrough to providers; kept for compatibility)
  - `GET /healthz`
- Start locally: `jobfinder-api` (after installing + setting `SERPAPI_API_KEY` as shown above).
- Quick curls:
  - Health: `curl -s http://localhost:8000/healthz`
  - Discover: `curl -s -X POST http://localhost:8000/discover -H "Content-Type: application/json" -d '{"cities":["Tel Aviv"],"keywords":["software"],"sources":["greenhouse","lever"],"limit":10}'`
  - Refresh (requires `ALLOW_REFRESH_ENDPOINT=1`): `curl -s -X POST http://localhost:8000/refresh -H "Content-Type: application/json" -d '{"cities":["Tel Aviv"],"keywords":["python"],"companies":[{"name":"Acme","provider":"greenhouse","org":"acme"}]}'`
  - Jobs query: `curl -s "http://localhost:8000/jobs?cities=Tel%20Aviv&remote=any&min_score=0&limit=50"`

## Database-backed flow

- Default DB: SQLite at `jobfinder.db` (override with `JOBFINDER_DATABASE_URL` or `DATABASE_URL`).
- Install Postgres driver when needed: `pip install -e .[pg]` (uses `psycopg[binary]`).
- Recommended UI flow: Discover -> select companies -> **Refresh** (stores into DB) -> Filters call `/jobs` (DB-only, no provider HTTP calls).

## Scheduled refresh (Render Cron Job)

Keep the web service lightweight (UI + DB queries) and run refresh as a scheduled job:
```bash
jobfinder refresh
```
Optional flags: `--cities "Tel Aviv" --keywords "python" --companies-path static/companies.json`

---

## CLI

- `jobfinder --help` (and subcommands) for options.
- Scan example: `jobfinder scan --companies-json '[{"name":"Acme","provider":"greenhouse","org":"acme"}]' --cities "Tel Aviv" --keywords "python"`
- Refresh example: `jobfinder refresh --cities "Tel Aviv" --keywords "python" --companies-path static/companies.json`
- Diagnostics: `jobfinder debug-providers`

---

## Configuration (`config.yaml`)

Optional file in project root:

```yaml
defaults:
  cities: ["Tel Aviv", "New York"]
  keywords: ["python", "data"]

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
def fetch_jobs(org: str, *, limit: int | None = None, **kwargs) -> list[dict]:
    ...
```

2) Add the provider name to:
   - `jobfinder/pipeline.py` (`PROVIDERS` + `_PROVIDER_HOST`)
   - `jobfinder/providers/__init__.py`
   - `jobfinder/static/app.js` (UI provider list)

---

## Troubleshooting

- `SERPAPI_API_KEY missing` -> set it before starting `jobfinder-api` or calling `/discover`
- PowerShell `export` error -> use `$env:VAR="value"`
- Empty `/scan` results -> verify:
  - `provider` in `{greenhouse, lever}`
  - `org` is the board slug
- Render memory restarts (Starter 512MB) -> run Gunicorn with a single worker and limit concurrency:
  - Start Command: `gunicorn jobfinder.api:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
  - If `WEB_CONCURRENCY` is set, force it to `1`

---

## License

MIT
