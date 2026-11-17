from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, UTCDateTime, utcnow

ROLES = ("admin", "dpo", "it", "auditor")
ANSWER_STATUSES = ("compliant", "partial", "non_compliant", "not_applicable", "not_assessed")
CHECK_STATUSES = ("PASS", "FAIL", "MANUAL")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    locale: Mapped[str] = mapped_column(String(8), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Two-factor sign-in (TOTP, RFC 6238). The secret is stored encrypted (see app/totp.py).
    totp_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_counter: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditLog(Base):
    """Append-only. Each row carries the hash of the previous row (tamper evidence).

    UPDATE/DELETE are blocked by ORM events (app/audit.py) and, on SQLite and
    Postgres, by database triggers created in the migration.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Answer(Base):
    """Self-attested status for one catalog requirement."""

    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="not_assessed")
    note: Mapped[str] = mapped_column(Text, default="")
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class EvidenceFile(Base):
    __tablename__ = "evidence_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CheckRun(Base):
    """One batch of automated findings (a Prowler scan, a Linux collector run, an import)."""

    __tablename__ = "check_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # prowler-import | prowler-run | linux-collector | oscal-import
    provider: Mapped[str] = mapped_column(String(16))  # aws | linux
    target: Mapped[str] = mapped_column(String(255))  # account id or hostname
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    filename: Mapped[str] = mapped_column(String(255), default="")
    file_sha256: Mapped[str] = mapped_column(String(64), default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    manual: Mapped[int] = mapped_column(Integer, default=0)
    unmapped: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    error: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    results: Mapped[list["CheckResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )


class CheckResult(Base):
    __tablename__ = "check_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("check_runs.id", ondelete="CASCADE"), index=True)
    check_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(8))
    severity: Mapped[str] = mapped_column(String(16), default="")
    resource_uid: Mapped[str] = mapped_column(String(512), default="")
    region: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(512), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    sha256: Mapped[str] = mapped_column(String(64), default="")

    run: Mapped[CheckRun] = relationship(back_populates="results")


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    overall: Mapped[float] = mapped_column(Float)
    by_area: Mapped[dict] = mapped_column(JSON, default=dict)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(String(64), default="")
    run_id: Mapped[int | None] = mapped_column(ForeignKey("check_runs.id", ondelete="SET NULL"), nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class ProcessingActivity(Base):
    """One entry in the records of processing (controller or processor register)."""

    __tablename__ = "processing_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="controller")  # controller | processor
    name: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(Text, default="")
    lawful_basis: Mapped[str] = mapped_column(String(255), default="")
    data_subjects: Mapped[list] = mapped_column(JSON, default=list)
    data_categories: Mapped[list] = mapped_column(JSON, default=list)
    sensitive_categories: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(255), default="")
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    cross_border: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_countries: Mapped[list] = mapped_column(JSON, default=list)
    transfer_safeguards: Mapped[str] = mapped_column(Text, default="")
    retention: Mapped[str] = mapped_column(String(255), default="")
    security_measures: Mapped[str] = mapped_column(Text, default="")
    systems: Mapped[list] = mapped_column(JSON, default=list)
    client_name: Mapped[str] = mapped_column(String(255), default="")  # processor register: on whose behalf
    owner: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | archived
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


OBLIGATION_KINDS = ("licence", "permit", "dpo_registration", "consent_mechanism", "cross_border_flow", "other")
OBLIGATION_STATUSES = ("planned", "applied", "active", "expired", "not_needed")


class Obligation(Base):
    """A licence, permit, registration or recurring duty the organisation tracks."""

    __tablename__ = "obligations"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    reference: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="planned")
    issued_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_due: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expiry_from_default: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str] = mapped_column(String(128), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Reminder(Base):
    """In-app reminder generated by the scheduler for an upcoming or missed date."""

    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("obligation_id", "kind", "due"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    obligation_id: Mapped[int] = mapped_column(ForeignKey("obligations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # expiry | review
    due: Mapped[datetime] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dismissed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


INCIDENT_STATUSES = ("open", "contained", "notified", "closed")


class Incident(Base):
    """A personal data breach (or suspected breach) and its notification clocks."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="open")
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    discovered_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    data_categories: Mapped[list] = mapped_column(JSON, default=list)
    affected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    systems: Mapped[list] = mapped_column(JSON, default=list)
    likely_consequences: Mapped[str] = mapped_column(Text, default="")
    measures_taken: Mapped[str] = mapped_column(Text, default="")
    contact: Mapped[str] = mapped_column(String(255), default="")
    individuals_notice_needed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    regulator_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    individuals_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    source: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. {"run_id": 16, "check_id": "..."}
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    events: Mapped[list["IncidentEvent"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="IncidentEvent.at", lazy="selectin"
    )


class IncidentEvent(Base):
    """Timeline entry: what happened and who recorded it."""

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))  # created | status | note | notified_regulator | notified_individuals | edited
    text: Mapped[str] = mapped_column(Text, default="")
    actor_name: Mapped[str] = mapped_column(String(128), default="")

    incident: Mapped[Incident] = relationship(back_populates="events")


