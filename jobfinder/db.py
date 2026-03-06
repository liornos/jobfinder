from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from . import filtering
from .filtering import Job as JobModel

log = logging.getLogger(__name__)


def _json_type():
    """
    Prefer JSONB on Postgres; fall back to generic JSON elsewhere.
    Uses with_variant so SQLite still compiles.
    """
    try:
        from sqlalchemy.dialects.postgresql import JSONB

        return JSON().with_variant(JSONB, "postgresql")
    except Exception:
        return JSON


JSONType = _json_type()


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    org: Mapped[str] = mapped_column(String(255), nullable=False)
    careers_url: Mapped[Optional[str]] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    jobs: Mapped[List["Job"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("provider", "org", name="uq_provider_org"),)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    org: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE")
    )
    company_name: Mapped[Optional[str]] = mapped_column(String(255))
    company_city: Mapped[Optional[str]] = mapped_column(String(255))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    location: Mapped[Optional[str]] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    remote: Mapped[Optional[bool]] = mapped_column(Boolean)
    work_mode: Mapped[Optional[str]] = mapped_column(String(32))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONType)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    reasons: Mapped[Optional[str]] = mapped_column(Text)

    company: Mapped[Optional[Company]] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("ix_jobs_active_created_id", "is_active", "created_at", "id"),
        Index("ix_jobs_provider", "provider"),
        Index("ix_jobs_org", "org"),
        Index("ix_jobs_company_name", "company_name"),
    )


class AlertUser(Base):
    __tablename__ = "alert_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    alerts: Mapped[List["SavedSearchAlert"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_alert_users_email", "email"),)


