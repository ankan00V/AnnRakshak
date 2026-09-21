"""Languages for farmers across India.

English, Hindi and Marathi are authored by hand in the knowledge base (the
PS is Maharashtra's). The other eight languages Sarvam speaks — Bengali,
Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi, Odia — are machine
translated ONCE from the approved English with Sarvam-Translate, placeholders
protected, and saved to kb/i18n/<lang>.json: a reviewable, committed
translation memory (English source -> translation). Nothing is translated on
the request path; a string missing from memory shows in English.

Never machine translated: pesticide verdicts (app.engine.labelcheck), which
stay exactly as authored — English in the new languages until reviewed.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app.config import KB_DIR

# Odia ("od") is switched off for now: Bhashini, the voice provider, does not
# answer Odia speech requests (every attempt hung past 60 s), and a language the
# app cannot read aloud should not be offered. Its translations stay in
# kb/i18n/od.json and frontend/landing/src/locales/od.json; adding "od" back
# here and in frontend/landing/src/lib/i18n.ts restores it.
LANGS = ("en", "hi", "mr", "bn", "ta", "te", "kn", "ml", "gu", "pa")
AUTHORED = ("en", "hi", "mr")
MACHINE = tuple(x for x in LANGS if x not in AUTHORED)
NATIVE_NAMES = {
    "en": "English", "hi": "हिन्दी", "mr": "मराठी", "bn": "বাংলা", "ta": "தமிழ்", "te": "తెలుగు",
    "kn": "ಕನ್ನಡ", "ml": "മലയാളം", "gu": "ગુજરાતી", "pa": "ਪੰਜਾਬੀ", "od": "ଓଡ଼ିଆ",
}
ENGLISH_NAMES = {
    "en": "English", "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil", "te": "Telugu",
    "kn": "Kannada", "ml": "Malayalam", "gu": "Gujarati", "pa": "Punjabi", "od": "Odia",
}
MEMORY_DIR = KB_DIR / "i18n"
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
"""{crop}, and {dep:+.0f} with a format spec — both must survive translation untouched."""


def same_placeholders(source: str, translated: str) -> bool:
    return sorted(PLACEHOLDER.findall(source)) == sorted(PLACEHOLDER.findall(translated))


@lru_cache
def memory(lang: str) -> dict[str, str]:
    """English -> translation. An entry whose placeholders don't match the
    English is dropped (the English shows instead): a mangled {name} would
    otherwise break the sentence, or the request that formats it."""
    f = MEMORY_DIR / f"{lang}.json"
    if lang in AUTHORED or not f.exists():
        return {}
    strings = json.loads(f.read_text(encoding="utf-8")).get("strings", {})
    return {en: t for en, t in strings.items() if isinstance(t, str) and same_placeholders(en, t)}


def lookup(english: str, lang: str) -> str | None:
    return memory(lang).get(english) if english else None


@lru_cache
def reviewed(lang: str) -> frozenset[str]:
    """English lines a native speaker has approved or corrected for `lang`
    (review_translations.py --import)."""
    f = MEMORY_DIR / f"{lang}.json"
    if lang in AUTHORED or not f.exists():
        return frozenset()
    return frozenset(json.loads(f.read_text(encoding="utf-8")).get("reviewed") or [])


def lookup_reviewed(english: str, lang: str) -> str | None:
    """A translation only once a native speaker has approved it. For text where
    a mistranslation could hurt someone — a pesticide warning — an unchecked
    machine translation is worse than English, so until review this returns
    None and the caller shows the English."""
    return lookup(english, lang) if english in reviewed(lang) else None


# --------------------------------------------------------------------------
# Machine translation (offline job, not the request path)
# --------------------------------------------------------------------------

def protect(text: str) -> tuple[str, list[str]]:
    names = PLACEHOLDER.findall(text)
    out = text
    for i, n in enumerate(names):
        out = out.replace("{" + n + "}", f"<{i}>", 1)
    return out, names


def restore(text: str, names: list[str]) -> str | None:
    """Put the placeholders back; None if the translation lost or duplicated one."""
    for i, n in enumerate(names):
        if text.count(f"<{i}>") != 1:
            return None
        text = text.replace(f"<{i}>", "{" + n + "}")
    return text


def machine_translate(text: str, lang: str) -> str | None:
    from app import voice  # noqa: PLC0415  (Sarvam, key pool)

    if not text.strip() or not re.search(r"[A-Za-z]", text):
        return text  # numbers, units, symbols: nothing to translate
    safe, names = protect(text)
    try:
        out = voice.translate(safe, "en", lang)
    except Exception:  # noqa: BLE001  one failed string must not stop the batch
        return None
    out = tidy(text, out)
    return restore(out, names) if names else out


SENTENCE_END = re.compile(r"[.।॥|!?]+\s*$")


def tidy(source: str, out: str) -> str:
    """Translators end a lone word or label with a full stop (Bengali 'আজ।' for
    'today'); keep the source's own ending instead."""
    out = out.strip()
    if not SENTENCE_END.search(source.strip()):
        out = SENTENCE_END.sub("", out).rstrip()
    return out


def translate_many(strings: list[str], lang: str, workers: int = 6, progress=None) -> dict[str, str]:
    done: dict[str, str] = {}

    def one(s: str):
        return s, machine_translate(s, lang)

    with ThreadPoolExecutor(workers) as pool:
        for i, (src, out) in enumerate(pool.map(one, strings), 1):
            if out:
                done[src] = out
            if progress and i % 50 == 0:
                progress(i, len(strings))
    return done
