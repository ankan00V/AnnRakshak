"""Sarvam AI voice layer: Bulbul TTS (read advisories aloud), Saaras STT
(speak instead of type) and Sarvam-Translate (expert notes → farmer's
language). Server-side only — the API key never reaches the browser.

TTS audio is cached on disk by (text, language): advisories repeat, and every
repeat would otherwise cost a paid call and a network round trip in the field.

Pesticide-verdict strings are the one thing we never re-phrase or translate
at runtime; they are read out exactly as authored in labelcheck.VERDICTS.
"""

from __future__ import annotations

import base64
import hashlib
import itertools
import threading
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import cache
from app.auth import require_user
from app.config import (
    DATA_DIR,
    SARVAM_API_KEYS,
    SARVAM_LANG,
    SARVAM_SPEAKER,
    SARVAM_STT_MODEL,
    SARVAM_TRANSLATE_MODEL,
    SARVAM_TTS_MODEL,
)

TTS_CACHE = DATA_DIR / "tts"
MAX_TTS_CHARS = 2400  # REST limit is 2,500
PAID_TTS_PER_MINUTE = 120  # cached audio is free and not counted

router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceUnavailable(RuntimeError):
    pass


class KeyPool:
    """Round-robin over the team's Sarvam keys. A key that is out of credits or
    revoked (401/402/403) is benched for hours, a rate-limited one (429) for a
    minute, and the call moves on to the next key. Other failures (bad input,
    Sarvam down) are not the key's fault and are raised at once."""

    BENCH_S = {401: 6 * 3600, 402: 6 * 3600, 403: 6 * 3600, 429: 60}

    def __init__(self, keys: list[str]) -> None:
        self.keys = keys
        self._next = itertools.cycle(range(len(keys))) if keys else None
        self._bench: dict[int, float] = {}
        self._clients: dict[int, object] = {}
        self._lock = threading.Lock()

    def _client(self, i: int):
        if i not in self._clients:
            from sarvamai import SarvamAI  # noqa: PLC0415  optional dependency

            self._clients[i] = SarvamAI(api_subscription_key=self.keys[i], timeout=30)
        return self._clients[i]

    def _fp(self, i: int) -> str:
        return hashlib.sha256(self.keys[i].encode()).hexdigest()[:12]  # never the key itself

    def _benched(self, i: int, now: float) -> bool:
        return self._bench.get(i, 0) > now or bool(cache.get_json(f"sarvam:bench:{self._fp(i)}"))

    def call(self, fn):
        if not self.keys:
            raise VoiceUnavailable("no Sarvam API key is set")
        with self._lock:
            order = [next(self._next) for _ in self.keys]
        now = time.time()
        ready = [i for i in order if not self._benched(i, now)] or order  # all benched: try anyway
        last = None
        for i in ready:
            try:
                return fn(self._client(i))
            except Exception as e:  # noqa: BLE001
                code = getattr(e, "status_code", None)
                if code not in self.BENCH_S:
                    raise
                self._bench[i] = time.time() + self.BENCH_S[code]
                cache.set_json(f"sarvam:bench:{self._fp(i)}", code, self.BENCH_S[code])  # tell other workers
                last = e
        raise VoiceUnavailable(f"every Sarvam key is out of credits or rate-limited ({getattr(last, 'status_code', '?')})")

    def status(self) -> dict:
        now = time.time()
        return {"keys": len(self.keys), "benched": sum(1 for t in self._bench.values() if t > now)}


pool = KeyPool(SARVAM_API_KEYS)


def tts(text: str, lang: str, pace: float = 0.95) -> bytes:
    text = " ".join(text.split())[:MAX_TTS_CHARS]
    key = hashlib.sha256(f"{SARVAM_TTS_MODEL}|{SARVAM_SPEAKER}|{lang}|{pace}|{text}".encode()).hexdigest()
    path = TTS_CACHE / f"{key}.wav"
    if path.exists():
        return path.read_bytes()
    from app.limits import limit  # noqa: PLC0415

    limit("sarvam:tts:paid", PAID_TTS_PER_MINUTE, 60)  # platform-wide cap on paid synthesis
    resp = pool.call(lambda c: c.text_to_speech.convert(
        text=text, language_code=SARVAM_LANG[lang], model=SARVAM_TTS_MODEL,
        speaker=SARVAM_SPEAKER, pace=pace,
    ))
    audio = base64.b64decode("".join(resp.audios))
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio


def stt(audio: bytes, filename: str, lang: str | None) -> dict:
    kwargs = {"model": SARVAM_STT_MODEL, "mode": "transcribe"}
    if lang:
        kwargs["language_code"] = SARVAM_LANG[lang]
    resp = pool.call(lambda c: c.speech_to_text.transcribe(file=(filename, audio), **kwargs))
    return {"transcript": resp.transcript, "language_code": getattr(resp, "language_code", None)}


def translate(text: str, source: str, target: str) -> str:
    if source == target or not text.strip():
        return text
    resp = pool.call(lambda c: c.text.translate(
        input=text[:1900], source_language_code=SARVAM_LANG[source],
        target_language_code=SARVAM_LANG[target], model=SARVAM_TRANSLATE_MODEL, mode="formal",
    ))
    return resp.translated_text


def status() -> dict:
    return {"configured": bool(pool.keys), "key_pool": pool.status(), "tts": SARVAM_TTS_MODEL, "stt": SARVAM_STT_MODEL,
            "translate": SARVAM_TRANSLATE_MODEL}


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    lang: str = Field(pattern="^(en|hi|mr|bn|ta|te|kn|ml|gu|pa|od)$")


@router.get("/status")
def voice_status():
    return status()


@router.post("/tts", dependencies=[Depends(require_user)])
def tts_endpoint(body: TTSIn, request: Request):
    from app.limits import client_ip, limit  # noqa: PLC0415

    limit(f"tts:{client_ip(request)}", 90, 60)
    try:
        return Response(tts(body.text, body.lang), media_type="audio/wav")
    except VoiceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:  # upstream failure: say so, don't pretend
        raise HTTPException(502, f"speech service failed: {type(exc).__name__}") from exc


@router.post("/stt", dependencies=[Depends(require_user)])
async def stt_endpoint(request: Request, audio: UploadFile = File(...), lang: str | None = Form(None)):
    from app.limits import client_ip, limit  # noqa: PLC0415

    limit(f"stt:{client_ip(request)}", 30, 60)
    data = await audio.read()
    if not data:
        raise HTTPException(422, "empty audio")
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "audio too long — keep it under 30 seconds")
    try:
        return stt(data, audio.filename or "speech.webm", lang if lang in SARVAM_LANG else None)
    except VoiceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"speech service failed: {type(exc).__name__}") from exc


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=1900)
    source: str = Field(pattern="^(en|hi|mr)$")
    target: str = Field(pattern="^(en|hi|mr)$")


@router.post("/translate", dependencies=[Depends(require_user)])
def translate_endpoint(body: TranslateIn):
    try:
        return {"text": translate(body.text, body.source, body.target)}
    except VoiceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"translation service failed: {type(exc).__name__}") from exc
