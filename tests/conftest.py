from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping

import pytest

os.environ.setdefault("AUTO_REFRESH_ON_START", "0")

from jobfinder.api import create_app

from jobfinder import pipeline


@pytest.fixture
def serpapi_env(monkeypatch):
    """
    Ensure SerpAPI is considered configured for discover() calls.
    """
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.setenv("SERPAPI_CACHE_TTL_SECONDS", "0")
    return "test-key"


@pytest.fixture
def serpapi_stub(monkeypatch):
    """
    Patch pipeline._http_get_json so discover() never hits the network.
    """

    def _stub(payloads: Mapping[str, Dict[str, Any]]):
        def fake_http(
            url: str, params: Dict[str, Any] | None = None, timeout: float = 25.0
        ):
            query = (params or {}).get("q", "")
            combined: List[Dict[str, Any]] = []
            for host, payload in payloads.items():
                if host in query:
                    results = payload.get("organic_results") if payload else None
                    if isinstance(results, list):
                        combined.extend(results)
            if combined:
                return {"organic_results": combined}
            return {"organic_results": []}

        monkeypatch.setattr(pipeline, "_http_get_json", fake_http)
        return fake_http

    return _stub


@pytest.fixture
def provider_stub(monkeypatch):
    """
    Patch pipeline._import_provider with a controllable in-memory fetcher.
    """

    def _stub(jobs_by_provider: Mapping[str, Mapping[str, Any]]):
        def fake_import(provider: str):
            provider_jobs = jobs_by_provider.get(provider, {})

            def fetch_jobs(
                org: str | None = None,
                slug: str | None = None,
                company: str | None = None,
                **_: Any,
            ):
                key = org or slug or company or ""
                return provider_jobs.get(key, [])

            return SimpleNamespace(fetch_jobs=fetch_jobs)

        monkeypatch.setattr(pipeline, "_import_provider", fake_import)
        return fake_import

    return _stub


@pytest.fixture
def temp_db_url(tmp_path, monkeypatch):
    """
    Provide an isolated SQLite DB for each test run.
    """
    path = tmp_path / "jobs.db"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", f"sqlite:///{path.as_posix()}")
    return path


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", "sqlite:///:memory:")
    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