class SavedSearchAlert(Base):
    __tablename__ = "saved_search_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("alert_users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[Optional[str]] = mapped_column(String(255))
    filter_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cities: Mapped[List[str]] = mapped_column(JSONType, default=list)
    keywords: Mapped[List[str]] = mapped_column(JSONType, default=list)
    title_keywords: Mapped[List[str]] = mapped_column(JSONType, default=list)
    provider: Mapped[Optional[str]] = mapped_column(String(64))
    remote: Mapped[str] = mapped_column(String(16), default="any")
    min_score: Mapped[int] = mapped_column(Integer, default=0)
    max_age_days: Mapped[Optional[int]] = mapped_column(Integer)
    only_active: Mapped[bool] = mapped_column(Boolean, default=True)
    send_limit: Mapped[int] = mapped_column(Integer, default=200)
    frequency_minutes: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["AlertUser"] = relationship(back_populates="alerts")
    deliveries: Mapped[List["AlertDelivery"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )
    seen_jobs: Mapped[List["AlertSeenJob"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "filter_hash", name="uq_alert_user_filter_hash"),
        Index("ix_alerts_user_active", "user_id", "is_active"),
        Index("ix_alerts_next_run", "next_run_at"),
    )


class AlertSeenJob(Base):
    __tablename__ = "alert_seen_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("saved_search_alerts.id", ondelete="CASCADE"), nullable=False
    )
    job_key: Mapped[str] = mapped_column(String(512), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    alert: Mapped["SavedSearchAlert"] = relationship(back_populates="seen_jobs")

    __table_args__ = (
        UniqueConstraint("alert_id", "job_key", name="uq_alert_seen_job"),
        Index("ix_alert_seen_alert_job", "alert_id", "job_key"),
    )


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("saved_search_alerts.id", ondelete="CASCADE"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    jobs_count: Mapped[int] = mapped_column(Integer, default=0)
    subject: Mapped[Optional[str]] = mapped_column(String(512))
    error_text: Mapped[Optional[str]] = mapped_column(Text)

    alert: Mapped["SavedSearchAlert"] = relationship(back_populates="deliveries")

    __table_args__ = (
        Index("ix_alert_deliveries_alert_sent", "alert_id", "sent_at"),
        Index("ix_alert_deliveries_status", "status"),
    )


_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker[Session]] = None
_DB_URL: Optional[str] = None
_SCHEMA_READY: set[str] = set()
_SCHEMA_LOCK = threading.Lock()


def _database_url(url: Optional[str] = None) -> str:
    return (
        url
        or os.getenv("JOBFINDER_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///jobfinder.db"
    )


def get_engine(url: Optional[str] = None) -> Engine:
    """
    Lazily create (and memoize) the SQLAlchemy engine.
    """
    global _ENGINE, _SESSION_FACTORY, _DB_URL
    resolved = _database_url(url)
    if _ENGINE is not None and _DB_URL == resolved:
        return _ENGINE

    kwargs: Dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if resolved.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    _ENGINE = create_engine(resolved, **kwargs)
    _SESSION_FACTORY = sessionmaker(
        bind=_ENGINE,
        autoflush=False,
        autocommit=False,
        future=True,
        expire_on_commit=False,
    )
    _DB_URL = resolved
    return _ENGINE


def get_session(url: Optional[str] = None) -> Session:
    engine = get_engine(url)
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY(bind=engine)


@contextmanager
def session_scope(url: Optional[str] = None) -> Iterator[Session]:
    """
    Provide a transactional scope around a series of operations.
    """
    session = get_session(url)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(url: Optional[str] = None) -> None:
    engine = get_engine(url)
    resolved = _database_url(url)
    if resolved in _SCHEMA_READY:
        return
    with _SCHEMA_LOCK:
        if resolved in _SCHEMA_READY:
            return
        Base.metadata.create_all(engine)
        if _ensure_schema(engine):
            _SCHEMA_READY.add(resolved)


def _ensure_schema(engine: Engine) -> bool:
    """
    Best-effort schema fixes for existing databases (add columns + indexes).
    """
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "jobs" not in tables:
            return True

        jobs_cols = {col["name"] for col in inspector.get_columns("jobs")}
        if "company_city" not in jobs_cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN company_city VARCHAR(255)")
                )
            jobs_cols.add("company_city")

        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_jobs_active_created_id "
                    "ON jobs (is_active, created_at, id)"
                )
            )
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_jobs_provider ON jobs (provider)")
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_org ON jobs (org)"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_jobs_company_name "
                    "ON jobs (company_name)"
                )
            )

            if "company_city" in jobs_cols and "companies" in tables:
                conn.execute(
                    text(
                        "UPDATE jobs SET company_city = ("
                        "SELECT city FROM companies WHERE companies.id = jobs.company_id"
                        ") WHERE company_city IS NULL"
                    )
                )
        return True
    except Exception as exc:
        log.warning("DB schema check skipped: %s", exc)
        return False


def _coerce_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    sval = str(val).strip().lower()
    if sval in {"1", "true", "yes", "y"}:
        return True
    if sval in {"0", "false", "no", "n"}:
        return False
    return None


def _parse_datetime(val: Any) -> Optional[datetime]:
    dt = filtering._parse_created_at(val)
    if dt:
        return dt
    return None


def _normalize_description(val: Any) -> Optional[str]:
    """
    Ensure description is stored as text (SQLite can't bind lists/dicts).
    """
    if val is None:
        return None
    if isinstance(val, str):
        return val
    try:
        import json as _json

        return _json.dumps(val, ensure_ascii=False)
    except Exception:
        return str(val)


def build_job_key(
    provider: str, org: str, external_id: Optional[str], url: Optional[str]
) -> str:
    """
    Stable job dedupe key. Prefer provider:org:<external_id>, else hash of URL.
    """
    prov = (provider or "").strip().lower()
    org_slug = (org or "").strip().lower()
    if external_id:
        return f"{prov}:{org_slug}:{external_id}"
    if url:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return f"{prov}:url:{digest}"
    digest = hashlib.sha1(f"{prov}:{org_slug}:fallback".encode("utf-8")).hexdigest()
    return f"{prov}:url:{digest}"


