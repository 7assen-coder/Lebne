#!/usr/bin/env python3
"""Smoke-test /v1/chat without printing secrets."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def _post(path: str, body: dict, token: str | None = None) -> tuple[int, dict | str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def main() -> int:
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=10) as resp:
            print("health", resp.status, resp.read().decode()[:120])
    except Exception as exc:
        print("API not reachable:", exc)
        return 1

    # Prefer local register (hybrid) so we don't shell-print IdP tokens.
    code, reg = _post(
        "/v1/auth/register",
        {"user_id": "smoke-user", "password": "SmokePass123!", "display_name": "Smoke"},
    )
    if code >= 400:
        code, reg = _post(
            "/v1/auth/login",
            {"user_id": "smoke-user", "password": "SmokePass123!"},
        )
    if code >= 400 or not isinstance(reg, dict) or "access_token" not in reg:
        print("auth failed", code, reg)
        return 1

    token = reg["access_token"]
    code, chat = _post(
        "/v1/chat",
        {
            "session_id": "smoke-1",
            "message": "What languages does Lebne support?",
            "locale": "en",
        },
        token=token,
    )
    if code >= 400:
        print("chat failed", code, chat)
        return 1
    assert isinstance(chat, dict)
    print("intent=", chat.get("intent"))
    print("reply=", (chat.get("reply") or "")[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
