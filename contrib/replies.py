"""Short safe assistant replies for exported training rows."""

from __future__ import annotations

SAFE_REPLIES: dict[str, dict[str, str]] = {
    "faq": {
        "en": "I can help with that. For exact Lebne fees or KYC steps, check the in-app preview or FAQ.",
        "fr": "Je peux vous aider. Pour les frais ou le KYC Lebne exacts, consultez l'aperçu ou la FAQ dans l'app.",
        "ar": "يمكنني المساعدة. لتفاصيل رسوم أو تحقق لبنة الدقيقة، راجع المعاينة أو الأسئلة الشائعة في التطبيق.",
        "hassaniya": "نقدر نعاونك. لتفاصيل لبنة الدقيقة شوف التطبيق.",
    },
    "account_action": {
        "en": "Account changes need login, confirmation, and strong verification in the Lebne app.",
        "fr": "Les actions compte exigent connexion, confirmation et vérification forte dans l'app Lebne.",
        "ar": "إجراءات الحساب تحتاج تسجيل دخول وتأكيداً وتحققاً قوياً في تطبيق لبنة.",
        "hassaniya": "تغيير الحساب يحتاج دخول وتأكيد قوي في تطبيق لبنة.",
    },
    "expense_extraction": {
        "en": '{"amount": null, "currency": "MRU", "merchant": null}',
        "fr": '{"amount": null, "currency": "MRU", "merchant": null}',
        "ar": '{"amount": null, "currency": "MRU", "merchant": null}',
        "hassaniya": '{"amount": null, "currency": "MRU", "merchant": null}',
    },
    "clarify": {
        "en": "Do you need help with expenses, a FAQ, or an account action?",
        "fr": "Besoin d'aide pour dépenses, FAQ, ou action compte ?",
        "ar": "هل تحتاج مساعدة في المصاريف أو سؤال شائع أو إجراء حساب؟",
        "hassaniya": "تبغي مساعدة في مصروف ولا سؤال ولا حساب؟",
    },
    "out_of_domain": {
        "en": "I only help with Lebne wallet topics (transfers, balance, KYC, expenses in MRU).",
        "fr": "Je n'aide que sur Lebne (transferts, solde, KYC, dépenses en MRU).",
        "ar": "أساعد فقط في مواضيع محفظة لبنة (تحويل، رصيد، تحقق، مصاريف بالأوقية).",
        "hassaniya": "نعاون غير في محفظة لبنة (تحويل، رصيد، مصروف).",
    },
}


def assistant_reply(intent: str, locale: str) -> str:
    by_intent = SAFE_REPLIES.get(intent) or SAFE_REPLIES["faq"]
    return by_intent.get(locale) or by_intent.get("en") or "OK."
