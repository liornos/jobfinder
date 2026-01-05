from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jobfinder import filtering
from jobfinder.models import Job


def test_score_counts_keywords_city_and_recency():
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    job = Job(
        id="1",
        title="Senior Data Engineer",
        company="Acme",
        url="https://example.com",
        location="Tel Aviv",
        remote=True,
        created_at=recent,
        provider="greenhouse",
        extra={"work_mode": "remote"},
    )

    s, reasons = filtering.score(job, keywords=["data"], cities=["Tel Aviv"])

    assert s >= 70  # title + city + remote + recency baseline without fuzz
    assert "title:data" in reasons
    assert "city" in reasons
    assert any(r.startswith("fresh-") for r in reasons)


def test_apply_filters_remote_and_city_logic():
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": "r1",
            "provider": "greenhouse",
            "remote": True,
            "location": "Anywhere",
            "company_city": "Tel Aviv",
            "score": 10,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "remote"},
        },
        {
            "id": "r2",
            "provider": "greenhouse",
            "remote": False,
            "location": "Tel Aviv",
            "score": 20,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "onsite"},
        },
        {
            "id": "r3",
            "provider": "lever",
            "remote": False,
            "location": "Tel Aviv",
            "score": 25,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "onsite"},
        },
    ]

    filters = {
        "provider": ["greenhouse"],
        "remote": "true",
        "cities": ["tel aviv"],
        "min_score": 5,
    }
    filtered = filtering.apply_filters(rows, filters)

    assert [r["id"] for r in filtered] == ["r1"]


def test_apply_filters_city_blocks_explicit_other_locations_even_if_remote():
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": "ny1",
            "provider": "greenhouse",
            "remote": True,
            "location": "New York",
            "company_city": "Tel Aviv",
            "score": 10,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "remote"},
        }
    ]

    filters = {"cities": ["tel aviv"], "min_score": 1}
    filtered = filtering.apply_filters(rows, filters)

    assert [r["id"] for r in filtered] == []


def test_apply_filters_city_blocks_remote_with_region_suffix():
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": "r1",
            "provider": "greenhouse",
            "remote": True,
            "location": "Remote, sg",
            "company_city": "Tel Aviv",
            "score": 10,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "remote"},
        }
    ]

    filters = {"cities": ["tel aviv"], "min_score": 1}
    filtered = filtering.apply_filters(rows, filters)

    assert [r["id"] for r in filtered] == []


def test_apply_filters_respects_age_and_score():
    now = datetime.now(timezone.utc)
    rows = [
        {
            "id": "fresh",
            "provider": "greenhouse",
            "remote": False,
            "location": "NYC",
            "score": 15,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "onsite"},
        },
        {
            "id": "old",
            "provider": "greenhouse",
            "remote": False,
            "location": "NYC",
            "score": 30,
            "created_at": (now - timedelta(days=60)).isoformat(),
            "extra": {"work_mode": "onsite"},
        },
        {
            "id": "low",
            "provider": "greenhouse",
            "remote": False,
            "location": "NYC",
            "score": 1,
            "created_at": now.isoformat(),
            "extra": {"work_mode": "onsite"},
        },
    ]

    filters = {"provider": "greenhouse", "max_age_days": 30, "min_score": 10}
    filtered = filtering.apply_filters(rows, filters)

    ids = {r["id"] for r in filtered}
    assert "fresh" in ids
    assert "old" not in ids
    assert "low" not in ids


def test_parse_created_at_accepts_multiple_formats():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert filtering._parse_created_at(now) == now

    iso = filtering._parse_created_at("2025-01-01T00:00:00Z")
    assert iso and iso.year == 2025 and iso.tzinfo == timezone.utc

    epoch_ms = filtering._parse_created_at(int(now.timestamp() * 1000))
    assert epoch_ms and abs(epoch_ms.timestamp() - now.timestamp()) < 1
