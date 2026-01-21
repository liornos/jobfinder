from __future__ import annotations

from jobfinder import pipeline
from jobfinder.providers import (
    ashby,
    breezy,
    icims,
    jobvite,
    recruitee,
    smartrecruiters,
    workable,
    workday,
)

from tests.unit.providers.contract import assert_normalized_job


def test_ashby_stub_returns_list():
    assert ashby.fetch_jobs("acme") == []


def test_breezy_parsing(monkeypatch):
    fixture = {
        "positions": [
            {
                "id": "1",
                "name": "QA Engineer",
                "location": {"name": "Tel Aviv"},
                "url": "https://acme.breezy.hr/p/1",
                "created_at": "2025-01-01T00:00:00Z",
                "remote": True,
                "description": "QA role",
            }
        ]
    }

    monkeypatch.setattr(breezy, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = breezy.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "breezy", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)


def test_smartrecruiters_parsing(monkeypatch):
    fixture = {
        "content": [
            {
                "id": "SR-1",
                "name": "Backend Engineer",
                "location": {"city": "Tel Aviv", "country": "Israel"},
                "releasedDate": "2025-01-02T00:00:00Z",
                "ref": "https://jobs.smartrecruiters.com/acme/SR-1",
            }
        ]
    }

    monkeypatch.setattr(smartrecruiters, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = smartrecruiters.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [
        pipeline._normalize_job(company, "smartrecruiters", j) for j in raw_jobs
    ]
    for job in normalized:
        assert_normalized_job(job)


def test_recruitee_parsing(monkeypatch):
    fixture = {
        "offers": [
            {
                "id": 123,
                "title": "Data Engineer",
                "location": "Tel Aviv",
                "careers_url": "https://acme.recruitee.com/o/123",
                "created_at": "2025-01-03T00:00:00Z",
                "remote": False,
                "description": "Data role",
            }
        ]
    }

    monkeypatch.setattr(recruitee, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = recruitee.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "recruitee", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)


def test_jobvite_parsing(monkeypatch):
    fixture = {
        "jobs": [
            {
                "jobId": "JV-1",
                "title": "Frontend Engineer",
                "location": "Tel Aviv",
                "applyUrl": "https://acme.jobvite.com/j/JV-1",
                "datePosted": "2025-01-04T00:00:00Z",
                "remote": False,
                "description": "Frontend role",
            }
        ]
    }

    monkeypatch.setattr(jobvite, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = jobvite.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "jobvite", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)


def test_icims_parsing(monkeypatch):
    fixture = {
        "searchResults": [
            {
                "jobId": "IC-1",
                "jobTitle": "QA Engineer",
                "location": "Tel Aviv",
                "jobUrl": "https://careers-acme.icims.com/jobs/IC-1",
                "datePosted": "2025-01-05T00:00:00Z",
                "remote": True,
                "description": "QA role",
            }
        ]
    }

    monkeypatch.setattr(icims, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = icims.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "icims", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)


def test_workable_parsing(monkeypatch):
    fixture = {
        "results": [
            {
                "id": "WB-1",
                "title": "Platform Engineer",
                "location": {"city": "Tel Aviv", "country": "Israel"},
                "url": "https://apply.workable.com/acme/j/WB-1/",
                "published_at": "2025-01-06T00:00:00Z",
                "workplace_type": "remote",
                "description": "Platform role",
            }
        ]
    }

    monkeypatch.setattr(workable, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = workable.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "workable", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)


def test_workday_parsing(monkeypatch):
    fixture = {
        "jobPostings": [
            {
                "jobPostingId": "WD-1",
                "title": "ML Engineer",
                "location": "Tel Aviv",
                "externalPath": "https://acme.myworkdayjobs.com/en-US/job/WD-1",
                "postedOn": "2025-01-07T00:00:00Z",
                "remote": False,
                "description": "ML role",
            }
        ]
    }

    monkeypatch.setattr(workday, "get_json", lambda *_args, **_kwargs: fixture)

    raw_jobs = workday.fetch_jobs("acme", limit=10)
    assert raw_jobs

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "workday", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)
