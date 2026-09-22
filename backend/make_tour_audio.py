"""Voice the app tour in every language, once, into static files.

The tour (frontend/landing/src/farmer/tour) plays one short clip per step:
public/tour/<lang>/<step>.mp3, the step's title and caption read by Sarvam's
Bulbul voice. Made here rather than at run time so the tour starts instantly,
works on a weak connection, and costs no voice credit when farmers use it.

Captions come from the app's own text (lib/i18n.ts for English, Hindi and
Marathi; locales/<lang>.json for the rest), so what is heard is what is shown.
A clip is remade only when its text changed (public/tour/manifest.json keeps a
hash per clip). Each clip is re-encoded to mono 32 kbit/s MP3 — plenty for a
voice, about a third of the size.

    SARVAM_TOUR_KEYS=key1,key2 ../.venv/bin/python make_tour_audio.py
    ... make_tour_audio.py --lang ta,pa --force
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx

import translate_i18n as T
from app.config import SARVAM_LANG

STEPS = ["welcome", "farm", "weather", "live", "scan", "checks", "spray", "alerts", "krishi", "lang", "done"]
"""Must match frontend/landing/src/farmer/tour/steps.ts."""
LANGS = ["en", "hi", "mr", "bn", "ta", "te", "kn", "ml", "gu", "pa"]
OUT = T.ROOT / "frontend" / "landing" / "public" / "tour"
TTS_URL = "https://api.sarvam.ai/text-to-speech"
MODEL, SPEAKER, PACE = "bulbul:v3", "shubh", 0.92
STOP = {"hi": "।", "bn": "।", "pa": "।"}  # the full stop each script writes
I18N_TS = T.ROOT / "frontend" / "landing" / "src" / "lib" / "i18n.ts"


def authored(lang: str) -> dict[str, str]:
    """The key: text pairs of one authored language block in lib/i18n.ts."""
    src = I18N_TS.read_text(encoding="utf-8")
    start = re.search(rf"^const {lang}\b.*=\s*{{\s*$", src, re.M)
    end = src.index("\n}", start.end())
    out = {}
    for line in src[start.end():end].splitlines():
        m = T.UI_LINE.match(line)
        if m:
            out[m.group(2)] = json.loads(f'"{m.group(4)}"') if m.group(3) == '"' else m.group(4).replace("\\'", "'")
    return out


def texts(lang: str) -> dict[str, str]:
    table = authored(lang) if lang in ("en", "hi", "mr") else \
        json.loads((T.UI_OUT / f"{lang}.json").read_text(encoding="utf-8"))
    out = {}
    for step in STEPS:
        title, body = table.get(f"tour_{step}_t"), table.get(f"tour_{step}_b")
        if title and body:
            out[step] = f"{title}{STOP.get(lang, '.')} {body}"
    return out


class Voice:
    def __init__(self, keys: list[str]):
        self.keys = keys

    def say(self, text: str, lang: str) -> bytes:
        for k in list(self.keys):
            r = httpx.post(TTS_URL, headers={"api-subscription-key": k}, timeout=90, json={
                "text": text, "target_language_code": SARVAM_LANG[lang], "model": MODEL,
                "speaker": SPEAKER, "pace": PACE, "output_audio_codec": "mp3"})
            if r.status_code in (401, 402, 403, 429):
                self.keys.remove(k)  # out of credit or limited: the next key
                continue
            r.raise_for_status()
            return base64.b64decode("".join(r.json()["audios"]))
        raise SystemExit("no Sarvam key with credit left")


def squeeze(mp3: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in.mp3"), Path(d, "out.mp3")
        src.write_bytes(mp3)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-b:a", "32k", str(dst)],
                       check=True)
        return dst.read_bytes()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=",".join(LANGS))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    keys = [k.strip() for k in (os.environ.get("SARVAM_TOUR_KEYS") or "").split(",") if k.strip()]
    if not keys:
        raise SystemExit("set SARVAM_TOUR_KEYS")
    voice = Voice(keys)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for lang in args.lang.split(","):
        made = 0
        for step, text in texts(lang).items():
            name = f"{lang}/{step}.mp3"
            digest = hashlib.sha256(f"{MODEL}|{SPEAKER}|{PACE}|{text}".encode()).hexdigest()[:16]
            path = OUT / name
            if not args.force and manifest.get(name) == digest and path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(squeeze(voice.say(text, lang)))
            manifest[name] = digest
            made += 1
        manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n")
        size = sum(p.stat().st_size for p in (OUT / lang).glob("*.mp3")) // 1024 if (OUT / lang).exists() else 0
        print(f"{lang}: {made} clip(s) made, {size} KB in all")


if __name__ == "__main__":
    main()