# --------------------------------------------------------------------------- governance modules

class Task(Base):
    """A remediation task: who fixes which gap, by when."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    requirement_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # gap | risk | incident | dpia | vendor | manual
    source_id: Mapped[str] = mapped_column(String(64), default="")
    owner: Mapped[str] = mapped_column(String(128), default="")
    priority: Mapped[str] = mapped_column(String(8), default="medium")  # low | medium | high
    status: Mapped[str] = mapped_column(String(16), default="todo")  # todo | in_progress | blocked | done
    due_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Risk(Base):
    """Privacy risk register entry, scored likelihood x impact on 1-5 scales."""

    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    likelihood: Mapped[int] = mapped_column(Integer, default=3)
    impact: Mapped[int] = mapped_column(Integer, default=3)
    residual_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    treatment: Mapped[str] = mapped_column(String(16), default="mitigate")  # mitigate | accept | transfer | avoid
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | treating | accepted | closed
    owner: Mapped[str] = mapped_column(String(128), default="")
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)
    controls: Mapped[str] = mapped_column(Text, default="")
    review_due: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    accepted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acceptance_expires_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acceptance_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class DataRequest(Base):
    """A request from an individual about their personal data (access, correction, deletion, and so on)."""

    __tablename__ = "data_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_type: Mapped[str] = mapped_column(String(24))
    requester: Mapped[str] = mapped_column(String(128))
    channel: Mapped[str] = mapped_column(String(64), default="")
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="received")  # received | in_progress | completed | refused
    details: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    owner: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Vendor(Base):
    """A processor, sub-processor or other recipient of personal data."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    service: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(16), default="processor")  # processor | sub_processor | recipient
    data_categories: Mapped[list] = mapped_column(JSON, default=list)
    countries: Mapped[list] = mapped_column(JSON, default=list)
    dpa_signed: Mapped[bool] = mapped_column(Boolean, default=False)
    dpa_signed_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    due_diligence_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    next_review_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(8), default="medium")
    security_notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | offboarded
    owner: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Dpia(Base):
    """Data protection impact assessment for one processing activity."""

    __tablename__ = "dpias"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("processing_activities.id", ondelete="SET NULL"), nullable=True)
    screening: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    necessity: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    measures: Mapped[str] = mapped_column(Text, default="")
    residual_risk: Mapped[str] = mapped_column(String(8), default="")  # low | medium | high
    dpo_opinion: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | in_review | approved | rejected
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_due: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    owner: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Policy(Base):
    """A versioned policy or procedure document."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(32), default="0.1")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved | retired
    owner: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    requirement_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_file_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_files.id", ondelete="SET NULL"), nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_on: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_due: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)  # [{version, status, at, by}]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
