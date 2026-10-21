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

def marker(i: int) -> str:
    """What a placeholder is replaced with while a translator has the sentence.

    It was `<0>`, which reads as punctuation: the models delete it, or turn it
    into a bare `0`. Measured over the five strings that kept failing, `<0>`
    survived none of four and `XX0XX` survived all four — a run of capitals is
    a word to a translator, and words come back. The difference is not
    cosmetic: "near <0>°C, frost can form" came back as "near 0°C", which is a
    frost warning with the wrong number in it."""
    return f"XX{i}XX"


DASH = "\u2014"
"""Stands in the name list for a spaced em-dash, which is protected like a
placeholder rather than repaired afterwards.

Repairing afterwards does not work: the translators flatten " — " to a hyphen
welded between two words, and so do compound words, so there is no way to tell
"বেগুনি-দাগযুক্ত" (purple-stained, correct) from "না-অতিরিক্ত" (a lost dash)
by looking at the output. A first attempt guessed, and turned the compound into
an em-dash while leaving the real one glued. A marker cannot guess: it comes
back where the translator put it, or it does not come back and the line stays
in English."""


def protect(text: str) -> tuple[str, list[str]]:
    names = PLACEHOLDER.findall(text)
    out = text
    for i, n in enumerate(names):
        out = out.replace("{" + n + "}", marker(i), 1)
    # The dash itself, not the spaces around it, so the translator still sees
    # two separate words with something between them.
    for _ in range(text.count(DASH)):
        names.append(DASH)
        out = out.replace(DASH, marker(len(names) - 1), 1)
    return out, names


def restore(text: str, names: list[str]) -> str | None:
    """Put the placeholders back; None if the translation lost or duplicated one.

    Both marker shapes are accepted: the memory holds eight thousand strings
    translated with the older `<0>`, and a re-run must not have to redo them.
    Bhashini drops the '>' of a marker followed by a word ('<6 acres' for
    '<6> acres') and spaces the capitals out ('XX 0 XX'); both are repaired
    first rather than losing the whole line."""
    text = re.sub(r"<(\d+)(?!\d|>)", r"<\1>", text)
    text = re.sub(r"X\s*X\s*(\d+)\s*X\s*X", r"XX\1XX", text)
    for i, n in enumerate(names):
        hits = text.count(marker(i)) + text.count(f"<{i}>")
        # A placeholder is data: lose it and the sentence is wrong, so the
        # line goes back in English. A dash is punctuation, and these scripts
        # mostly do not use one — losing it costs a pause, and refusing the
        # whole translation over it costs the farmer the sentence. Thirty to
        # fifty strings a language came down to exactly that choice.
        if n == DASH:
            text = text.replace(marker(i), DASH, 1).replace(f"<{i}>", DASH, 1)
            text = text.replace(marker(i), "").replace(f"<{i}>", "")
            continue
        if hits != 1:
            return None
        text = text.replace(marker(i), "{" + n + "}").replace(f"<{i}>", "{" + n + "}")
    return re.sub(r"\s{2,}", " ", text).strip()


UNIT_BOUND = re.compile(r"\{[^{}]*\}\s*(?:km|mm|cm|kg|ml|°C|%|acres?|ha)\b")
"""A placeholder that means nothing without the unit standing next to it."""


def kept_order(out: str, count: int) -> bool:
    """Whether the markers came back in the order they went out.

    Word order is the translator's business and reordering is usually right —
    Gujarati and Malayalam put the verb last. But a sentence like "{name} on a
    {crop} farm {km} km from you" pins each placeholder to the words beside
    it, and a model that moves one without the other produces "{crop}
    kilometres away": every marker present, every count correct, and the
    number is a crop. Where a placeholder is bound to a unit, order is the one
    cheap signal that the pairing survived."""
    seen = [int(m.group(1) or m.group(2)) for m in re.finditer(r"XX(\d+)XX|<(\d+)>", out)]
    # Only the placeholders are checked. A dash marker rides at the end of the
    # list and may legitimately go missing, so counting it here would refuse
    # the line for the one thing we are willing to lose.
    order = [i for i in seen if i < count]
    return order == sorted(order) and len(order) == count


def machine_translate(text: str, lang: str) -> str | None:
    from app import voice  # noqa: PLC0415  (Sarvam, key pool)

    if not text.strip() or not re.search(r"[A-Za-z]", text):
        return text  # numbers, units, symbols: nothing to translate
    safe, names = protect(text)
    try:
        out = voice.translate(safe, "en", lang)
    except Exception:  # noqa: BLE001  one failed string must not stop the batch
        return None
    holes = sum(1 for n in names if n != DASH)
    if holes > 1 and UNIT_BOUND.search(text) and not kept_order(out, holes):
        return None  # shuffled: better in English than with the wrong number
    out = tidy(text, out)
    return restore(out, names) if names else out


