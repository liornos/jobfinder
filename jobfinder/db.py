from __future__ import annotations

import hashlib
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
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


_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker[Session]] = None
_DB_URL: Optional[str] = None


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
    Base.metadata.create_all(engine)
    _ensure_schema(engine)


def _ensure_schema(engine: Engine) -> None:
    """
    Best-effort schema fixes for existing databases (add columns + indexes).
    """
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        if "jobs" not in tables:
            return

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
    except Exception as exc:
        log.warning("DB schema check skipped: %s", exc)


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
