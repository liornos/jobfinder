from __future__ import annotations

import os
from urllib.parse import quote

import pytest

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import expect, sync_playwright
except Exception:  # pragma: no cover - optional dependency
    pytest.skip("playwright not installed", allow_module_level=True)


if os.getenv("RUN_PROD_SMOKE") != "1":
    pytest.skip("prod smoke disabled", allow_module_level=True)


BASE_URL = os.getenv(
    "JOBFINDER_SMOKE_URL", "https://jobfinder-8def.onrender.com"
).rstrip("/")
CITY = os.getenv("JOBFINDER_SMOKE_CITY", "Tel Aviv")


def _attempt_search(page, url: str) -> tuple[str, int]:
    page.goto(url, wait_until="domcontentloaded")
    status = page.locator("#statusMsg")
    expect(status).not_to_have_text("", timeout=60000)
    try:
        page.wait_for_function(
            """
            () => {
              const el = document.querySelector('#statusMsg');
              if (!el) return false;
              const text = (el.textContent || '').trim();
              return text && text !== 'Loading jobs...';
            }
            """,
            timeout=90000,
        )
    except PlaywrightTimeoutError:
        pass
    status_text = status.inner_text()
    count_text = page.locator("#resultsCount").inner_text()
    try:
        count = int(count_text.strip())
    except ValueError:
        count = 0
    return status_text, count


def test_search_city_shows_results():
    url = f"{BASE_URL}/search?cities={quote(CITY)}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(90000)

        last_status = ""
        last_count = 0
        for _ in range(3):
            status_text, count = _attempt_search(page, url)
            last_status = status_text
            last_count = count
            if "Loaded" in status_text and count > 0:
                break
            page.wait_for_timeout(5000)
            page.reload(wait_until="domcontentloaded")

        assert "Loaded" in last_status, f"Unexpected status: {last_status}"
        assert last_count > 0, "Expected at least one job result"
        expect(page.locator("#resultsBody")).not_to_contain_text("No jobs found")

        browser.close()