def upsert_company(session: Session, payload: Dict[str, Any]) -> Company:
    provider = (payload.get("provider") or "").strip().lower()
    org = (payload.get("org") or payload.get("name") or "").strip()
    if not provider or not org:
        raise ValueError("Company requires provider and org")

    stmt = select(Company).where(Company.provider == provider, Company.org == org)
    company = session.execute(stmt).scalar_one_or_none()

    if company is None:
        company = Company(
            name=payload.get("name") or org,
            city=payload.get("city"),
            provider=provider,
            org=org,
            careers_url=payload.get("careers_url"),
        )
        session.add(company)
    else:
        company.name = payload.get("name") or company.name
        company.city = payload.get("city") or company.city
        company.careers_url = payload.get("careers_url") or company.careers_url

    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        # Re-fetch in case of race
        company = session.execute(stmt).scalar_one()
    return company


def _score_job(
    job_dict: Dict[str, Any], keywords: Sequence[str], cities: Sequence[str]
) -> Tuple[int, str]:
    """
    Compute score + reasons using filtering.score (which expects a Job dataclass).
    """
    created_at = _parse_datetime(job_dict.get("created_at"))
    job_obj = JobModel(
        id=str(job_dict.get("id") or job_dict.get("url") or ""),
        title=job_dict.get("title") or "",
        company=job_dict.get("company") or "",
        url=job_dict.get("url") or "",
        location=job_dict.get("location"),
        remote=_coerce_bool(job_dict.get("remote")),
        created_at=created_at,
        provider=job_dict.get("provider"),
        extra=job_dict.get("extra"),
    )
    try:
        score_val, reasons = filtering.score(
            job_obj, list(keywords or []), list(cities or [])
        )
        return int(score_val or 0), ", ".join(reasons or [])
    except Exception:
        return int(job_dict.get("score") or 0), str(job_dict.get("reasons") or "")


def upsert_job(
    session: Session,
    *,
    company: Company,
    job_dict: Dict[str, Any],
    seen_at: datetime,
    keywords: Sequence[str],
    cities: Sequence[str],
) -> Job:
    provider = company.provider
    org = company.org
    external_id = str(job_dict.get("id") or "").strip() or None
    url = (job_dict.get("url") or "").strip()
    job_key = build_job_key(provider, org, external_id, url)

    created_at = _parse_datetime(job_dict.get("created_at"))
    description = _normalize_description(
        job_dict.get("description") or (job_dict.get("extra") or {}).get("description")
    )
    raw_json = job_dict.get("extra") or {}
    if not isinstance(raw_json, dict):
        raw_json = {"value": raw_json}
    work_mode = (raw_json.get("work_mode") or "").lower() or None

    score_val, reasons = _score_job(job_dict, keywords, cities)

    stmt = select(Job).where(Job.job_key == job_key)
    row = session.execute(stmt).scalar_one_or_none()

    if row is None:
        row = Job(
            job_key=job_key,
            provider=provider,
            org=org,
            company=company,
            company_name=company.name,
            company_city=company.city,
            title=job_dict.get("title"),
            location=job_dict.get("location"),
            url=url or job_key,
            remote=_coerce_bool(job_dict.get("remote")),
            work_mode=work_mode,
            description=description,
            created_at=created_at,
            last_seen_at=seen_at,
            is_active=True,
            external_id=external_id,
            raw_json=raw_json,
            score=score_val,
            reasons=reasons,
        )
        session.add(row)
    else:
        row.title = job_dict.get("title") or row.title
        row.location = job_dict.get("location") or row.location
        row.url = url or row.url
        row.remote = _coerce_bool(job_dict.get("remote"))
        row.work_mode = work_mode or row.work_mode
        row.description = description or row.description
        row.created_at = created_at or row.created_at
        row.last_seen_at = seen_at
        row.is_active = True
        row.external_id = external_id or row.external_id
        row.raw_json = raw_json or row.raw_json
        row.score = score_val
        row.reasons = reasons or row.reasons
        row.company = company
        row.company_name = company.name or row.company_name
        row.company_city = company.city or row.company_city

    session.flush()
    return row


