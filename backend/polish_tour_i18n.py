"""Second pass over the machine-translated app-tour lines, before they are voiced.

The tour is read aloud, so a stiff or wrong line is heard, not skimmed. The
first pass (translate_i18n.py, Bhashini) is literal: "take a close-up of one
sick leaf" came back as "take one sick leaf from nearby" — which sounds like
plucking it. This asks a larger model (openai/gpt-oss-120b on Groq) to correct
each line against the English into plain, natural speech for a farmer, keeping
every {placeholder}. The result replaces the line in
frontend/landing/src/locales/<lang>.json; it is still machine output and is
marked for native review like the rest.

    ../.venv/bin/python polish_tour_i18n.py              # all seven languages
    ../.venv/bin/python polish_tour_i18n.py --lang ta,pa
"""

from __future__ import annotations

import argparse
import json
import re
import time

import httpx

import translate_i18n as T
from app.config import GROQ_API_KEYS, GROQ_URL
from app.llm import LANG_NAME, json_reply

MODEL = "openai/gpt-oss-120b"
MACHINE = ["bn", "ta", "te", "kn", "ml", "gu", "pa"]
PLACEHOLDER = re.compile(r"\{\w+\}")

SYSTEM = """You check translations for a farming app used by Indian farmers.
Each line is shown on screen AND read aloud by a voice during a short guided
tour of the app. Given the English line and a machine translation into
{language}, return the best {language} version: correct meaning, simple
everyday words a farmer uses, natural when spoken, short. Keep app names
(AnnRakshak, Krishi) recognisable, and keep every {{placeholder}} exactly.
If the translation is already good, return it unchanged.

Reply as JSON and nothing else: {{"text": "..."}}"""


def polish(english: str, current: str, lang: str, key_index: int) -> str | None:
    key = GROQ_API_KEYS[key_index % len(GROQ_API_KEYS)]
    for attempt in range(3):
        try:
            r = httpx.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, timeout=60, json={
                "model": MODEL, "temperature": 0, "max_tokens": 1500, "reasoning_effort": "medium",
                "messages": [{"role": "system", "content": SYSTEM.format(language=LANG_NAME[lang])},
                             {"role": "user", "content": f"English: {english}\n{LANG_NAME[lang]}: {current}"}]})
        except httpx.HTTPError:
            time.sleep(2)
            continue
        if r.status_code == 429:  # this key's minute is used up: the next key
            key = GROQ_API_KEYS[(key_index + attempt + 1) % len(GROQ_API_KEYS)]
            time.sleep(1)
            continue
        if r.status_code != 200:
            return None
        text = ((json_reply(r.json()["choices"][0]["message"]["content"] or "") or {}).get("text") or "").strip()
        if text and sorted(PLACEHOLDER.findall(text)) == sorted(PLACEHOLDER.findall(english)):
            return " ".join(text.split())
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=",".join(MACHINE))
    args = ap.parse_args()
    english = {k: v for k, v in T.ui_strings().items() if k.startswith("tour")}
    for lang in args.lang.split(","):
        path = T.UI_OUT / f"{lang}.json"
        ui = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        for i, (k, en) in enumerate(sorted(english.items())):
            if k not in ui:
                continue
            better = polish(en, ui[k], lang, i)
            if better and better != ui[k]:
                ui[k] = better
                changed += 1
        path.write_text(json.dumps(dict(sorted(ui.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{lang}: {changed}/{len(english)} tour lines corrected")


if __name__ == "__main__":
    main()
