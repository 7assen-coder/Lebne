"""LangGraph orchestration for Lebne chat agent."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from agent.nodes.account import AccountActionsAgent
from agent.nodes.expense import ExpenseExtractionAgent
from agent.nodes.faq import FaqRagAgent
from agent.nodes.router import IntentRouter
from api.config import Settings, get_settings
from api.llm_client import LLMClient
from api.schemas import AccountActionType, ChatMessage, ChatResponse, Intent, Sensitivity
from api.security.acl import ACTION_REQUIRED_SCOPE, ACTION_SENSITIVITY
from api.security.audit import audit_logger
from api.security.auth import Principal
from api.security.chat_safety import filter_model_output, sanitize_user_text
from api.security.step_up import (
    issue_confirmation,
    peek_dev_2fa_code,
    verify_confirmation_token,
    verify_two_fa_token,
)
from guardrail.domain import DomainGuardrail


def _safe_reply(text: str) -> str:
    scrubbed, _ = filter_model_output(text)
    return scrubbed


class AgentState(TypedDict, total=False):
    principal: Principal
    session_id: str
    message: str
    safe_message: str
    history: list[ChatMessage]
    confirmation_token: str | None
    two_fa_token: str | None
    settings: Settings
    intent: Intent
    in_domain: bool
    guardrail_score: float
    prompt_redactions: int
    injection_flags: list[str]
    response: ChatResponse


GRAPH_NODES = ("sanitize", "guardrail", "router", "expense", "faq", "account", "end")


def _node_sanitize(state: AgentState) -> dict[str, Any]:
    safety = sanitize_user_text(state["message"])
    # Hard-block obvious exfiltration / jailbreak attempts before routing.
    dangerous = any("dump" in f.lower() or "jailbreak" in f.lower() or "ignore" in f.lower() for f in safety.injection_flags)
    out: dict[str, Any] = {
        "safe_message": safety.safe_text,
        "prompt_redactions": safety.redactions,
        "injection_flags": safety.injection_flags,
    }
    if dangerous:
        out["in_domain"] = False
        out["response"] = ChatResponse(
            session_id=state["session_id"],
            intent=Intent.OUT_OF_DOMAIN,
            reply=_safe_reply(
                "I can't help with that request. I only assist with Lebne wallet topics."
            ),
            metadata={"reason": "injection_blocked", "injection_flags": safety.injection_flags},
        )
    return out


async def _node_guardrail(state: AgentState) -> dict[str, Any]:
    if state.get("response") is not None:
        return {}
    settings = state["settings"]
    guardrail = DomainGuardrail(settings)
    decision = await guardrail.check(state["safe_message"])
    if not decision.in_domain:
        return {
            "in_domain": False,
            "guardrail_score": decision.score,
            "response": ChatResponse(
                session_id=state["session_id"],
                intent=Intent.OUT_OF_DOMAIN,
                reply=_safe_reply(decision.safe_reply),
                metadata={
                    "guardrail_score": decision.score,
                    "reason": decision.reason,
                    "prompt_redactions": state.get("prompt_redactions", 0),
                    "injection_flags": state.get("injection_flags", []),
                },
            ),
        }
    return {"in_domain": True, "guardrail_score": decision.score}


def _after_sanitize(state: AgentState) -> Literal["guardrail", "end"]:
    if state.get("response") is not None:
        return "end"
    return "guardrail"


async def _node_router(state: AgentState) -> dict[str, Any]:
    llm = LLMClient(state["settings"])
    router = IntentRouter(llm)
    intent = await router.route(state["safe_message"], state.get("history") or [])
    return {"intent": intent}


async def _node_expense(state: AgentState) -> dict[str, Any]:
    llm = LLMClient(state["settings"])
    expense = ExpenseExtractionAgent(llm)
    result = await expense.run(state["safe_message"], state.get("history") or [])
    return {
        "response": ChatResponse(
            session_id=state["session_id"],
            intent=Intent.EXPENSE_EXTRACTION,
            reply=_safe_reply(result["reply"]),
            metadata={
                **result.get("metadata", {}),
                "prompt_redactions": state.get("prompt_redactions", 0),
                "injection_flags": state.get("injection_flags", []),
            },
        )
    }


async def _node_faq(state: AgentState) -> dict[str, Any]:
    llm = LLMClient(state["settings"])
    faq = FaqRagAgent(llm, state["settings"])
    result = await faq.run(
        state["safe_message"],
        state.get("history") or [],
        user_id=state["principal"].user_id,
    )
    return {
        "response": ChatResponse(
            session_id=state["session_id"],
            intent=Intent.FAQ,
            reply=_safe_reply(result["reply"]),
            metadata={
                **result.get("metadata", {}),
                "prompt_redactions": state.get("prompt_redactions", 0),
                "injection_flags": state.get("injection_flags", []),
            },
        )
    }


async def _node_account(state: AgentState) -> dict[str, Any]:
    settings = state["settings"]
    principal = state["principal"]
    session_id = state["session_id"]
    account = AccountActionsAgent(settings)
    action = await account.detect_action(state["safe_message"])
    scope = ACTION_REQUIRED_SCOPE[action]

    if not principal.has_scope(scope):
        audit_logger.record(
            user_id=principal.user_id,
            session_id=session_id,
            action=action.value,
            outcome="denied_scope",
            principal_roles=list(principal.roles),
        )
        return {
            "response": ChatResponse(
                session_id=session_id,
                intent=Intent.ACCOUNT_ACTION,
                reply=_safe_reply("You are not allowed to perform this account action."),
                metadata={"action": action.value, "missing_scope": scope.value},
            )
        }

    sensitivity = ACTION_SENSITIVITY.get(action, Sensitivity.CONFIRMATION)
    confirmation_token = state.get("confirmation_token")
    two_fa_token = state.get("two_fa_token")

    if sensitivity in {Sensitivity.CONFIRMATION, Sensitivity.STRONG_2FA}:
        if not confirmation_token:
            challenge = issue_confirmation(
                user_id=principal.user_id,
                action=action,
                session_id=session_id,
                settings=settings,
            )
            audit_logger.record(
                user_id=principal.user_id,
                session_id=session_id,
                action=action.value,
                outcome="challenge_issued",
                principal_roles=list(principal.roles),
            )
            return {
                "response": ChatResponse(
                    session_id=session_id,
                    intent=Intent.ACCOUNT_ACTION,
                    reply=_safe_reply("Confirm this sensitive action to continue."),
                    requires_confirmation=True,
                    requires_2fa=challenge.two_fa_required,
                    confirmation_token=challenge.confirmation_token,
                    two_fa_challenge_id=challenge.two_fa_challenge_id,
                    dev_2fa_code=(
                        peek_dev_2fa_code(challenge.two_fa_challenge_id, settings)
                        if challenge.two_fa_challenge_id
                        else None
                    ),
                    metadata={"action": action.value},
                )
            }

        verify_confirmation_token(
            confirmation_token,
            user_id=principal.user_id,
            action=action,
            session_id=session_id,
            settings=settings,
        )

        if sensitivity == Sensitivity.STRONG_2FA:
            if not two_fa_token:
                return {
                    "response": ChatResponse(
                        session_id=session_id,
                        intent=Intent.ACCOUNT_ACTION,
                        reply=_safe_reply("2FA verification required before this action can run."),
                        requires_confirmation=False,
                        requires_2fa=True,
                        metadata={"action": action.value},
                    )
                }
            verify_two_fa_token(
                two_fa_token,
                user_id=principal.user_id,
                action=action,
                settings=settings,
            )

    result = await account.execute(action=action, user_id=principal.user_id, principal=principal)
    audit_logger.record(
        user_id=principal.user_id,
        session_id=session_id,
        action=action.value,
        outcome="executed",
        principal_roles=list(principal.roles),
    )
    return {
        "response": ChatResponse(
            session_id=session_id,
            intent=Intent.ACCOUNT_ACTION,
            reply=_safe_reply(result["reply"]),
            metadata=result.get("metadata", {}),
        )
    }


def _node_clarify(state: AgentState) -> dict[str, Any]:
    return {
        "response": ChatResponse(
            session_id=state["session_id"],
            intent=Intent.CLARIFY,
            reply=_safe_reply(
                "Pouvez-vous préciser votre demande ? / Could you clarify your request?"
            ),
        )
    }


def _after_guardrail(state: AgentState) -> Literal["router", "end"]:
    if state.get("response") is not None or state.get("in_domain") is False:
        return "end"
    return "router"


def _after_router(state: AgentState) -> Literal["expense", "faq", "account", "clarify"]:
    intent = state.get("intent")
    if intent == Intent.EXPENSE_EXTRACTION:
        return "expense"
    if intent == Intent.FAQ:
        return "faq"
    if intent == Intent.ACCOUNT_ACTION:
        return "account"
    return "clarify"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("sanitize", _node_sanitize)
    graph.add_node("guardrail", _node_guardrail)
    graph.add_node("router", _node_router)
    graph.add_node("expense", _node_expense)
    graph.add_node("faq", _node_faq)
    graph.add_node("account", _node_account)
    graph.add_node("clarify", _node_clarify)

    graph.set_entry_point("sanitize")
    graph.add_conditional_edges("sanitize", _after_sanitize, {"guardrail": "guardrail", "end": END})
    graph.add_conditional_edges("guardrail", _after_guardrail, {"router": "router", "end": END})
    graph.add_conditional_edges(
        "router",
        _after_router,
        {
            "expense": "expense",
            "faq": "faq",
            "account": "account",
            "clarify": "clarify",
        },
    )
    graph.add_edge("expense", END)
    graph.add_edge("faq", END)
    graph.add_edge("account", END)
    graph.add_edge("clarify", END)
    return graph.compile()


_COMPILED = None


def get_compiled_graph():
    global _COMPILED
    if _COMPILED is None:
        _COMPILED = build_graph()
    return _COMPILED


async def run_agent(
    *,
    principal: Principal,
    session_id: str,
    message: str,
    history: list[ChatMessage],
    confirmation_token: str | None,
    two_fa_token: str | None,
    settings: Settings | None = None,
) -> ChatResponse:
    settings = settings or get_settings()
    graph = get_compiled_graph()
    final: AgentState = await graph.ainvoke(
        {
            "principal": principal,
            "session_id": session_id,
            "message": message,
            "history": history,
            "confirmation_token": confirmation_token,
            "two_fa_token": two_fa_token,
            "settings": settings,
        }
    )
    response = final.get("response")
    if response is None:
        return ChatResponse(
            session_id=session_id,
            intent=Intent.CLARIFY,
            reply=_safe_reply("Something went wrong routing your request."),
        )
    return response