def mark_inactive(
    session: Session,
    *,
    provider: str,
    org: str,
    seen_keys: Sequence[str],
    seen_at: datetime,
) -> int:
    """
    Mark jobs for a provider/org as inactive if they were not seen in the latest refresh.
    """
    conditions = [Job.provider == provider, Job.org == org]
    if seen_keys:
        conditions.append(Job.job_key.not_in(list(seen_keys)))
    stmt = update(Job).where(*conditions).values(is_active=False, last_seen_at=seen_at)
    res = session.execute(stmt)
    rowcount = getattr(res, "rowcount", None)
    return int(rowcount or 0)


def job_to_dict(row: Job, *, include_extra: bool = True) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": row.external_id or row.job_key,
        "job_key": row.job_key,
        "title": row.title,
        "company": row.company_name,
        "company_city": row.company_city,
        "provider": row.provider,
        "org": row.org,
        "location": row.location,
        "url": row.url,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
        "is_active": bool(row.is_active),
        "remote": row.remote,
        "score": row.score,
        "reasons": row.reasons,
    }

    if include_extra:
        extra = dict(row.raw_json or {})
        if row.work_mode and not extra.get("work_mode"):
            extra["work_mode"] = row.work_mode
        if row.description and not extra.get("description"):
            extra["description"] = row.description
        payload["extra"] = extra
    else:
        extra = {}
        if row.work_mode:
            extra["work_mode"] = row.work_mode
        payload["extra"] = extra
    return payload


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_text_list(values: Any) -> List[str]:
    if values is None:
        return []
    raw_values: List[str] = []
    if isinstance(values, list):
        for item in values:
            for part in str(item).split(","):
                part = part.strip()
                if part:
                    raw_values.append(part)
    else:
        for part in str(values).split(","):
            part = part.strip()
            if part:
                raw_values.append(part)

    out: List[str] = []
    seen = set()
    for item in raw_values:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return sorted(out, key=lambda x: x.lower())


def _clamp_int(value: Any, default: int, *, min_val: int, max_val: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_val, min(max_val, parsed))


def canonicalize_alert_filters(
    *,
    cities: Any = None,
    keywords: Any = None,
    title_keywords: Any = None,
    provider: Any = None,
    remote: Any = None,
    min_score: Any = 0,
    max_age_days: Any = None,
    only_active: Any = True,
    send_limit: Any = 200,
    frequency_minutes: Any = 60,
) -> Dict[str, Any]:
    max_age: Optional[int]
    try:
        max_age = int(max_age_days) if max_age_days not in (None, "") else None
    except (TypeError, ValueError):
        max_age = None
    return {
        "cities": _normalize_text_list(cities),
        "keywords": _normalize_text_list(keywords),
        "title_keywords": _normalize_text_list(title_keywords),
        "provider": (str(provider).strip().lower() or None) if provider else None,
        "remote": (str(remote).strip().lower() or "any"),
        "min_score": _clamp_int(min_score, 0, min_val=0, max_val=1000),
        "max_age_days": max_age,
        "only_active": bool(only_active),
        "send_limit": _clamp_int(send_limit, 200, min_val=1, max_val=500),
        "frequency_minutes": _clamp_int(
            frequency_minutes, 60, min_val=5, max_val=10080
        ),
    }


