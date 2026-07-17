#!/usr/bin/env python3
"""Import public banking intent datasets into Lebne training JSONL.

Sources:
  - PolyAI/banking77 (Hugging Face) — English
  - SinaLab/ArBanking77 (GitHub) — MSA Arabic only
  - abderrahmanskiredj/DarijaBanking (GitHub) — EN / FR / MSA only (drop Darija)

Writes: data/datasets/imported_banking.jsonl with reviewed=false.
Does not overwrite sample_train.jsonl.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "datasets" / "imported_banking.jsonl"

# Banking77 / ArBanking77-style labels → Lebne intents
ACCOUNT_ACTION_LABELS = {
    "activate_my_card",
    "change_pin",
    "edit_personal_details",
    "lost_or_stolen_card",
    "lost_or_stolen_phone",
    "passcode_forgotten",
    "pin_blocked",
    "terminate_account",
    "unable_to_verify_identity",
    "verify_my_identity",
    "verify_source_of_funds",
    "why_verify_identity",
    "get_physical_card",
    "order_physical_card",
    "getting_spare_card",
    "getting_virtual_card",
    "get_disposable_virtual_card",
    "card_linking",
}

CLARIFY_LABELS = {
    "general",
    "greeting",
    "greetings",
    "hello",
    "help",
    "other",
}

OUT_OF_DOMAIN_LABELS = {
    "out_of_domain",
    "ood",
    "non_banking",
}

SAFE_REPLIES = {
    "faq": {
        "en": "I can help with that banking question. For Lebne product specifics (fees, KYC, MRU), check the in-app FAQ or ask about Lebne directly.",
        "fr": "Je peux vous aider sur cette question bancaire. Pour les détails Lebne (frais, KYC, MRU), consultez la FAQ dans l'app ou posez une question Lebne.",
        "ar": "يمكنني المساعدة في هذا السؤال المصرفي. لتفاصيل منتج لبنة (الرسوم، التحقق، الأوقية) راجع الأسئلة الشائعة في التطبيق أو اسأل عن لبنة مباشرة.",
    },
    "account_action": {
        "en": "Account changes require authentication, confirmation, and strong verification. Please continue in the Lebne app when prompted.",
        "fr": "Les actions sur le compte exigent authentification, confirmation et vérification forte. Continuez dans l'application Lebne lorsque c'est demandé.",
        "ar": "إجراءات الحساب تتطلب مصادقة وتأكيداً وتحققاً قوياً. تابع في تطبيق لبنة عند الطلب.",
    },
    "clarify": {
        "en": "Could you clarify whether you need help with expenses, a FAQ, or an account action?",
        "fr": "Pouvez-vous préciser : dépenses, FAQ, ou action sur le compte ?",
        "ar": "هل يمكنك التوضيح: مصاريف، سؤال شائع، أم إجراء على الحساب؟",
    },
    "out_of_domain": {
        "en": "That looks outside Lebne wallet support. Ask about transfers, balance, KYC, or expenses in MRU.",
        "fr": "Cela semble hors du périmètre Lebne. Demandez plutôt transferts, solde, KYC ou dépenses en MRU.",
        "ar": "يبدو هذا خارج نطاق دعم محفظة لبنة. اسأل عن التحويلات أو الرصيد أو التحقق أو المصاريف بالأوقية.",
    },
}

BANKING77_TRAIN_CSV = (
    "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv"
)
BANKING77_TEST_CSV = (
    "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv"
)
ARBANKING_MSA_FILES = [
    "https://raw.githubusercontent.com/SinaLab/ArBanking77/main/data/Banking77_Arabized_MSA_PAL_train.csv",
    "https://raw.githubusercontent.com/SinaLab/ArBanking77/main/data/Banking77_Arabized_MSA_PAL_val.csv",
    "https://raw.githubusercontent.com/SinaLab/ArBanking77/main/data/Banking77_Arabized_MSA_test.csv",
]
ARBANKING_INTENTS_CSV = (
    "https://raw.githubusercontent.com/SinaLab/ArBanking77/main/data/Banking77_intents.csv"
)
DARIJA_HF_DATASET = "AbderrahmanSkiredj1/DarijaBanking"


def _normalize_label(label: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", label.strip().lower()).strip("_")


def map_intent(label: str) -> str | None:
    key = _normalize_label(label)
    if key in OUT_OF_DOMAIN_LABELS:
        return "out_of_domain"
    if key in CLARIFY_LABELS:
        return "clarify"
    if key in ACCOUNT_ACTION_LABELS:
        return "account_action"
    if not key:
        return None
    # Default: informational banking question
    return "faq"


def assign_split(index: int, total: int) -> str:
    """Deterministic ~80/10/10 split by position."""
    if total <= 0:
        return "train"
    ratio = index / total
    if ratio < 0.8:
        return "train"
    if ratio < 0.9:
        return "val"
    return "test"


def _http_get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "LebneImporter/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _load_csv_text_label(url: str, text_key: str, label_key: str) -> list[tuple[str, str]]:
    raw = _http_get(url).decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    pairs: list[tuple[str, str]] = []
    for row in reader:
        text = (row.get(text_key) or "").strip()
        label = (row.get(label_key) or "").strip()
        if text and label:
            pairs.append((text, label))
    return pairs


def load_banking77(max_per_split: int | None) -> list[dict]:
    """Banking77 EN from PolyAI GitHub CSVs (HF script datasets are unsupported)."""
    print("Loading Banking77 (EN) from PolyAI GitHub CSVs…")
    rows: list[dict] = []
    for url in (BANKING77_TRAIN_CSV, BANKING77_TEST_CSV):
        try:
            pairs = _load_csv_text_label(url, "text", "category")
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"  warn: failed {url}: {exc}")
            continue
        if max_per_split is not None:
            pairs = pairs[:max_per_split]
        for text, label in pairs:
            intent = map_intent(label)
            if intent is None:
                continue
            rows.append(
                {
                    "source": "banking77",
                    "locale": "en",
                    "intent": intent,
                    "user": text,
                    "label": label,
                }
            )
        print(f"  loaded {len(pairs)} from {url.rsplit('/', 1)[-1]}")
    print(f"  banking77 rows={len(rows)}")
    return rows


def _load_ar_to_en_labels() -> dict[str, str]:
    try:
        raw = _http_get(ARBANKING_INTENTS_CSV).decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"  warn: intents map unavailable: {exc}")
        return {}
    mapping: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(raw))
    for row in reader:
        en = (row.get("label_en") or "").strip().strip('"')
        ar = (row.get("label_ar") or "").strip().strip('"')
        if en and ar:
            mapping[ar] = en
            mapping[_normalize_label(en).replace("_", " ")] = en
    return mapping


def load_arbanking77(max_rows: int | None) -> list[dict]:
    print("Loading ArBanking77 (MSA files only) from GitHub…")
    ar_to_en = _load_ar_to_en_labels()
    rows: list[dict] = []
    seen: set[str] = set()
    for url in ARBANKING_MSA_FILES:
        try:
            pairs = _load_csv_text_label(url, "text", "label")
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            print(f"  warn: failed {url}: {exc}")
            continue
        kept = 0
        for text, label_ar in pairs:
            key = text.strip()
            if not key or key in seen:
                continue
            label_en = ar_to_en.get(label_ar) or ar_to_en.get(label_ar.strip('"')) or label_ar
            intent = map_intent(label_en)
            if intent is None:
                continue
            seen.add(key)
            rows.append(
                {
                    "source": "arbanking77",
                    "locale": "ar",
                    "intent": intent,
                    "user": text,
                    "label": label_en,
                }
            )
            kept += 1
            if max_rows is not None and len(rows) >= max_rows:
                print(f"  arbanking77 rows={len(rows)} (capped)")
                return rows
        print(f"  kept {kept} from {url.rsplit('/', 1)[-1]}")
    print(f"  arbanking77 rows={len(rows)}")
    return rows


_DARIJA_MARKERS = re.compile(
    r"(كشوفات|ديالي|بزاف|واش|اشنو|فين|بغيت|ماشي|دابا|كيفاش|عافاك|المرجو|كانتفرج|"
    r"\b(wash|bghit|fin|ach|chno|bzaf|daba|kifash)\b)",
    re.I,
)
_LATIN_RATIO = re.compile(r"[A-Za-z]")
_ARABIC_CHARS = re.compile(r"[\u0600-\u06FF]")
_FRENCH_HINTS = re.compile(
    r"[àâäéèêëïîôùûüçœæ]|(\b(je|vous|mon|ma|mes|carte|compte|virement|pouvez|comment|pourquoi)\b)",
    re.I,
)


def _resolve_darija_locale(language: str | None, text: str) -> str | None:
    """Map HF language tags to ar|fr|en; drop Darija."""
    lang = (language or "").strip().lower()
    text = text.strip()
    if not text:
        return None

    if lang in {"ar", "msa", "modern_standard_arabic"}:
        return "ar"

    if lang in {"darija", "ary", "moroccan"}:
        return None

    if lang in {"arabic or darija", "arabic/darija", "ar_or_darija"}:
        # Latinized Darija or dialect markers → drop; keep likely MSA Arabic
        latin = len(_LATIN_RATIO.findall(text))
        arabic = len(_ARABIC_CHARS.findall(text))
        if latin > arabic:
            return None
        if _DARIJA_MARKERS.search(text):
            return None
        if arabic == 0:
            return None
        return "ar"

    if lang in {"french or english", "french/english", "fr_or_en", "en_or_fr"}:
        if _FRENCH_HINTS.search(text):
            return "fr"
        return "en"

    if lang in {"fr", "fra", "french"}:
        return "fr"
    if lang in {"en", "eng", "english"}:
        return "en"
    if lang in {"arabic", "ara"}:
        if _DARIJA_MARKERS.search(text):
            return None
        return "ar"
    return None


def load_darija_banking(max_rows: int | None) -> list[dict]:
    """DarijaBanking from HF — keep EN / FR / MSA only; drop Darija rows."""
    print(f"Loading DarijaBanking (EN/FR/MSA) from Hugging Face ({DARIJA_HF_DATASET})…")
    try:
        from datasets import load_dataset
    except ImportError:
        print("  warn: `datasets` not installed; skip DarijaBanking (pip install datasets)")
        return []

    try:
        ds = load_dataset(DARIJA_HF_DATASET)
    except Exception as exc:  # noqa: BLE001 — surface HF/network errors
        print(f"  warn: DarijaBanking unavailable: {exc}")
        return []

    sample_split = next(iter(ds.keys()))
    sample = ds[sample_split][0] if len(ds[sample_split]) else {}
    print(f"  columns={list(sample.keys())}")

    rows: list[dict] = []
    seen: set[str] = set()
    dropped_darija = 0
    for _split_name, subset in ds.items():
        for item in subset:
            if max_rows is not None and len(rows) >= max_rows:
                break
            text = str(item.get("text") or "").strip()
            label = str(item.get("label") or item.get("intent") or "").strip()
            language = str(item.get("language") or item.get("lang") or "").strip()
            if not text or not label:
                continue
            loc = _resolve_darija_locale(language, text)
            if loc is None:
                dropped_darija += 1
                continue
            key = f"{loc}:{text.lower()}"
            if key in seen:
                continue
            intent = map_intent(label)
            if intent is None:
                continue
            seen.add(key)
            rows.append(
                {
                    "source": "darijabanking",
                    "locale": loc,
                    "intent": intent,
                    "user": text,
                    "label": label,
                }
            )
        if max_rows is not None and len(rows) >= max_rows:
            break

    print(f"  darijabanking rows={len(rows)} dropped_non_msa_or_darija≈{dropped_darija}")
    return rows


def dedupe_raw(raw: list[dict]) -> list[dict]:
    """Drop duplicate user texts per locale (keep first source)."""
    seen: set[str] = set()
    out: list[dict] = []
    for item in raw:
        key = f"{item['locale']}\0{item['user'].strip().lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    print(f"dedupe: {len(raw)} → {len(out)} (removed {len(raw) - len(out)})")
    return out


def to_lebne_rows(raw: list[dict], seed: int) -> list[dict]:
    rng = random.Random(seed)
    shuffled = list(raw)
    rng.shuffle(shuffled)
    total = len(shuffled)
    out: list[dict] = []
    for i, item in enumerate(shuffled):
        locale = item["locale"]
        intent = item["intent"]
        reply = SAFE_REPLIES[intent][locale]
        src = item["source"]
        out.append(
            {
                "id": f"{src}-{locale}-{i:05d}",
                "intent": intent,
                "locale": locale,
                "reviewed": False,
                "split": assign_split(i, total),
                "messages": [
                    {"role": "user", "content": item["user"]},
                    {"role": "assistant", "content": reply},
                ],
                "meta": {"source_label": item.get("label"), "source": src},
            }
        )
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            # Strip meta from training shape? Keep meta for audit — validate only checks required keys.
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_stats(rows: list[dict]) -> None:
    by_locale = Counter(r["locale"] for r in rows)
    by_intent = Counter(r["intent"] for r in rows)
    by_split = Counter(r["split"] for r in rows)
    by_source = Counter((r.get("meta") or {}).get("source", "?") for r in rows)
    print("counts:")
    print(f"  total={len(rows)}")
    print(f"  locale={dict(by_locale)}")
    print(f"  intent={dict(by_intent)}")
    print(f"  split={dict(by_split)}")
    print(f"  source={dict(by_source)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import public banking datasets → Lebne JSONL")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--max-per-source",
        type=int,
        default=None,
        help="Optional cap per source (useful for smoke runs)",
    )
    parser.add_argument("--skip-banking77", action="store_true")
    parser.add_argument("--skip-arbanking", action="store_true")
    parser.add_argument("--skip-darija", action="store_true")
    args = parser.parse_args()

    raw: list[dict] = []
    if not args.skip_banking77:
        raw.extend(load_banking77(args.max_per_source))
    if not args.skip_arbanking:
        raw.extend(load_arbanking77(args.max_per_source))
    if not args.skip_darija:
        raw.extend(load_darija_banking(args.max_per_source))

    if not raw:
        raise SystemExit("No rows imported — check network / dataset availability")

    raw = dedupe_raw(raw)
    rows = to_lebne_rows(raw, seed=args.seed)
    write_jsonl(args.out, rows)
    print_stats(rows)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
