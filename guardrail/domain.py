"""Domain guardrail via embedding similarity to in-domain seeds."""

from __future__ import annotations

from dataclasses import dataclass

from api.config import Settings
from rag.embeddings import EmbeddingProvider, get_embedder


@dataclass
class GuardrailDecision:
    in_domain: bool
    score: float
    reason: str
    safe_reply: str


IN_DOMAIN_SEEDS = [
    "wallet balance transfer fees Lebne",
    "solde frais transfert portefeuille",
    "رصيد تحويل محفظة لبنة",
    "expense spent merchant purchase MRU",
    "changer mot de passe numéro téléphone compte",
    "how do fees work FAQ support help",
    "أشتريت صرفت مصروف دكان",
    "what languages does Lebne support Arabic French English",
    "quelles langues supportées arabe français anglais",
    "KYC documents NNI passport open account Mauritania",
    "transaction history suspicious report OTP password security",
]


class DomainGuardrail:
    """Pre-LLM gate: max cosine similarity vs in-domain seeds."""

    def __init__(self, settings: Settings, embedder: EmbeddingProvider | None = None) -> None:
        self.settings = settings
        self.embedder = embedder or get_embedder()
        self._seed_vecs = self.embedder.embed_many(IN_DOMAIN_SEEDS)

    async def check(self, message: str) -> GuardrailDecision:
        if not self.settings.guardrail_enabled:
            return GuardrailDecision(True, 1.0, "disabled", "")

        msg_vec = self.embedder.embed(message)
        score = max(self.embedder.cosine(msg_vec, seed) for seed in self._seed_vecs)
        in_domain = score >= self.settings.guardrail_threshold
        return GuardrailDecision(
            in_domain=in_domain,
            score=float(score),
            reason="embedding_cosine_max",
            safe_reply=(
                "Je peux vous aider uniquement pour le portefeuille Lebne "
                "(dépenses, FAQ, compte). / I can only help with Lebne wallet topics."
            ),
        )