SENTENCE_END = re.compile(r"[.।॥|!?]+\s*$")


VISARGA = "\u0903\u0983\u0a03\u0a83\u0b03\u0c03\u0c83\u0d03"
"""The visarga of Devanagari, Bengali, Gurmukhi, Gujarati, Odia, Telugu, Kannada
and Malayalam. It looks like a colon and Bhashini writes it for one ('ফসলঃ' for
'Crop:'), but it is a letter, so the label reads as a misspelt word."""
_VISARGA_AS_COLON = re.compile(f"[{VISARGA}](?=\\s|$|\\{{|<)")


def colons(source: str, out: str) -> str:
    """Give back the colons a translator turned into visargas — only as many
    as the source had, and only at a word's end, so a real visarga inside a
    word (দুঃখ) is never touched."""
    n = source.count(":")
    return _VISARGA_AS_COLON.sub(":", out, count=n) if n else out


def tidy(source: str, out: str) -> str:
    """Translators end a lone word or label with a full stop (Bengali 'আজ।' for
    'today'); keep the source's own ending instead. And colons written as a
    visarga are colons again."""
    out = colons(source, out.strip())
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


# --------------------------------------------------------------------------
# Dates in the farmer's language
# --------------------------------------------------------------------------

MONTHS = {
    "en": "January February March April May June July August September October November December",
    "hi": "जनवरी फ़रवरी मार्च अप्रैल मई जून जुलाई अगस्त सितंबर अक्टूबर नवंबर दिसंबर",
    "mr": "जानेवारी फेब्रुवारी मार्च एप्रिल मे जून जुलै ऑगस्ट सप्टेंबर ऑक्टोबर नोव्हेंबर डिसेंबर",
    "bn": "জানুয়ারি ফেব্রুয়ারি মার্চ এপ্রিল মে জুন জুলাই আগস্ট সেপ্টেম্বর অক্টোবর নভেম্বর ডিসেম্বর",
    "ta": "ஜனவரி பிப்ரவரி மார்ச் ஏப்ரல் மே ஜூன் ஜூலை ஆகஸ்ட் செப்டம்பர் அக்டோபர் நவம்பர் டிசம்பர்",
    "te": "జనవరి ఫిబ్రవరి మార్చి ఏప్రిల్ మే జూన్ జూలై ఆగస్టు సెప్టెంబర్ అక్టోబర్ నవంబర్ డిసెంబర్",
    "kn": "ಜನವರಿ ಫೆಬ್ರವರಿ ಮಾರ್ಚ್ ಏಪ್ರಿಲ್ ಮೇ ಜೂನ್ ಜುಲೈ ಆಗಸ್ಟ್ ಸೆಪ್ಟೆಂಬರ್ ಅಕ್ಟೋಬರ್ ನವೆಂಬರ್ ಡಿಸೆಂಬರ್",
    "ml": "ജനുവരി ഫെബ്രുവരി മാർച്ച് ഏപ്രിൽ മേയ് ജൂൺ ജൂലൈ ഓഗസ്റ്റ് സെപ്റ്റംബർ ഒക്ടോബർ നവംബർ ഡിസംബർ",
    "gu": "જાન્યુઆરી ફેબ્રુઆરી માર્ચ એપ્રિલ મે જૂન જુલાઈ ઑગસ્ટ સપ્ટેમ્બર ઑક્ટોબર નવેમ્બર ડિસેમ્બર",
    "pa": "ਜਨਵਰੀ ਫ਼ਰਵਰੀ ਮਾਰਚ ਅਪ੍ਰੈਲ ਮਈ ਜੂਨ ਜੁਲਾਈ ਅਗਸਤ ਸਤੰਬਰ ਅਕਤੂਬਰ ਨਵੰਬਰ ਦਸੰਬਰ",
}
"""Month names as written in each language (the CLDR forms): a translated
sentence must not carry 'September' or 'Jun' in English."""


def month_name(month: int, lang: str) -> str:
    return (MONTHS.get(lang) or MONTHS["en"]).split()[month - 1]


def local_date(d, lang: str, *, year: bool = True) -> str:
    """'28 June 2026' / '28 जून 2026' — day, month name, year in every language
    (English keeps its short month)."""
    m = month_name(d.month, lang)
    if lang == "en":
        m = m[:3]
    return f"{d.day} {m}" + (f" {d.year}" if year else "")
