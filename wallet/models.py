"""Persistent wallet models (Postgres in prod, SQLite for local/tests)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wallet.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    phone: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), default="Lebne User", nullable=False)
    # Placeholder until first set — argon2id via wallet.passwords
    password_hash: Mapped[str] = mapped_column(String(255), default="pending:unset", nullable=False)
    balance_mru: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    ledger_entries: Mapped[list[LedgerEntry]] = relationship(back_populates="user")


class LedgerEntry(Base):
    """Append-only money movement. Balance on UserAccount is the cached sum."""

    __tablename__ = "ledger_entries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_ledger_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_accounts.user_id"), nullable=False, index=True)
    amount_mru: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed: +credit / -debit
    kind: Mapped[str] = mapped_column(String(64), nullable=False)  # topup | transfer_in | transfer_out | fee | adjust
    reference: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user: Mapped[UserAccount] = relationship(back_populates="ledger_entries")
