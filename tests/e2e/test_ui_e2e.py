from __future__ import annotations

import threading
from typing import Iterator

import pytest
from werkzeug.serving import make_server

from jobfinder.api import create_app

try:
    from playwright.sync_api import expect, sync_playwright
except Exception:  # pragma: no cover - optional dependency
    pytest.skip("playwright not installed", allow_module_level=True)


@pytest.fixture
def live_server(tmp_path, monkeypatch) -> Iterator[str]:
    db_path = tmp_path / "jobs.db"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    app = create_app()
    app.config.update(TESTING=True)

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    addr = server.server_address
    host = addr[0]
    port = addr[1]
    if isinstance(host, bytes):
        host = host.decode()
    host = str(host)
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_discover_refresh_flow(live_server, serpapi_env, serpapi_stub, provider_stub):
    serpapi_stub(
        {
            "boards.greenhouse.io": {
                "organic_results": [{"link": "https://boards.greenhouse.io/acme"}]
            },
            "jobs.lever.co": {
                "organic_results": [{"link": "https://jobs.lever.co/contoso"}]
            },
        }
    )
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Backend Engineer",
                        "location": "Tel Aviv",
                        "url": "https://example.com/1",
                        "created_at": "2025-01-01T00:00:00Z",
                        "remote": False,
                    }
                ]
            },
            "lever": {
                "contoso": [
                    {
                        "id": "2",
                        "title": "Data Scientist",
                        "location": "Tel Aviv",
                        "url": "https://example.com/2",
                        "created_at": "2025-01-02T00:00:00Z",
                        "remote": True,
                    }
                ]
            },
        }
    )

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server}/?e2e=1", wait_until="domcontentloaded")

        page.locator("#btnDiscover").click()
        expect(page.locator("#companiesPanel")).to_be_visible()
        expect(page.locator("#companiesBody")).to_contain_text("acme")
        expect(page.locator("#companiesBody")).to_contain_text("contoso")

        page.locator("#selectAll").check()
        expect(page.locator("#btnScanSelected")).to_be_enabled()
        page.locator("#btnScanSelected").click()

        expect(page.locator("#jobsCount")).to_have_text("2")
        expect(page.locator("#jobsBody")).to_contain_text("Backend Engineer")
        expect(page.locator("#jobsBody")).to_contain_text("Data Scientist")

        browser.close()
