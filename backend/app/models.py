"""ORM tables.

Two invariants live in the schema rather than in Python, because a Python guard
is the first thing skipped at 3 a.m. before a demo:

- an Alert cannot be stored without at least one inspection task;
- one weather/phenology alert per farm, target and day (the risk job is
  idempotent by constraint, not by a SELECT-then-INSERT race).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    """A person who signs in: a farmer or an expert (KVK scientist, agriculture
    officer, agronomist). Both give a mobile number and an email; one-time codes
    go to the email until an SMS gateway is wired (config.OTP_CHANNEL)."""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(16), unique=True)
    email: Mapped[str | None] = mapped_column(String(200), unique=True)
    lang: Mapped[str] = mapped_column(String(2), default="en")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (CheckConstraint("role IN ('farmer', 'expert')", name="ck_user_role"),)


class FarmerProfile(Base):
    __tablename__ = "farmer_profile"

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    state: Mapped[str | None] = mapped_column(String(60))
    district: Mapped[str] = mapped_column(String(60))
    taluka: Mapped[str | None] = mapped_column(String(80))
    village: Mapped[str | None] = mapped_column(String(80))
    total_land_acres: Mapped[float | None] = mapped_column(Float)
    has_smartphone_data: Mapped[bool] = mapped_column(default=True)
    consent_at: Mapped[datetime] = mapped_column(DateTime)
    """When the farmer agreed to how their data is used (required)."""


class ExpertProfile(Base):
    __tablename__ = "expert_profile"

    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), primary_key=True)
    designation: Mapped[str] = mapped_column(String(30))
    organisation: Mapped[str] = mapped_column(String(160))
    employee_id: Mapped[str] = mapped_column(String(60))
    qualification: Mapped[str] = mapped_column(String(20))
    experience_years: Mapped[int] = mapped_column(Integer)
    districts: Mapped[list] = mapped_column(JSON)
    crops: Mapped[list] = mapped_column(JSON)
    specialities: Mapped[list] = mapped_column(JSON)
    languages: Mapped[list] = mapped_column(JSON)
    verified: Mapped[bool] = mapped_column(default=False)
    """Checked by the district office before verdicts count (auto in demo builds)."""


class OtpChallenge(Base):
    """One one-time code, sent to the account's email (SMS later). Only a salted
    hash is kept."""

    __tablename__ = "otp_challenge"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(40), unique=True)
    channel: Mapped[str] = mapped_column(String(8))
    destination: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(8))
    role: Mapped[str] = mapped_column(String(10))
    code_hash: Mapped[str] = mapped_column(String(64))
    salt: Mapped[str] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    user_agent: Mapped[str | None] = mapped_column(String(200))


class Farm(Base):
    __tablename__ = "farm"

    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    lang: Mapped[str] = mapped_column(String(2), default="en")
    crop: Mapped[str] = mapped_column(String(20))
    variety: Mapped[str | None] = mapped_column(String(80))
    sowing_date: Mapped[date] = mapped_column(Date)
    state: Mapped[str | None] = mapped_column(String(60))
    """Any state or union territory: the app is not one state's app."""
    district: Mapped[str] = mapped_column(String(60))
    village: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    area_acres: Mapped[float] = mapped_column(Float, default=1.0)
    soil: Mapped[str | None] = mapped_column(String(40))
    soil_ph: Mapped[float | None] = mapped_column(Float)  # from the farmer's Soil Health Card
    soil_ph_on: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(200))
    email_pref: Mapped[str] = mapped_column(String(10), default="warnings")
    """Which emails: 'warnings' (right away) + daily summary, 'all', 'digest' (summary only) or 'off'."""
    email_token: Mapped[str | None] = mapped_column(String(40))
    agro_polygon_id: Mapped[str | None] = mapped_column(String(40))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"))
    """The farmer who owns this farm; None for seeded demo farms."""
    irrigation: Mapped[str | None] = mapped_column(String(20))
    """rainfed | canal | borewell | open_well | farm_pond | drip | sprinkler"""
    location_source: Mapped[str] = mapped_column(String(10), default="district")
    """'gps' when the farmer stood in the field and allowed location, else
    'district' — the district headquarters, which the weather, the spray window
    and the 5 km outbreak radius all have to make do with until they do."""
    taluka: Mapped[str | None] = mapped_column(String(80))
    """This farm's field polygon at AgroMonitoring (satellite NDVI and soil)."""
    """Secret for the one-click unsubscribe link; never shown in the app."""
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    problems: Mapped[list[Problem]] = relationship(back_populates="farm")


