from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC in DB


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)  # administrator | investigator


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    role: Mapped[Role] = relationship(lazy="joined")


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    investigator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|in_review|closed
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    investigator: Mapped[User | None] = relationship()
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="case")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))  # server-generated, relative to ORIGINALS_DIR
    size_bytes: Mapped[int] = mapped_column(Integer)
    mime_type: Mapped[str] = mapped_column(String(128))  # detected from content
    declared_mime: Mapped[str] = mapped_column(String(128), default="")
    detected_type: Mapped[str] = mapped_column(String(32), index=True)
    source_description: Mapped[str] = mapped_column(Text, default="")
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    integrity_status: Mapped[str] = mapped_column(String(16), default="verified")  # verified|mismatch|unverified
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    case: Mapped[Case] = relationship(back_populates="evidence")
    uploader: Mapped[User] = relationship()


class EvidenceHash(Base):
    """Every hash computation (acquisition, pre/post analysis, manual verification)."""
    __tablename__ = "evidence_hashes"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    algorithm: Mapped[str] = mapped_column(String(16), default="sha256")
    value: Mapped[str] = mapped_column(String(64))
    context: Mapped[str] = mapped_column(String(24))  # acquisition|pre_analysis|post_analysis|manual
    matches_original: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    computed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|completed|aborted|failed
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    tool_versions: Mapped[str] = mapped_column(Text, default="{}")


class MetadataRecord(Base):
    __tablename__ = "metadata_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.id"))
    source: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(512))


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)  # UTC
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(64))  # metadata:* | case_activity | analyst
    provenance: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("evidence_id", "timestamp", "title", "source", name="uq_timeline_dedupe"),)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id"), index=True)
    category: Mapped[str] = mapped_column(String(16), index=True)  # benign|needs_review|suspicious
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16))  # automated_rule|ai_model|analyst
    confidence: Mapped[float | None] = mapped_column(Float)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    review_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|accepted|rejected
    analyst_interpretation: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Note(Base):
    __tablename__ = "investigator_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"))
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    method: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    is_conclusion: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    author: Mapped[User] = relationship()


class _Chained:
    seq: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(48), index=True)
    details: Mapped[str] = mapped_column(Text, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


class CustodyEvent(Base, _Chained):
    __tablename__ = "custody_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_ref: Mapped[str] = mapped_column(String(20), index=True)  # evidence_id string; survives deletion


class AuditLog(Base, _Chained):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), default="")


class ReportExport(Base):
    __tablename__ = "report_exports"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    format: Mapped[str] = mapped_column(String(8))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    generated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # integrity_mismatch|evidence_uploaded|pending_review|case_update
    message: Mapped[str] = mapped_column(String(300))
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    evidence_ref: Mapped[str | None] = mapped_column(String(20))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))


Index("ix_evidence_case_type", Evidence.case_id, Evidence.detected_type)
