from __future__ import annotations

import pytest

from jobfinder.api import create_app


@pytest.fixture()
def app(monkeypatch, tmp_path):
    db_path = tmp_path / "jobs.db"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