class Problem(Base):
    """One thing going wrong on one farm, from first photo to resolution."""

    __tablename__ = "problem"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    target: Mapped[str | None] = mapped_column(String(60))
    """Current best label. Null while nobody — model or human — has settled it."""
    status: Mapped[str] = mapped_column(String(20), default="open")
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    farm: Mapped[Farm] = relationship(back_populates="problems")
    diagnoses: Mapped[list[Diagnosis]] = relationship(order_by="Diagnosis.id")
    observations: Mapped[list[Observation]] = relationship(order_by="Observation.id")


class Diagnosis(Base):
    __tablename__ = "diagnosis"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    image_path: Mapped[str | None] = mapped_column(String(255))
    topk: Mapped[list] = mapped_column(JSON)
    gate_outcome: Mapped[str] = mapped_column(String(10))
    gate_reason: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(80))
    is_stub: Mapped[bool] = mapped_column(default=True)
    heatmap: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Observation(Base):
    """A farmer's field answer. Doubt Doctor answers land here and travel into
    the expert's case bundle — without that the question is theatre."""

    __tablename__ = "observation"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    kind: Mapped[str] = mapped_column(String(20))
    cue_id: Mapped[str | None] = mapped_column(String(60))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Advisory(Base):
    __tablename__ = "advisory"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    target: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(20))
    """'model' when the gate advised, 'doubt_doctor' when a cue resolved it,
    'expert' when an agronomist confirmed or corrected."""
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FollowUp(Base):
    __tablename__ = "followup"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    due_on: Mapped[date] = mapped_column(Date)
    response: Mapped[str | None] = mapped_column(String(20))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)


class Case(Base):
    """An escalation waiting for a human expert."""

    __tablename__ = "case"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    status: Mapped[str] = mapped_column(String(20), default="open")
    reason: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class Confirmation(Base):
    """An expert's verdict. The labelled record that 'learns from field
    confirmations' reads — hotspots, the local prior and field accuracy."""

    __tablename__ = "confirmation"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("case.id"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    verdict: Mapped[str] = mapped_column(String(20))
    model_label: Mapped[str | None] = mapped_column(String(60))
    """What the model predicted, frozen at confirm time. A correction overwrites
    Problem.target, so the model's guess is unrecoverable afterwards."""
    final_label: Mapped[str] = mapped_column(String(60))
    expert_name: Mapped[str] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    referred_to_lab: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("verdict IN ('confirmed', 'corrected')", name="ck_confirmation_verdict"),
    )


class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    target: Mapped[str] = mapped_column(String(60))
    trigger: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(10))
    reason: Mapped[dict] = mapped_column(JSON)
    """Per-language sentence saying WHY, frozen at issue time."""
    tasks: Mapped[dict] = mapped_column(JSON)
    """Per-language list of 'go look here' tasks."""
    issued_on: Mapped[date] = mapped_column(Date)
    outcome: Mapped[str | None] = mapped_column(String(20))
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime)
    source_case_id: Mapped[int | None] = mapped_column(ForeignKey("case.id"))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    """When the phone / in-app notification for this alert went out."""
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        # COALESCE: a missing 'en' yields NULL, and a CHECK on NULL passes.
        # JSON syntax differs per database, so each gets its own spelling.
        CheckConstraint(
            "COALESCE(json_array_length(json_extract(tasks, '$.en')), 0) > 0",
            name="ck_alert_has_task",
        ).ddl_if(dialect="sqlite"),
        CheckConstraint(
            "COALESCE(json_array_length(tasks -> 'en'), 0) > 0",
            name="ck_alert_has_task",
        ).ddl_if(dialect="postgresql"),
        UniqueConstraint("farm_id", "target", "trigger", "issued_on", name="uq_alert_daily"),
    )


