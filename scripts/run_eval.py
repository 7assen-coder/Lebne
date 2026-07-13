#!/usr/bin/env python3
"""Run regression eval suite against the in-process agent graph."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.graph import run_agent
from api.config import get_settings
from api.schemas import Intent
from api.security.acl import Role, scopes_for_roles
from api.security.auth import Principal
from wallet.db import init_db, reset_engine


async def _run_case(case: dict) -> dict:
    settings = get_settings()
    principal = Principal(
        user_id=case.get("user_id", "eval-user"),
        roles=(Role.END_USER.value,),
        scopes=frozenset(scopes_for_roles([Role.END_USER])),
    )
    result = await run_agent(
        principal=principal,
        session_id=case.get("id", "eval"),
        message=case["input"],
        history=[],
        confirmation_token=None,
        two_fa_token=None,
        settings=settings,
    )
    expected_intent = case.get("expected_intent")
    intent_ok = expected_intent is None or result.intent.value == expected_intent
    contains = case.get("expected_contains") or []
    contains_ok = all(c.lower() in result.reply.lower() for c in contains)
    requires_2fa_ok = True
    if "expected_requires_2fa" in case:
        requires_2fa_ok = bool(result.requires_2fa) == bool(case["expected_requires_2fa"])

    passed = intent_ok and contains_ok and requires_2fa_ok
    return {
        "id": case.get("id"),
        "passed": passed,
        "expected_intent": expected_intent,
        "got_intent": result.intent.value,
        "requires_2fa": result.requires_2fa,
        "reply_preview": result.reply[:160],
    }


async def _amain(suite: Path, out: Path) -> int:
    get_settings.cache_clear()
    reset_engine()
    init_db()
    cases = [json.loads(line) for line in suite.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = [await _run_case(c) for c in cases]
    passed = sum(1 for r in results if r["passed"])
    report = {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Eval {passed}/{len(results)} passed → {out}")
    # Guardrail/account cases are deterministic; FAQ/expense may need live LLM — don't fail CI hard on LLM stubs.
    critical = [r for r in results if r["id"] in {"ev-003", "ev-004", "ev-005"}]
    critical_fail = [r for r in critical if not r["passed"]]
    if critical_fail:
        print("Critical failures:", critical_fail)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=Path("eval/test_suite.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("eval/results/latest.json"))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_amain(args.suite, args.out)))


if __name__ == "__main__":
    main()
