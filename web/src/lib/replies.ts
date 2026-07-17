const SAFE: Record<string, Record<string, string>> = {
  faq: {
    en: "I can help with that. Check the Lebne in-app FAQ for exact fees or KYC steps.",
    fr: "Je peux vous aider. Vérifiez la FAQ Lebne dans l'app pour les détails exacts.",
    ar: "يمكنني المساعدة. راجع أسئلة لبنة في التطبيق للتفاصيل الدقيقة.",
    hassaniya: "نقدر نعاونك. شوف تطبيق لبنة للتفاصيل.",
  },
  account_action: {
    en: "Account changes need login, confirmation, and strong verification in Lebne.",
    fr: "Les actions compte exigent connexion, confirmation et vérification forte.",
    ar: "إجراءات الحساب تحتاج دخولاً وتأكيداً وتحققاً قوياً.",
    hassaniya: "تغيير الحساب يحتاج دخول وتأكيد قوي.",
  },
  expense_extraction: {
    en: '{"amount": null, "currency": "MRU", "merchant": null}',
    fr: '{"amount": null, "currency": "MRU", "merchant": null}',
    ar: '{"amount": null, "currency": "MRU", "merchant": null}',
    hassaniya: '{"amount": null, "currency": "MRU", "merchant": null}',
  },
  clarify: {
    en: "Do you need expenses, FAQ, or an account action?",
    fr: "Dépenses, FAQ, ou action compte ?",
    ar: "مصاريف أم سؤال أم إجراء حساب؟",
    hassaniya: "مصروف ولا سؤال ولا حساب؟",
  },
  out_of_domain: {
    en: "I only help with Lebne wallet topics.",
    fr: "Je n'aide que sur le portefeuille Lebne.",
    ar: "أساعد فقط في محفظة لبنة.",
    hassaniya: "نعاون غير في محفظة لبنة.",
  },
};

export function assistantReply(intent: string, locale: string) {
  const by = SAFE[intent] || SAFE.faq;
  return by[locale] || by.en;
}