def build_alert_filter_hash(payload: Dict[str, Any]) -> str:
    identity_payload = {
        "cities": list(payload.get("cities") or []),
        "keywords": list(payload.get("keywords") or []),
        "title_keywords": list(payload.get("title_keywords") or []),
        "provider": payload.get("provider"),
        "remote": payload.get("remote"),
        "min_score": payload.get("min_score"),
        "max_age_days": payload.get("max_age_days"),
        "only_active": payload.get("only_active"),
    }
    raw = json.dumps(
        identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get_or_create_alert_user(session: Session, email: str) -> AlertUser:
    normalized = normalize_email(email)
    if not normalized:
        raise ValueError("Email is required")

    row = session.execute(
        select(AlertUser).where(AlertUser.email == normalized)
    ).scalar_one_or_none()
    if row is not None:
        return row

    row = AlertUser(email=normalized)
    session.add(row)
    try:
        session.flush()
        return row
    except IntegrityError:
        session.rollback()
        row = session.execute(
            select(AlertUser).where(AlertUser.email == normalized)
        ).scalar_one()
        return row


def upsert_saved_search_alert(
    session: Session,
    *,
    email: str,
    name: Optional[str] = None,
    cities: Any = None,
    keywords: Any = None,
    title_keywords: Any = None,
    provider: Any = None,
    remote: Any = None,
    min_score: Any = 0,
    max_age_days: Any = None,
    only_active: Any = True,
    send_limit: Any = 200,
    frequency_minutes: Any = 60,
) -> Tuple[SavedSearchAlert, bool]:
    user = get_or_create_alert_user(session, email)
    now = _utcnow()

    filters = canonicalize_alert_filters(
        cities=cities,
        keywords=keywords,
        title_keywords=title_keywords,
        provider=provider,
        remote=remote,
        min_score=min_score,
        max_age_days=max_age_days,
        only_active=only_active,
        send_limit=send_limit,
        frequency_minutes=frequency_minutes,
    )
    filter_hash = build_alert_filter_hash(filters)

    existing = session.execute(
        select(SavedSearchAlert).where(
            SavedSearchAlert.user_id == user.id,
            SavedSearchAlert.filter_hash == filter_hash,
        )
    ).scalar_one_or_none()

    if existing is None:
        row = SavedSearchAlert(
            user_id=user.id,
            name=(name or "").strip() or None,
            filter_hash=filter_hash,
            cities=list(filters["cities"]),
            keywords=list(filters["keywords"]),
            title_keywords=list(filters["title_keywords"]),
            provider=filters["provider"],
            remote=str(filters["remote"]),
            min_score=int(filters["min_score"]),
            max_age_days=filters["max_age_days"],
            only_active=bool(filters["only_active"]),
            send_limit=int(filters["send_limit"]),
            frequency_minutes=int(filters["frequency_minutes"]),
            is_active=True,
            next_run_at=now,
        )
        session.add(row)
        session.flush()
        return row, True

    existing.name = (name or "").strip() or existing.name
    existing.cities = list(filters["cities"])
    existing.keywords = list(filters["keywords"])
    existing.title_keywords = list(filters["title_keywords"])
    existing.provider = filters["provider"]
    existing.remote = str(filters["remote"])
    existing.min_score = int(filters["min_score"])
    existing.max_age_days = filters["max_age_days"]
    existing.only_active = bool(filters["only_active"])
    existing.send_limit = int(filters["send_limit"])
    existing.frequency_minutes = int(filters["frequency_minutes"])
    existing.is_active = True
    existing.next_run_at = now
    session.flush()
    return existing, False


def list_saved_search_alerts(
    session: Session,
    *,
    email: str,
    include_inactive: bool = False,
) -> List[SavedSearchAlert]:
    normalized = normalize_email(email)
    if not normalized:
        return []

    stmt = (
        select(SavedSearchAlert)
        .join(AlertUser, AlertUser.id == SavedSearchAlert.user_id)
        .where(AlertUser.email == normalized)
        .order_by(SavedSearchAlert.created_at.desc(), SavedSearchAlert.id.desc())
    )
    if not include_inactive:
        stmt = stmt.where(SavedSearchAlert.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_saved_search_alert(
    session: Session, *, alert_id: int, email: Optional[str] = None
) -> Optional[SavedSearchAlert]:
    stmt = select(SavedSearchAlert).where(SavedSearchAlert.id == int(alert_id))
    if email is not None:
        normalized = normalize_email(email)
        stmt = stmt.join(AlertUser, AlertUser.id == SavedSearchAlert.user_id).where(
            AlertUser.email == normalized
        )
    return session.execute(stmt).scalar_one_or_none()


def delete_saved_search_alert(session: Session, *, alert_id: int, email: str) -> bool:
    row = get_saved_search_alert(session, alert_id=alert_id, email=email)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def list_due_saved_search_alert_ids(
    session: Session, *, now: Optional[datetime] = None, limit: int = 200
) -> List[int]:
    now_val = now or _utcnow()
    max_rows = _clamp_int(limit, 200, min_val=1, max_val=1000)
    stmt = (
        select(SavedSearchAlert.id)
        .where(
            SavedSearchAlert.is_active.is_(True),
            SavedSearchAlert.next_run_at <= now_val,
        )
        .order_by(SavedSearchAlert.next_run_at.asc(), SavedSearchAlert.id.asc())
        .limit(max_rows)
    )
    return [int(x) for x in session.scalars(stmt).all()]


def touch_saved_search_alert_run(
    session: Session,
    *,
    alert: SavedSearchAlert,
    ran_at: Optional[datetime] = None,
    sent: bool = False,
) -> SavedSearchAlert:
    now = ran_at or _utcnow()
    alert.last_run_at = now
    if sent:
        alert.last_sent_at = now
    freq = _clamp_int(alert.frequency_minutes, 60, min_val=5, max_val=10080)
    alert.next_run_at = now + timedelta(minutes=freq)
    session.flush()
    return alert


def record_alert_delivery(
    session: Session,
    *,
    alert_id: int,
    status: str,
    jobs_count: int = 0,
    subject: Optional[str] = None,
    error_text: Optional[str] = None,
    sent_at: Optional[datetime] = None,
) -> AlertDelivery:
    row = AlertDelivery(
        alert_id=int(alert_id),
        sent_at=sent_at or _utcnow(),
        status=(status or "").strip().lower() or "unknown",
        jobs_count=max(0, int(jobs_count or 0)),
        subject=(subject or "").strip() or None,
        error_text=(error_text or "").strip() or None,
    )
    session.add(row)
    session.flush()
    return row


def get_seen_job_keys_for_alert(
    session: Session, *, alert_id: int, job_keys: Sequence[str]
) -> set[str]:
    normalized = [str(k).strip() for k in (job_keys or []) if str(k).strip()]
    if not normalized:
        return set()
    stmt = select(AlertSeenJob.job_key).where(
        AlertSeenJob.alert_id == int(alert_id), AlertSeenJob.job_key.in_(normalized)
    )
    return {str(x) for x in session.scalars(stmt).all()}


def mark_seen_job_keys_for_alert(
    session: Session,
    *,
    alert_id: int,
    job_keys: Sequence[str],
    first_seen_at: Optional[datetime] = None,
) -> int:
    seen_at = first_seen_at or _utcnow()
    unique_keys: List[str] = []
    seen = set()
    for item in job_keys or []:
        key = str(item).strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique_keys.append(key)
    if not unique_keys:
        return 0

    existing = get_seen_job_keys_for_alert(
        session, alert_id=alert_id, job_keys=unique_keys
    )
    to_insert = [k for k in unique_keys if k not in existing]
    if not to_insert:
        return 0

    for key in to_insert:
        session.add(
            AlertSeenJob(alert_id=int(alert_id), job_key=key, first_seen_at=seen_at)
        )
    session.flush()
    return len(to_insert)


def alert_to_dict(row: SavedSearchAlert) -> Dict[str, Any]:
    return {
        "id": int(row.id),
        "email": row.user.email if row.user else None,
        "name": row.name,
        "cities": list(row.cities or []),
        "keywords": list(row.keywords or []),
        "title_keywords": list(row.title_keywords or []),
        "provider": row.provider,
        "remote": row.remote,
        "min_score": int(row.min_score or 0),
        "max_age_days": row.max_age_days,
        "only_active": bool(row.only_active),
        "send_limit": int(row.send_limit or 0),
        "frequency_minutes": int(row.frequency_minutes or 0),
        "is_active": bool(row.is_active),
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
