"""JSON API for the Next.js crowdsource app — Postgres-backed.

Roles: owner / reviewer / contributor
- Owner: People + promote + unlimited review (approve exports immediately)
- Reviewer: Inbox only, 100 approve/decline per UTC day; 3 agreeing votes export
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, not_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from api.config import Settings, get_settings
from contrib.crowd_auth import (
    effective_role,
    get_crowd_user,
    mint_crowd_token,
    require_owner,
    require_reviewer_or_owner,
)
from contrib.db import get_contrib_session
from api.security.rate_limit import rate_limiter
from contrib.export_util import (
    LOCALES,
    append_approved_row,
    count_nonempty_lines,
    locale_path,
    row_from_submission,
    upsert_approved_row,
)
from contrib.media_util import MAX_AUDIO_BYTES, MEDIA_DIR, safe_audio_path
from contrib.models import (
    CONSENSUS_NEEDED,
    ROLE_CONTRIBUTOR,
    ROLE_OWNER,
    ROLE_REVIEWER,
    REVIEWER_DAILY_LIMIT,
    AuditLog,
    CrowdUser,
    PromptItem,
    ReviewVote,
    Submission,
    UserProgress,
)
from contrib.stt import transcribe_audio
from contrib.translate_view import VIEW_LOCALES, view_text
from wallet.passwords import hash_password, verify_password

TARGET_LOCALE = "hassaniya"
OPEN_STATUSES = ("pending", "awaiting_consensus")
router = APIRouter(prefix="/crowd/v1", tags=["crowd"])


def _client_ip(request: Request) -> str:
    return request.client.host if request and request.client else "unknown"


class RegisterBody(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email")
        return v


class LoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class SubmitBody(BaseModel):
    prompt_id: int
    text: str | None = Field(default=None, max_length=2000)
    answer: str | None = Field(default=None, max_length=4000)
    audio_path: str | None = Field(default=None, max_length=512)
    note: str | None = Field(default=None, max_length=300)
    question: str | None = None


class ReviewBody(BaseModel):
    submission_id: int
    action: Literal["approve", "reject"]
    text: str | None = Field(default=None, min_length=2, max_length=2000)
    answer: str | None = Field(default=None, max_length=4000)


class RoleBody(BaseModel):
    role: Literal["reviewer", "contributor"]


class ApprovedEditBody(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    answer: str | None = Field(default=None, max_length=4000)


def _user_out(user: CrowdUser) -> dict:
    role = effective_role(user)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": role,
        "isAdmin": role == ROLE_OWNER,
        "isReviewer": role in (ROLE_OWNER, ROLE_REVIEWER),
    }


def _progress(db: Session, user_id: int) -> dict:
    # Skips are excluded — only real Hassaniya contributions count
    done = db.scalar(
        select(func.count()).select_from(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.locale == TARGET_LOCALE,
            UserProgress.skipped.is_(False),
        )
    ) or 0
    total = db.scalar(select(func.count()).select_from(PromptItem)) or 0
    percent = 0.0 if total == 0 else round(done * 1000 / total) / 10
    return {"done": done, "total": total, "percent": percent}


def _prompt_payload(db: Session, prompt: PromptItem, view: str) -> dict:
    rendered = view_text(db, prompt, view)
    return {
        "id": prompt.id,
        "intent": prompt.intent,
        "sourceLocale": prompt.source_locale,
        "importId": prompt.import_id,
        "view": rendered["locale"],
        "text": rendered["text"],
    }


def _audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | int,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            detail_json=json.dumps(detail or {}, ensure_ascii=False),
        )
    )


def _utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _reviewer_actions_today(db: Session, actor_id: int) -> int:
    start = _utc_day_start()
    return (
        db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.actor_id == actor_id,
                AuditLog.action.in_(("approve", "decline")),
                AuditLog.created_at >= start,
            )
        )
        or 0
    )


def _enforce_daily_limit(db: Session, actor: CrowdUser) -> dict:
    role = effective_role(actor)
    used = _reviewer_actions_today(db, actor.id)
    limit = None if role == ROLE_OWNER else REVIEWER_DAILY_LIMIT
    remaining = None if limit is None else max(0, limit - used)
    if role == ROLE_REVIEWER and used >= REVIEWER_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Daily review limit reached ({REVIEWER_DAILY_LIMIT}/day)",
        )
    return {"used": used, "limit": limit, "remaining": remaining}


def _clear_votes(db: Session, submission_id: int) -> None:
    votes = db.scalars(select(ReviewVote).where(ReviewVote.submission_id == submission_id)).all()
    for v in votes:
        db.delete(v)


def _approvals_payload(db: Session, submission_id: int, text: str) -> dict:
    votes = db.scalars(
        select(ReviewVote)
        .options(joinedload(ReviewVote.reviewer))
        .where(
            ReviewVote.submission_id == submission_id,
            ReviewVote.action == "approve",
            ReviewVote.text_snapshot == text,
        )
    ).all()
    return {
        "count": len(votes),
        "needed": CONSENSUS_NEEDED,
        "voters": [
            {
                "id": v.reviewer.id if v.reviewer else None,
                "name": v.reviewer.name if v.reviewer else "?",
            }
            for v in votes
        ],
    }


def _vote_snapshots(db: Session, submission_id: int) -> list[dict]:
    votes = db.scalars(
        select(ReviewVote)
        .options(joinedload(ReviewVote.reviewer))
        .where(ReviewVote.submission_id == submission_id, ReviewVote.action == "approve")
    ).all()
    return [
        {
            "id": v.reviewer.id if v.reviewer else None,
            "name": v.reviewer.name if v.reviewer else "?",
            "email": v.reviewer.email if v.reviewer else "",
            "textSnapshot": v.text_snapshot,
        }
        for v in votes
    ]


def _acceptance_for(db: Session, sub: Submission) -> dict:
    """Who accepted this approved submission (owner export and/or consensus voters)."""
    voters = _vote_snapshots(db, sub.id)
    export_log = db.scalars(
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .where(
            AuditLog.entity_type == "submission",
            AuditLog.entity_id == str(sub.id),
            AuditLog.action.in_(("export", "edit")),
        )
        .order_by(AuditLog.created_at.desc())
    ).first()

    detail: dict = {}
    if export_log and export_log.detail_json:
        try:
            detail = json.loads(export_log.detail_json)
        except json.JSONDecodeError:
            detail = {}

    mode = detail.get("mode")
    if not mode and sub.reviewer and effective_role(sub.reviewer) == ROLE_OWNER:
        mode = "owner"
    if not mode:
        mode = "consensus" if (voters or detail.get("voters")) else "owner"

    stored_voters = detail.get("voters") or voters
    final = None
    if sub.reviewer:
        final = {
            "id": sub.reviewer.id,
            "name": sub.reviewer.name,
            "email": sub.reviewer.email,
            "role": effective_role(sub.reviewer),
        }
    elif export_log and export_log.actor:
        final = {
            "id": export_log.actor.id,
            "name": export_log.actor.name,
            "email": export_log.actor.email,
            "role": effective_role(export_log.actor),
        }

    return {
        "mode": mode,
        "finalAccepter": final,
        "voters": stored_voters,
        "exportedAt": (export_log.created_at.isoformat() if export_log and export_log.created_at else None),
        "reviewedAt": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
    }


def _export_submission(
    db: Session,
    sub: Submission,
    actor: CrowdUser,
    *,
    mode: str = "owner",
    voters: list[dict] | None = None,
    replace: bool = False,
) -> dict:
    row = row_from_submission(
        submission_id=sub.id,
        intent=sub.prompt.intent if sub.prompt else "faq",
        locale=sub.target_locale,
        text=sub.text,
        answer=sub.answer_text,
        contributor_id=sub.user_id,
    )
    # Attribution / audio stay in DB + audit — never in training JSONL
    try:
        if replace:
            upsert_approved_row(row)
        else:
            append_approved_row(row)
    except OSError:
        pass
    if not replace:
        _audit(
            db,
            actor_id=actor.id,
            action="export",
            entity_type="submission",
            entity_id=sub.id,
            detail={
                "locale": sub.target_locale,
                "mode": mode,
                "voters": voters or [],
                "accepter": {"id": actor.id, "name": actor.name, "email": actor.email},
                "text": sub.text,
                "answer": sub.answer_text,
            },
        )
    return row


def _undo_progress(db: Session, user_id: int | None, prompt_id: int) -> None:
    if not user_id:
        return
    row = db.scalar(
        select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.prompt_id == prompt_id,
            UserProgress.locale == TARGET_LOCALE,
        )
    )
    if row:
        db.delete(row)


@router.post("/auth/register")
def register(
    body: RegisterBody,
    request: Request,
    db: Annotated[Session, Depends(get_contrib_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    rate_limiter.check(
        f"crowd-auth:{_client_ip(request)}",
        settings,
        limit=settings.crowd_auth_rate_limit,
    )

    email = body.email.lower().strip()
    exists = db.scalar(select(CrowdUser).where(CrowdUser.email == email))
    if exists:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    bootstrap = (settings.admin_bootstrap_email or "").lower().strip()
    # Only bootstrap if no owner exists yet (one-time)
    owner_exists = db.scalar(
        select(func.count()).select_from(CrowdUser).where(CrowdUser.role == ROLE_OWNER)
    ) or 0
    is_owner = bool(bootstrap and email == bootstrap and owner_exists == 0)
    user = CrowdUser(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role=ROLE_OWNER if is_owner else ROLE_CONTRIBUTOR,
        is_admin=is_owner,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = mint_crowd_token(user, settings)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@router.post("/auth/login")
def login(
    body: LoginBody,
    request: Request,
    db: Annotated[Session, Depends(get_contrib_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    rate_limiter.check(
        f"crowd-auth:{_client_ip(request)}",
        settings,
        limit=settings.crowd_auth_rate_limit,
    )
    email = body.email.lower().strip()
    user = db.scalar(select(CrowdUser).where(CrowdUser.email == email))
    if not user or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    # Keep is_admin cache in sync with role
    role = effective_role(user)
    if user.role != role or user.is_admin != (role == ROLE_OWNER):
        user.role = role
        user.is_admin = role == ROLE_OWNER
        db.commit()
        db.refresh(user)
    token = mint_crowd_token(user, settings)
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


@router.get("/auth/me")
def me(user: Annotated[CrowdUser, Depends(get_crowd_user)]) -> dict:
    return {"user": _user_out(user)}


@router.get("/prompts/next")
def next_prompt(
    user: Annotated[CrowdUser, Depends(get_crowd_user)],
    db: Annotated[Session, Depends(get_contrib_session)],
    view: str = "en",
) -> dict:
    view = view.lower().strip()
    if view not in VIEW_LOCALES:
        view = "en"

    covered = select(UserProgress.prompt_id).where(
        UserProgress.user_id == user.id,
        UserProgress.locale == TARGET_LOCALE,
    )
    # ORDER BY random() LIMIT 1 — avoids COUNT + large OFFSET scans on ~45k rows
    prompt = db.scalars(
        select(PromptItem)
        .where(not_(PromptItem.id.in_(covered)))
        .order_by(func.random())
        .limit(1)
    ).first()

    return {
        "prompt": _prompt_payload(db, prompt, view) if prompt else None,
        "progress": _progress(db, user.id),
        "done": prompt is None,
        "targetLocale": TARGET_LOCALE,
        "viewLocales": list(VIEW_LOCALES),
    }


@router.get("/prompts/{prompt_id}/view")
def prompt_view(
    prompt_id: int,
    user: Annotated[CrowdUser, Depends(get_crowd_user)],
    db: Annotated[Session, Depends(get_contrib_session)],
    view: str = "en",
) -> dict:
    _ = user
    prompt = db.get(PromptItem, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    view = view.lower().strip()
    if view not in VIEW_LOCALES:
        raise HTTPException(status_code=400, detail="view must be en, fr, or ar")
    return {"prompt": _prompt_payload(db, prompt, view)}


@router.get("/progress")
def progress(
    user: Annotated[CrowdUser, Depends(get_crowd_user)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    return {"progress": _progress(db, user.id), "targetLocale": TARGET_LOCALE}


@router.post("/submissions")
def submit(
    body: SubmitBody,
    user: Annotated[CrowdUser, Depends(get_crowd_user)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    prompt = db.get(PromptItem, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    utterance = (body.text or body.question or "").strip()
    answer = (body.answer or "").strip() or None

    audio_path = safe_audio_path(body.audio_path)

    if len(utterance) < 2 and not audio_path:
        raise HTTPException(status_code=400, detail="Type Hassaniya or record voice")
    if len(utterance) < 2 and audio_path:
        utterance = "[voice]"

    def _mark_contributed() -> None:
        row = db.scalar(
            select(UserProgress).where(
                UserProgress.user_id == user.id,
                UserProgress.prompt_id == prompt.id,
                UserProgress.locale == TARGET_LOCALE,
            )
        )
        if row:
            row.skipped = False
        else:
            db.add(
                UserProgress(
                    user_id=user.id,
                    prompt_id=prompt.id,
                    locale=TARGET_LOCALE,
                    skipped=False,
                )
            )

    # Resolve progress race before inserting the submission (rollback would drop it)
    _mark_contributed()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        _mark_contributed()

    db.add(
        Submission(
            prompt_id=prompt.id,
            user_id=user.id,
            target_locale=TARGET_LOCALE,
            text=utterance,
            answer_text=answer,
            audio_path=audio_path,
            contributor_note=(body.note or "").strip() or None,
            status="pending",
        )
    )
    db.commit()
    return {"ok": True, "progress": _progress(db, user.id)}


class SkipBody(BaseModel):
    prompt_id: int


@router.post("/prompts/skip")
def skip_prompt(
    body: SkipBody,
    user: Annotated[CrowdUser, Depends(get_crowd_user)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    """Skip Hassaniya for this item — does NOT count toward progress; still leaves the queue."""
    prompt = db.get(PromptItem, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    existing = db.scalar(
        select(UserProgress).where(
            UserProgress.user_id == user.id,
            UserProgress.prompt_id == prompt.id,
            UserProgress.locale == TARGET_LOCALE,
        )
    )
    if existing:
        # Already contributed — do not turn a real contribution into a skip
        if not existing.skipped:
            return {"ok": True, "skipped": False, "progress": _progress(db, user.id)}
    else:
        db.add(
            UserProgress(
                user_id=user.id,
                prompt_id=prompt.id,
                locale=TARGET_LOCALE,
                skipped=True,
            )
        )
        _audit(
            db,
            actor_id=user.id,
            action="skip",
            entity_type="prompt",
            entity_id=prompt.id,
            detail={"locale": TARGET_LOCALE},
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another request already wrote progress — treat as success if still a skip/contrib row
        existing = db.scalar(
            select(UserProgress).where(
                UserProgress.user_id == user.id,
                UserProgress.prompt_id == prompt.id,
                UserProgress.locale == TARGET_LOCALE,
            )
        )
        if not existing:
            raise HTTPException(status_code=409, detail="Could not record skip") from None
        if not existing.skipped:
            return {"ok": True, "skipped": False, "progress": _progress(db, user.id)}
    return {"ok": True, "skipped": True, "progress": _progress(db, user.id)}


@router.post("/stt")
async def stt(
    request: Request,
    user: Annotated[CrowdUser, Depends(get_crowd_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    audio: UploadFile = File(...),
    field: str = Form(default="question"),
) -> dict:
    rate_limiter.check(
        f"crowd-stt:{user.id}:{_client_ip(request)}",
        settings,
        limit=settings.crowd_stt_rate_limit,
    )
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio.filename or "clip.webm").suffix or ".webm"
    if suffix.lower() not in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4"}:
        suffix = ".webm"
    dest = MEDIA_DIR / f"{uuid.uuid4().hex}{suffix}"
    content = await audio.read()
    if len(content) < 32:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio too large (max 8MB)")
    dest.write_bytes(content)

    transcript = ""
    stt_configured = bool(settings.openai_api_key or settings.whisper_api_key)
    if stt_configured:
        try:
            transcript = await transcribe_audio(dest, settings, language_hint="hassaniya")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail="STT failed") from exc

    rel = safe_audio_path(str(dest)) or f"media/contrib_audio/{dest.name}"
    return {
        "ok": True,
        "audio_path": rel,
        "audioPath": rel,
        "transcript": transcript,
        "field": field if field in ("question", "answer") else "question",
        "sttConfigured": stt_configured,
    }


@router.get("/admin/users")
def admin_users(
    actor: Annotated[CrowdUser, Depends(require_owner)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    _ = actor
    total = db.scalar(select(func.count()).select_from(PromptItem)) or 0
    users = db.scalars(select(CrowdUser).order_by(CrowdUser.created_at.asc())).all()

    done_map = {
        int(uid): int(n)
        for uid, n in db.execute(
            select(UserProgress.user_id, func.count())
            .where(
                UserProgress.locale == TARGET_LOCALE,
                UserProgress.skipped.is_(False),
            )
            .group_by(UserProgress.user_id)
        ).all()
    }
    status_map: dict[int, dict[str, int]] = {}
    for uid, status, n in db.execute(
        select(Submission.user_id, Submission.status, func.count())
        .where(Submission.user_id.is_not(None))
        .group_by(Submission.user_id, Submission.status)
    ).all():
        if uid is None:
            continue
        bucket = status_map.setdefault(int(uid), {"pending": 0, "approved": 0, "rejected": 0})
        count = int(n)
        if status in OPEN_STATUSES:
            bucket["pending"] += count
        elif status == "approved":
            bucket["approved"] = count
        elif status == "rejected":
            bucket["rejected"] = count

    out = []
    for u in users:
        role = effective_role(u)
        done = done_map.get(u.id, 0)
        subs = status_map.get(u.id, {"pending": 0, "approved": 0, "rejected": 0})
        percent = 0.0 if total == 0 else round(done * 1000 / total) / 10
        out.append(
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": role,
                "isAdmin": role == ROLE_OWNER,
                "isReviewer": role in (ROLE_OWNER, ROLE_REVIEWER),
                "progress": {"done": done, "total": total, "percent": percent},
                "submissions": {
                    "pending": subs["pending"],
                    "approved": subs["approved"],
                    "rejected": subs["rejected"],
                },
            }
        )
    return {"users": out}


@router.post("/admin/users/{user_id}/role")
def admin_set_role(
    user_id: int,
    body: RoleBody,
    owner: Annotated[CrowdUser, Depends(require_owner)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    target = db.get(CrowdUser, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == owner.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    new_role = body.role
    old_role = effective_role(target)

    if old_role == ROLE_OWNER:
        owners = (
            db.scalar(
                select(func.count()).select_from(CrowdUser).where(
                    or_(CrowdUser.role == ROLE_OWNER, CrowdUser.is_admin.is_(True))
                )
            )
            or 0
        )
        if owners <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last owner")

    target.role = new_role
    target.is_admin = False
    target.token_version = int(getattr(target, "token_version", 0) or 0) + 1
    _audit(
        db,
        actor_id=owner.id,
        action="promote" if new_role == ROLE_REVIEWER else "revoke",
        entity_type="user",
        entity_id=target.id,
        detail={"from": old_role, "to": new_role, "email": target.email},
    )
    db.commit()
    db.refresh(target)
    return {"ok": True, "user": _user_out(target)}


@router.get("/admin/pending")
def admin_pending(
    actor: Annotated[CrowdUser, Depends(require_reviewer_or_owner)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    items = db.scalars(
        select(Submission)
        .options(joinedload(Submission.prompt), joinedload(Submission.user))
        .where(
            Submission.status.in_(OPEN_STATUSES),
            or_(Submission.user_id.is_(None), Submission.user_id != actor.id),
        )
        .order_by(Submission.created_at.asc())
        .limit(80)
    ).unique().all()

    role = effective_role(actor)
    used = _reviewer_actions_today(db, actor.id)
    daily = {
        "used": used,
        "limit": None if role == ROLE_OWNER else REVIEWER_DAILY_LIMIT,
        "remaining": None if role == ROLE_OWNER else max(0, REVIEWER_DAILY_LIMIT - used),
    }

    return {
        "daily": daily,
        "consensusNeeded": CONSENSUS_NEEDED,
        "items": [
            {
                "id": str(s.id),
                "locale": s.target_locale,
                "text": s.text,
                "answer": s.answer_text,
                "audioPath": s.audio_path,
                "note": s.contributor_note,
                "status": s.status,
                "approvals": _approvals_payload(db, s.id, s.text),
                "user": {
                    "id": s.user.id if s.user else None,
                    "name": s.user.name if s.user else "unknown",
                    "email": s.user.email if s.user else "",
                },
                "prompt": {
                    "sourceText": s.prompt.source_text,
                    "sourceLocale": s.prompt.source_locale,
                    "intent": s.prompt.intent,
                    "importId": s.prompt.import_id,
                },
            }
            for s in items
            if s.prompt
        ],
    }


@router.post("/admin/review")
def admin_review(
    body: ReviewBody,
    actor: Annotated[CrowdUser, Depends(require_reviewer_or_owner)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    sub = db.scalars(
        select(Submission)
        .options(joinedload(Submission.prompt), joinedload(Submission.user))
        .where(Submission.id == body.submission_id)
    ).first()
    if not sub or not sub.prompt or sub.status not in OPEN_STATUSES:
        raise HTTPException(status_code=404, detail="Not found")
    if sub.user_id == actor.id:
        raise HTTPException(status_code=400, detail="Cannot review your own submission")

    daily = _enforce_daily_limit(db, actor)
    role = effective_role(actor)
    now = datetime.now(timezone.utc)

    if body.action == "reject":
        sub.status = "rejected"
        sub.reviewed_at = now
        sub.reviewed_by = actor.id
        _clear_votes(db, sub.id)
        _undo_progress(db, sub.user_id, sub.prompt_id)
        _audit(
            db,
            actor_id=actor.id,
            action="decline",
            entity_type="submission",
            entity_id=sub.id,
            detail={"role": role},
        )
        db.commit()
        return {"ok": True, "progressUndone": True, "exported": False, "daily": daily}

    text = (body.text or sub.text).strip()
    answer = (body.answer or sub.answer_text or "").strip()
    if len(text) < 2:
        raise HTTPException(status_code=400, detail="Empty text")

    # Owner: immediate export
    if role == ROLE_OWNER:
        sub.text = text
        if answer:
            sub.answer_text = answer
        sub.status = "approved"
        sub.reviewed_at = now
        sub.reviewed_by = actor.id
        prior_voters = _vote_snapshots(db, sub.id)
        _clear_votes(db, sub.id)
        _audit(
            db,
            actor_id=actor.id,
            action="approve",
            entity_type="submission",
            entity_id=sub.id,
            detail={"role": role, "mode": "owner"},
        )
        row = _export_submission(db, sub, actor, mode="owner", voters=prior_voters)
        db.commit()
        return {
            "ok": True,
            "exported": True,
            "status": "approved",
            "row": row,
            "daily": {
                "used": _reviewer_actions_today(db, actor.id),
                "limit": None,
                "remaining": None,
            },
            "approvals": {"count": CONSENSUS_NEEDED, "needed": CONSENSUS_NEEDED, "voters": []},
        }

    # Reviewer path: consensus
    # If text changed from current submission text, wipe all votes
    if text != sub.text.strip():
        _clear_votes(db, sub.id)
        sub.text = text
    if answer:
        sub.answer_text = answer

    existing = db.scalar(
        select(ReviewVote).where(
            ReviewVote.submission_id == sub.id,
            ReviewVote.reviewer_id == actor.id,
        )
    )
    if existing:
        # Editing own vote text: if snapshot changes, treat as text change for others
        if existing.text_snapshot != text:
            _clear_votes(db, sub.id)
            db.add(
                ReviewVote(
                    submission_id=sub.id,
                    reviewer_id=actor.id,
                    action="approve",
                    text_snapshot=text,
                )
            )
        else:
            existing.action = "approve"
            existing.text_snapshot = text
    else:
        # If any existing vote has different snapshot, reset others
        others = db.scalars(select(ReviewVote).where(ReviewVote.submission_id == sub.id)).all()
        if others and any(v.text_snapshot != text for v in others):
            _clear_votes(db, sub.id)
        db.add(
            ReviewVote(
                submission_id=sub.id,
                reviewer_id=actor.id,
                action="approve",
                text_snapshot=text,
            )
        )

    _audit(
        db,
        actor_id=actor.id,
        action="approve",
        entity_type="submission",
        entity_id=sub.id,
        detail={"role": role, "mode": "consensus_vote"},
    )
    db.flush()

    approvals = _approvals_payload(db, sub.id, text)
    exported = False
    row = None
    if approvals["count"] >= CONSENSUS_NEEDED:
        sub.status = "approved"
        sub.reviewed_at = now
        sub.reviewed_by = actor.id
        voters = _vote_snapshots(db, sub.id)
        row = _export_submission(db, sub, actor, mode="consensus", voters=voters)
        exported = True
    else:
        sub.status = "awaiting_consensus"

    db.commit()
    used = _reviewer_actions_today(db, actor.id)
    return {
        "ok": True,
        "exported": exported,
        "status": sub.status,
        "row": row,
        "approvals": approvals,
        "daily": {
            "used": used,
            "limit": REVIEWER_DAILY_LIMIT,
            "remaining": max(0, REVIEWER_DAILY_LIMIT - used),
        },
    }


@router.get("/admin/approved")
def admin_approved(
    owner: Annotated[CrowdUser, Depends(require_owner)],
    db: Annotated[Session, Depends(get_contrib_session)],
    q: str | None = None,
    limit: int = 80,
) -> dict:
    del owner  # auth gate only
    limit = max(1, min(limit, 200))
    stmt = (
        select(Submission)
        .options(
            joinedload(Submission.prompt),
            joinedload(Submission.user),
            joinedload(Submission.reviewer),
        )
        .where(Submission.status == "approved")
        .order_by(Submission.reviewed_at.desc().nulls_last(), Submission.id.desc())
        .limit(limit)
    )
    items = db.scalars(stmt).unique().all()
    needle = (q or "").strip().lower()
    out = []
    for s in items:
        if not s.prompt:
            continue
        if needle:
            blob = " ".join(
                [
                    s.text or "",
                    s.answer_text or "",
                    s.prompt.source_text or "",
                    s.user.name if s.user else "",
                    s.user.email if s.user else "",
                    s.reviewer.name if s.reviewer else "",
                ]
            ).lower()
            if needle not in blob:
                continue
        out.append(
            {
                "id": str(s.id),
                "locale": s.target_locale,
                "text": s.text,
                "answer": s.answer_text,
                "audioPath": s.audio_path,
                "status": s.status,
                "acceptance": _acceptance_for(db, s),
                "user": {
                    "id": s.user.id if s.user else None,
                    "name": s.user.name if s.user else "unknown",
                    "email": s.user.email if s.user else "",
                },
                "prompt": {
                    "sourceText": s.prompt.source_text,
                    "sourceLocale": s.prompt.source_locale,
                    "intent": s.prompt.intent,
                    "importId": s.prompt.import_id,
                },
            }
        )
    return {"items": out, "total": len(out)}


@router.post("/admin/approved/{submission_id}")
def admin_edit_approved(
    submission_id: int,
    body: ApprovedEditBody,
    owner: Annotated[CrowdUser, Depends(require_owner)],
    db: Annotated[Session, Depends(get_contrib_session)],
) -> dict:
    sub = db.scalars(
        select(Submission)
        .options(
            joinedload(Submission.prompt),
            joinedload(Submission.user),
            joinedload(Submission.reviewer),
        )
        .where(Submission.id == submission_id, Submission.status == "approved")
    ).first()
    if not sub or not sub.prompt:
        raise HTTPException(status_code=404, detail="Approved item not found")

    text = body.text.strip()
    answer = (body.answer if body.answer is not None else sub.answer_text or "").strip()
    if len(text) < 2:
        raise HTTPException(status_code=400, detail="Empty text")

    prev = {"text": sub.text, "answer": sub.answer_text}
    sub.text = text
    sub.answer_text = answer or None
    sub.reviewed_at = datetime.now(timezone.utc)
    sub.reviewed_by = owner.id

    acceptance = _acceptance_for(db, sub)
    voters = acceptance.get("voters") or []
    row = _export_submission(
        db,
        sub,
        owner,
        mode=acceptance.get("mode") or "owner",
        voters=voters if isinstance(voters, list) else [],
        replace=True,
    )
    _audit(
        db,
        actor_id=owner.id,
        action="edit",
        entity_type="submission",
        entity_id=sub.id,
        detail={"from": prev, "to": {"text": text, "answer": answer}},
    )
    db.commit()
    db.refresh(sub)
    return {
        "ok": True,
        "item": {
            "id": str(sub.id),
            "text": sub.text,
            "answer": sub.answer_text,
            "acceptance": _acceptance_for(db, sub),
            "row": row,
        },
    }


@router.get("/admin/exports")
def list_exports(owner: Annotated[CrowdUser, Depends(require_owner)]) -> dict:
    """Owner-only: list training JSONL files (not public HTTP)."""
    _ = owner
    out = []
    for locale in LOCALES:
        path = locale_path(locale)
        if path.is_file():
            out.append(
                {
                    "locale": locale,
                    "filename": path.name,
                    "bytes": path.stat().st_size,
                    "lines": count_nonempty_lines(path),
                }
            )
        else:
            out.append({"locale": locale, "filename": path.name, "bytes": 0, "lines": 0})
    return {"items": out}


@router.get("/admin/exports/{locale}")
def download_export(
    locale: str,
    owner: Annotated[CrowdUser, Depends(require_owner)],
) -> FileResponse:
    """Owner-only download of a training JSONL file."""
    _ = owner
    locale = locale.lower().strip()
    if locale not in LOCALES:
        raise HTTPException(status_code=400, detail="Invalid locale")
    path = locale_path(locale)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path,
        media_type="application/x-ndjson",
        filename=path.name,
    )


@router.get("/health")
def crowd_health(db: Annotated[Session, Depends(get_contrib_session)]) -> dict:
    total = db.scalar(select(func.count()).select_from(PromptItem)) or 0
    return {"status": "ok", "prompts": total, "targetLocale": TARGET_LOCALE}
