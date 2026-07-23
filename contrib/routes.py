"""Legacy HTML contribute + cookie admin (disabled by default).

Prefer Next.js + /crowd/v1. Set LEBNE_CONTRIB_LEGACY_ENABLED=true only for local legacy UI.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session, joinedload

from api.config import Settings, get_settings
from contrib.db import get_contrib_session
from contrib.export_util import append_approved_row, row_from_submission
from contrib.media_util import MAX_AUDIO_BYTES, MEDIA_DIR, safe_audio_path
from contrib.models import PromptItem, Submission
from contrib.stt import transcribe_audio

TARGET_LOCALES = ("en", "fr", "ar", "hassaniya")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_DEFAULT_ADMIN_PASSWORD = "CHANGE_ME_CONTRIB_ADMIN"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(tags=["contrib"])


def _require_legacy(settings: Settings = Depends(get_settings)) -> None:
    if not settings.contrib_legacy_enabled:
        raise HTTPException(
            status_code=410,
            detail="Legacy /contrib is disabled. Use the Next.js app and /crowd/v1.",
        )


def _serializer(settings: Settings) -> URLSafeSerializer:
    secret = settings.contrib_admin_password
    if not secret or secret == _DEFAULT_ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Legacy admin password not configured securely")
    return URLSafeSerializer(secret, salt="lebne-contrib-admin")


def _admin_ok(request: Request, settings: Settings) -> bool:
    cookie = request.cookies.get("lebne_contrib_admin")
    if not cookie:
        return False
    try:
        data = _serializer(settings).loads(cookie)
        return data.get("role") == "admin"
    except BadSignature:
        return False


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    if not _admin_ok(request, settings):
        raise HTTPException(status_code=401, detail="Admin login required")


def _pick_random_prompt(db: Session, locale: str) -> PromptItem | None:
    """Prefer prompts with no pending/approved rewrite for this locale."""
    covered = (
        select(Submission.prompt_id)
        .where(
            Submission.target_locale == locale,
            Submission.status.in_(("pending", "approved")),
        )
        .scalar_subquery()
    )
    uncovered = db.scalars(
        select(PromptItem)
        .where(not_(PromptItem.id.in_(covered)))
        .order_by(func.random())
        .limit(1)
    ).first()
    if uncovered:
        return uncovered
    return db.scalars(select(PromptItem).order_by(func.random()).limit(1)).first()


@router.get("/contrib", response_class=HTMLResponse)
@router.get("/contrib/", response_class=HTMLResponse)
async def contribute_page(
    request: Request,
    locale: str = "fr",
    thanks: int = 0,
    db: Session = Depends(get_contrib_session),
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_legacy),
) -> HTMLResponse:
    locale = locale if locale in TARGET_LOCALES else "fr"
    prompt = _pick_random_prompt(db, locale)
    pending = db.scalar(select(func.count()).select_from(Submission).where(Submission.status == "pending")) or 0
    approved = db.scalar(select(func.count()).select_from(Submission).where(Submission.status == "approved")) or 0
    total = db.scalar(select(func.count()).select_from(PromptItem)) or 0
    return templates.TemplateResponse(
        request,
        "contribute.html",
        {
            "prompt": prompt,
            "locale": locale,
            "locales": TARGET_LOCALES,
            "thanks": bool(thanks),
            "stats": {"pending": pending, "approved": approved, "prompts": total},
            "stt_configured": bool(settings.openai_api_key or settings.whisper_api_key),
        },
    )


@router.post("/contrib/submit")
async def submit_rewrite(
    request: Request,
    prompt_id: int = Form(...),
    target_locale: str = Form(...),
    text: str = Form(...),
    contributor_note: str = Form(""),
    db: Session = Depends(get_contrib_session),
    _: None = Depends(_require_legacy),
) -> RedirectResponse:
    target_locale = target_locale.strip().lower()
    if target_locale not in TARGET_LOCALES:
        raise HTTPException(status_code=400, detail="Invalid locale")
    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        raise HTTPException(status_code=400, detail="Write a real Mauritanian rewrite first")
    prompt = db.get(PromptItem, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    form = await request.form()
    raw_audio = form.get("audio_path")
    audio_path = safe_audio_path(raw_audio if isinstance(raw_audio, str) else None)

    sub = Submission(
        prompt_id=prompt_id,
        target_locale=target_locale,
        text=cleaned,
        audio_path=audio_path,
        status="pending",
        contributor_note=(contributor_note or "").strip() or None,
    )
    db.add(sub)
    db.commit()
    return RedirectResponse(url=f"/contrib/?locale={target_locale}&thanks=1", status_code=303)


@router.post("/contrib/stt")
async def stt_draft(
    target_locale: str = Form("fr"),
    audio: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_legacy),
) -> JSONResponse:
    if target_locale not in TARGET_LOCALES:
        raise HTTPException(status_code=400, detail="Invalid locale")
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio.filename or "clip.webm").suffix or ".webm"
    dest = MEDIA_DIR / f"{uuid.uuid4().hex}{suffix}"
    content = await audio.read()
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio too large (max 8MB)")
    dest.write_bytes(content)
    try:
        transcript = await transcribe_audio(dest, settings, language_hint=target_locale)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"STT failed: {exc}") from exc
    return JSONResponse(
        {
            "text": transcript,
            "audio_path": str(dest),
            "note": "Draft only — edit before submit. Admin must approve.",
        }
    )


@router.get("/admin/contrib/login", response_model=None)
async def admin_login_page(
    request: Request,
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_legacy),
):
    if _admin_ok(request, settings):
        return RedirectResponse(url="/admin/contrib", status_code=303)
    return templates.TemplateResponse(request, "admin_login.html", {"error": None})


@router.post("/admin/contrib/login", response_model=None)
async def admin_login(
    request: Request,
    password: str = Form(...),
    settings: Settings = Depends(get_settings),
    _: None = Depends(_require_legacy),
):
    expected = settings.contrib_admin_password
    if (
        not expected
        or expected == _DEFAULT_ADMIN_PASSWORD
        or not secrets.compare_digest(password, expected)
    ):
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {"error": "Invalid password"},
            status_code=401,
        )
    token = _serializer(settings).dumps({"role": "admin"})
    resp = RedirectResponse(url="/admin/contrib", status_code=303)
    resp.set_cookie(
        "lebne_contrib_admin",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
        max_age=60 * 60 * 12,
    )
    return resp


@router.post("/admin/contrib/logout")
async def admin_logout(_: None = Depends(_require_legacy)) -> RedirectResponse:
    resp = RedirectResponse(url="/admin/contrib/login", status_code=303)
    resp.delete_cookie("lebne_contrib_admin")
    return resp


@router.get("/admin/contrib", response_model=None)
async def admin_queue(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_contrib_session),
    _: None = Depends(_require_legacy),
):
    if not _admin_ok(request, settings):
        return RedirectResponse(url="/admin/contrib/login", status_code=303)
    items = db.scalars(
        select(Submission)
        .options(joinedload(Submission.prompt))
        .where(Submission.status == "pending")
        .order_by(Submission.created_at.asc())
        .limit(50)
    ).unique().all()
    return templates.TemplateResponse(
        request,
        "admin_queue.html",
        {"items": items, "locales": TARGET_LOCALES},
    )


@router.post("/admin/contrib/{submission_id}/approve")
async def admin_approve(
    submission_id: int,
    request: Request,
    text: str = Form(...),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_contrib_session),
    __: None = Depends(_require_legacy),
    _: None = Depends(require_admin),
) -> RedirectResponse:
    _ = request
    sub = db.scalars(
        select(Submission).options(joinedload(Submission.prompt)).where(Submission.id == submission_id)
    ).first()
    if not sub or not sub.prompt:
        raise HTTPException(status_code=404, detail="Not found")
    cleaned = text.strip()
    if len(cleaned) < 2:
        raise HTTPException(status_code=400, detail="Empty text")
    sub.text = cleaned
    sub.status = "approved"
    sub.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    row = row_from_submission(
        submission_id=sub.id,
        intent=sub.prompt.intent,
        locale=sub.target_locale,
        text=sub.text,
        source_text=sub.prompt.source_text if sub.prompt else None,
        source_locale=sub.prompt.source_locale if sub.prompt else None,
    )
    append_approved_row(row)
    return RedirectResponse(url="/admin/contrib", status_code=303)


@router.post("/admin/contrib/{submission_id}/reject")
async def admin_reject(
    submission_id: int,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_contrib_session),
    __: None = Depends(_require_legacy),
    _: None = Depends(require_admin),
) -> RedirectResponse:
    _ = settings
    sub = db.get(Submission, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    sub.status = "rejected"
    sub.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(url="/admin/contrib", status_code=303)
