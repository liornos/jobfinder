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


DISCOVER_STUB = {
    "boards.greenhouse.io": {
        "organic_results": [{"link": "https://boards.greenhouse.io/acme"}],
    },
    "jobs.lever.co": {
        "organic_results": [{"link": "https://jobs.lever.co/contoso"}],
    },
}

PROVIDER_STUB = {
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
                "location": "Haifa",
                "url": "https://example.com/2",
                "created_at": "2025-01-02T00:00:00Z",
                "remote": True,
            }
        ]
    },
}


@pytest.fixture
def live_server(tmp_path, monkeypatch) -> Iterator[str]:
    db_path = tmp_path / "jobs.db"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("AUTO_REFRESH_ON_START", "0")
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


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(5000)
    try:
        yield page
    finally:
        context.close()


def test_refresh_jobs_shows_rows(
    live_server, page, serpapi_env, serpapi_stub, provider_stub
):
    serpapi_stub(DISCOVER_STUB)
    provider_stub(PROVIDER_STUB)

    page.goto(f"{live_server}/?e2e=1", wait_until="domcontentloaded")
    page.get_by_test_id("cities-clear").click()
    page.get_by_test_id("discover-button").click()

    expect(page.get_by_test_id("companies-panel")).to_be_visible()
    expect(page.get_by_test_id("company-row")).to_have_count(2)

    page.get_by_test_id("companies-select-all").check()
    page.get_by_test_id("refresh-button").click()

    expect(page.get_by_test_id("jobs-count")).to_have_text("2")
    expect(page.get_by_test_id("job-row")).to_have_count(2)
    expect(page.get_by_test_id("jobs-body")).to_contain_text("Backend Engineer")
    expect(page.get_by_test_id("jobs-body")).to_contain_text("Data Scientist")


def test_filters_by_city_and_title(
    live_server, page, serpapi_env, serpapi_stub, provider_stub
):
    serpapi_stub(DISCOVER_STUB)
    provider_stub(PROVIDER_STUB)

    page.goto(f"{live_server}/?e2e=1", wait_until="domcontentloaded")
    page.get_by_test_id("cities-clear").click()
    page.get_by_test_id("discover-button").click()
    expect(page.get_by_test_id("company-row")).to_have_count(2)

    page.get_by_test_id("companies-select-all").check()
    page.get_by_test_id("refresh-button").click()
    expect(page.get_by_test_id("jobs-count")).to_have_text("2")

    page.get_by_test_id("city-select").select_option("Tel Aviv")
    expect(page.get_by_test_id("jobs-count")).to_have_text("1")
    expect(page.get_by_test_id("job-row")).to_have_count(1)

    page.get_by_test_id("title-filter").fill("Scientist")
    expect(page.get_by_test_id("jobs-count")).to_have_text("0")
    expect(page.get_by_test_id("job-row")).to_have_count(0)
