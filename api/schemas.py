"""Shared request/response and domain models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Intent(str, Enum):
    EXPENSE_EXTRACTION = "expense_extraction"
    FAQ = "faq"
    ACCOUNT_ACTION = "account_action"
    OUT_OF_DOMAIN = "out_of_domain"
    CLARIFY = "clarify"


class AccountActionType(str, Enum):
    """Sensitive actions must never execute without confirmation / 2FA."""

    GET_BALANCE = "get_balance"
    LIST_TRANSACTIONS = "list_transactions"
    CHANGE_PASSWORD = "change_password"
    CHANGE_PHONE = "change_phone"
    UPDATE_PROFILE = "update_profile"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    CONFIRMATION = "confirmation"
    STRONG_2FA = "strong_2fa"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    """user_id is NEVER accepted from the client — it comes from the JWT principal."""

    session_id: str
    message: str
    locale: str | None = Field(default=None, description="ar | fr | en")
    confirmation_token: str | None = None
    two_fa_token: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    intent: Intent
    reply: str
    requires_confirmation: bool = False
    requires_2fa: bool = False
    confirmation_token: str | None = None
    two_fa_challenge_id: str | None = None
    # Dev-only helper; always null in production.
    dev_2fa_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExpenseDraft(BaseModel):
    amount: float | None = None
    currency: str | None = "MRU"
    merchant: str | None = None
    category: str | None = None
    date: str | None = None
    raw_text: str | None = None


class DevTokenRequest(BaseModel):
    user_id: str = "user-demo"
    roles: list[str] = Field(default_factory=lambda: ["end_user"])


class LoginRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=8)


class RegisterRequest(BaseModel):
    user_id: str
    password: str = Field(min_length=8)
    display_name: str = "Lebne User"


class ConfirmChallengeRequest(BaseModel):
    action: AccountActionType
    session_id: str


class TwoFAVerifyRequest(BaseModel):
    challenge_id: str
    code: str
    action: AccountActionType