class TrapReading(Base):
    """Pheromone / light / sticky trap count — the PS's pest-trap input."""

    __tablename__ = "trap_reading"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    target: Mapped[str] = mapped_column(String(60))
    trap_type: Mapped[str] = mapped_column(String(20))
    count: Mapped[int] = mapped_column(Integer)
    traps: Mapped[int] = mapped_column(Integer, default=1)
    nights: Mapped[int] = mapped_column(Integer, default=1)
    recorded_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("count >= 0 AND traps > 0 AND nights > 0", name="ck_trap_positive"),
    )


class SensorReading(Base):
    """A daily summary from an in-field sensor. When present it overrides the
    regional forecast for that farm and day — the canopy is what the fungus
    feels, not the district."""

    __tablename__ = "sensor_reading"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    on: Mapped[date] = mapped_column(Date)
    rh_max: Mapped[float | None] = mapped_column(Float)
    t_min: Mapped[float | None] = mapped_column(Float)
    t_max: Mapped[float | None] = mapped_column(Float)
    rain_mm: Mapped[float | None] = mapped_column(Float)
    leaf_wetness_h: Mapped[float | None] = mapped_column(Float)
    soil_ph: Mapped[float | None] = mapped_column(Float)
    soil_moisture_pct: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (UniqueConstraint("farm_id", "on", name="uq_sensor_daily"),)


class LabelPrior(Base):
    __tablename__ = "label_prior"

    district: Mapped[str] = mapped_column(String(60), primary_key=True)
    crop: Mapped[str] = mapped_column(String(20), primary_key=True)
    target: Mapped[str] = mapped_column(String(60), primary_key=True)
    confirmed: Mapped[int] = mapped_column(Integer, default=0)
    corrected: Mapped[int] = mapped_column(Integer, default=0)


class LiveScan(Base):
    """One guided live walk. Frames are never stored; only the summary and the
    few evidence frames attached to problems it opened."""

    __tablename__ = "live_scan"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    location_source: Mapped[str] = mapped_column(String(10), default="farm")
    frames: Mapped[int] = mapped_column(default=0)
    good_frames: Mapped[int] = mapped_column(default=0)
    classified_views: Mapped[int] = mapped_column(default=0)
    verdict: Mapped[str] = mapped_column(String(20))
    findings: Mapped[dict] = mapped_column(JSON)
    context: Mapped[dict] = mapped_column(JSON)
    problem_ids: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(80))


class Notice(Base):
    """A weather advisory issued to one farm (app.engine.agromet). The text is
    rendered from the KB when read, in whoever's language is asking; only the
    numbers are frozen. One per farm and dedupe key — the watcher can run every
    half hour without repeating itself."""

    __tablename__ = "notice"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    rule: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(20))
    dedupe_key: Mapped[str] = mapped_column(String(80))
    values: Mapped[dict] = mapped_column(JSON)
    valid_until: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("farm_id", "dedupe_key", name="uq_notice_key"),
        CheckConstraint("severity IN ('warning', 'advice', 'info')", name="ck_notice_severity"),
    )


class PushSubscription(Base):
    """A browser's Web Push endpoint for one farm (the PWA on the farmer's phone)."""

    __tablename__ = "push_subscription"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    failures: Mapped[int] = mapped_column(Integer, default=0)


class SprayLog(Base):
    """'I sprayed just now' — lets the watcher warn when rain follows."""

    __tablename__ = "spray_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    product: Mapped[str | None] = mapped_column(String(120))
    sprayed_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EmailLog(Base):
    """Every email attempt: the daily summary is idempotent per farm and day by
    constraint, and the per-day cap counts these rows."""

    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farm.id"))
    kind: Mapped[str] = mapped_column(String(10))  # alert | digest | test
    dedupe_key: Mapped[str] = mapped_column(String(80))
    to_addr: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10))  # sent | outbox | failed
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("farm_id", "dedupe_key", name="uq_email_key"),)
