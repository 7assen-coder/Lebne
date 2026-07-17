"""SQLAlchemy models for crowdsourcing (Postgres in Docker / prod)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ROLES = ("owner", "reviewer", "contributor")
ROLE_OWNER = "owner"
ROLE_REVIEWER = "reviewer"
ROLE_CONTRIBUTOR = "contributor"
CONSENSUS_NEEDED = 3
REVIEWER_DAILY_LIMIT = 100

AUDIO_STATUS_UPLOADING = "uploading"
AUDIO_STATUS_READY = "ready"
AUDIO_STATUS_FAILED = "failed"
AUDIO_STATUS_DELETED = "deleted"


class ContribBase(DeclarativeBase):
    pass


class CrowdUser(ContribBase):
    __tablename__ = "contrib_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Derived cache: True iff role == owner (compat for older clients)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(32), default=ROLE_CONTRIBUTOR, index=True)
    # Bumped on role change to invalidate outstanding JWTs
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list[Submission]] = relationship(
        back_populates="user",
        foreign_keys="[Submission.user_id]",
    )
    reviews: Mapped[list[Submission]] = relationship(
        back_populates="reviewer",
        foreign_keys="[Submission.reviewed_by]",
    )
    progress: Mapped[list[UserProgress]] = relationship(back_populates="user")
    review_votes: Mapped[list[ReviewVote]] = relationship(back_populates="reviewer")
    audit_events: Mapped[list[AuditLog]] = relationship(back_populates="actor")
    audio_assets: Mapped[list[AudioAsset]] = relationship(back_populates="uploader")


class PromptItem(ContribBase):
    __tablename__ = "contrib_prompt_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source_text: Mapped[str] = mapped_column(Text)
    assistant_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_locale: Mapped[str] = mapped_column(String(32), index=True)
    intent: Mapped[str] = mapped_column(String(64), index=True)
    source_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    translations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list[Submission]] = relationship(back_populates="prompt")
    progress: Mapped[list[UserProgress]] = relationship(back_populates="prompt")


class AudioAsset(ContribBase):
    """Metadata for a durable voice clip (bytes in R2 or Neon payload)."""

    __tablename__ = "contrib_audio_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    object_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    content_type: Mapped[str] = mapped_column(String(64), default="audio/webm")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(16), default="neon")  # r2 | neon
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("contrib_users.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default=AUDIO_STATUS_UPLOADING, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Soft link (no FK) to avoid circular create with submissions.audio_id
    submission_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    uploader: Mapped[CrowdUser | None] = relationship(back_populates="audio_assets")


class AudioPayload(ContribBase):
    """Neon fallback bytes keyed by object_key (used when R2 is not configured)."""

    __tablename__ = "contrib_audio_payloads"

    object_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), default="audio/webm")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Submission(ContribBase):
    __tablename__ = "contrib_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("contrib_prompt_items.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("contrib_users.id"), nullable=True, index=True)
    target_locale: Mapped[str] = mapped_column(String(32), index=True)
    text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # legacy
    audio_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contrib_audio_assets.id"), nullable=True, index=True
    )
    # pending | awaiting_consensus | approved | rejected
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    contributor_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("contrib_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prompt: Mapped[PromptItem] = relationship(back_populates="submissions")
    user: Mapped[CrowdUser | None] = relationship(
        back_populates="submissions",
        foreign_keys=[user_id],
    )
    reviewer: Mapped[CrowdUser | None] = relationship(
        back_populates="reviews",
        foreign_keys=[reviewed_by],
    )
    votes: Mapped[list[ReviewVote]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class UserProgress(ContribBase):
    __tablename__ = "contrib_user_progress"
    __table_args__ = (UniqueConstraint("user_id", "prompt_id", "locale", name="uq_user_prompt_locale"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("contrib_users.id"), index=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("contrib_prompt_items.id"), index=True)
    locale: Mapped[str] = mapped_column(String(32), index=True)
    # True = skipped (hidden from queue, does NOT count toward progress)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[CrowdUser] = relationship(back_populates="progress")
    prompt: Mapped[PromptItem] = relationship(back_populates="progress")


class ReviewVote(ContribBase):
    __tablename__ = "contrib_review_votes"
    __table_args__ = (UniqueConstraint("submission_id", "reviewer_id", name="uq_vote_submission_reviewer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("contrib_submissions.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("contrib_users.id"), index=True)
    action: Mapped[str] = mapped_column(String(32), default="approve")
    text_snapshot: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped[Submission] = relationship(back_populates="votes")
    reviewer: Mapped[CrowdUser] = relationship(back_populates="review_votes")


class AuditLog(ContribBase):
    __tablename__ = "contrib_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("contrib_users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    actor: Mapped[CrowdUser | None] = relationship(back_populates="audit_events")


class AudioBlob(ContribBase):
    """Legacy Neon bytes by basename — migrated to AudioAsset + R2/payload; keep for backfill."""

    __tablename__ = "contrib_audio_blobs"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), default="audio/webm")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
