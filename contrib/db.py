"""Contrib DB engine (Postgres in Docker; SQLite for tests)."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import get_settings
from contrib.models import ContribBase, ROLE_CONTRIBUTOR, ROLE_OWNER


@lru_cache
def get_contrib_engine() -> Engine:
    settings = get_settings()
    url = settings.contrib_database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    pool_kwargs: dict = {}
    if not url.startswith("sqlite"):
        # Sized for ~100 concurrent crowd users on a single API instance + Neon.
        pool_kwargs = {
            "pool_size": 12,
            "max_overflow": 24,
            "pool_recycle": 1800,
            "pool_timeout": 30,
        }
    engine = create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
        **pool_kwargs,
    )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_fk(dbapi_conn, _):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def reset_contrib_engine() -> None:
    get_contrib_engine.cache_clear()


def _ensure_columns(engine: Engine) -> None:
    """Additive columns + role backfill."""
    alters = [
        ("contrib_prompt_items", "assistant_text", "TEXT"),
        ("contrib_prompt_items", "translations_json", "TEXT"),
        ("contrib_submissions", "answer_text", "TEXT"),
        ("contrib_submissions", "audio_id", "VARCHAR(36)"),
        ("contrib_users", "role", "VARCHAR(32)"),
        ("contrib_users", "token_version", "INTEGER DEFAULT 0"),
        ("contrib_user_progress", "skipped", "BOOLEAN DEFAULT FALSE"),
    ]
    dialect = engine.dialect.name
    with engine.begin() as conn:
        for table, col, typ in alters:
            if dialect == "postgresql":
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}"))
            elif dialect == "sqlite":
                cols = {
                    r[1]
                    for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                }
                if col not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))

        # Backfill roles from is_admin + known owner email
        if dialect == "postgresql":
            conn.execute(
                text(
                    f"""
                    UPDATE contrib_users
                    SET role = '{ROLE_CONTRIBUTOR}'
                    WHERE role IS NULL OR role = ''
                    """
                )
            )
            # Never hardcode emails — only promote accounts already flagged is_admin
            conn.execute(
                text(
                    f"""
                    UPDATE contrib_users
                    SET role = '{ROLE_OWNER}', is_admin = TRUE
                    WHERE is_admin = TRUE
                    """
                )
            )
            conn.execute(
                text(
                    f"""
                    UPDATE contrib_users
                    SET is_admin = (role = '{ROLE_OWNER}')
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE contrib_users
                    SET token_version = 0
                    WHERE token_version IS NULL
                    """
                )
            )
            # Helpful indexes for crowd queue + admin aggregates
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_contrib_user_progress_user_locale_skipped "
                    "ON contrib_user_progress (user_id, locale, skipped)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_contrib_submissions_user_status "
                    "ON contrib_submissions (user_id, status)"
                )
            )
            # Prior skips were stored as progress — mark them so they don't inflate done%
            conn.execute(
                text(
                    """
                    UPDATE contrib_user_progress AS p
                    SET skipped = TRUE
                    WHERE EXISTS (
                      SELECT 1 FROM contrib_audit_log a
                      WHERE a.action = 'skip'
                        AND a.entity_type = 'prompt'
                        AND a.entity_id = CAST(p.prompt_id AS TEXT)
                        AND a.actor_id = p.user_id
                    )
                    AND NOT EXISTS (
                      SELECT 1 FROM contrib_submissions s
                      WHERE s.user_id = p.user_id
                        AND s.prompt_id = p.prompt_id
                        AND s.target_locale = p.locale
                    )
                    """
                )
            )
        elif dialect == "sqlite":
            conn.execute(
                text(
                    f"UPDATE contrib_users SET role = '{ROLE_CONTRIBUTOR}' "
                    "WHERE role IS NULL OR role = ''"
                )
            )
            conn.execute(
                text(
                    f"UPDATE contrib_users SET role = '{ROLE_OWNER}', is_admin = 1 "
                    "WHERE is_admin = 1"
                )
            )
            conn.execute(
                text(
                    f"UPDATE contrib_users SET is_admin = CASE WHEN role = '{ROLE_OWNER}' THEN 1 ELSE 0 END"
                )
            )


def init_contrib_db() -> None:
    engine = get_contrib_engine()
    ContribBase.metadata.create_all(bind=engine)
    _ensure_columns(engine)


def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_contrib_engine(), autoflush=False, autocommit=False, future=True)


def get_contrib_session() -> Generator[Session, None, None]:
    factory = session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
