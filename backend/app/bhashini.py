"""Bhashini (MeitY's language platform) — translation, speech and transcription.

One compute endpoint, three tasks, all authorised by the account's inference
key (server-side only; it never reaches the browser):

  translate(text, source, target)   IndicTrans2, 11 languages
  tts(text, lang)                   Indic TTS -> 16-bit PCM WAV
  asr(audio, lang)                  Conformer / Whisper -> text

Model ids are fixed rather than looked up per call: the pipeline-config lookup
is a second round trip on every request, and the ids it returns are these.

Every function raises BhashiniError on any failure. voice.py decides what to do
next (try Sarvam, or tell the farmer), so nothing here guesses.
"""

from __future__ import annotations

import base64
import io
import shutil
import struct
import subprocess
import wave

import httpx
import numpy as np

from app import cache
from app.config import (
    BHASHINI_ASR_SERVICE,
    BHASHINI_COMPUTE_URL,
    BHASHINI_INFERENCE_KEY,
    BHASHINI_TRANSLATE_SERVICE,
    BHASHINI_TTS_SERVICE,
)

TIMEOUT = {"translation": 15.0, "tts": 12.0, "asr": 30.0}
"""TTS answers in 0.4-1.2 s when it answers at all (measured on all 11
languages); Odia hung past 60 s every time. A short bar hands a stuck call to
the fallback before the farmer gives up on the Listen button."""
BENCH_S = 600
"""After a failure a (task, language) pair is skipped for this long, so a
language the platform is not serving costs one farmer one wait, not everyone."""
ASR_RATE = 16000

# Bhashini uses the ISO 639-1 code for Odia; the app has always used "od".
CODE = {"od": "or"}


class BhashiniError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(BHASHINI_INFERENCE_KEY)


def _code(lang: str) -> str:
    return CODE.get(lang, lang)


def _bench_key(task: str, lang: str) -> str:
    return f"bhashini:bench:{task}:{lang}"


def benched(task: str, lang: str) -> bool:
    return bool(cache.get_json(_bench_key(task, lang)))


def _run(task: str, lang: str, config: dict, data: dict) -> dict:
    if not enabled():
        raise BhashiniError("no Bhashini inference key is set")
    if benched(task, lang):
        raise BhashiniError(f"{task} in {lang} failed recently; skipping for now")
    body = {"pipelineTasks": [{"taskType": task, "config": config}], "inputData": data}
    try:
        r = httpx.post(BHASHINI_COMPUTE_URL, json=body, timeout=TIMEOUT[task],
                       headers={"Authorization": BHASHINI_INFERENCE_KEY, "Content-Type": "application/json"})
        if r.status_code != 200:
            raise BhashiniError(f"{task} HTTP {r.status_code}")
        return r.json()["pipelineResponse"][0]
    except BhashiniError:
        cache.set_json(_bench_key(task, lang), 1, BENCH_S)
        raise
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        cache.set_json(_bench_key(task, lang), 1, BENCH_S)
        raise BhashiniError(f"{task} failed: {type(e).__name__}") from e


def translate(text: str, source: str, target: str) -> str:
    out = _run("translation", target, {
        "language": {"sourceLanguage": _code(source), "targetLanguage": _code(target)},
        "serviceId": BHASHINI_TRANSLATE_SERVICE,
    }, {"input": [{"source": text}]})
    got = (out.get("output") or [{}])[0].get("target")
    if not got:
        raise BhashiniError("translation came back empty")
    return got


def tts(text: str, lang: str) -> bytes:
    service = BHASHINI_TTS_SERVICE.get(lang)
    if not service:
        raise BhashiniError(f"no Bhashini voice for {lang}")
    out = _run("tts", lang, {
        "language": {"sourceLanguage": _code(lang)}, "serviceId": service,
        "gender": "female", "samplingRate": 16000,
    }, {"input": [{"source": text}]})
    try:
        raw = base64.b64decode(out["audio"][0]["audioContent"])
    except (KeyError, IndexError, ValueError) as e:
        raise BhashiniError("speech came back empty") from e
    return pcm16(raw)


def asr(audio: bytes, lang: str) -> str:
    service = BHASHINI_ASR_SERVICE.get(lang)
    if not service:
        raise BhashiniError(f"no Bhashini transcription for {lang}")
    wav = to_wav16k(audio)
    out = _run("asr", lang, {
        "language": {"sourceLanguage": _code(lang)}, "serviceId": service,
        "audioFormat": "wav", "samplingRate": ASR_RATE,
    }, {"audio": [{"audioContent": base64.b64encode(wav).decode()}]})
    return ((out.get("output") or [{}])[0].get("source") or "").strip()


def pcm16(wav: bytes) -> bytes:
    """Bhashini returns 32-bit float WAV. Browsers mostly play it, but not all,
    and Python's wave module cannot read it; 16-bit PCM plays everywhere."""
    if wav[:4] != b"RIFF":
        raise BhashiniError("speech is not a WAV file")
    i, fmt, data = 12, None, None
    while i + 8 <= len(wav):
        cid, size = wav[i:i + 4], struct.unpack("<I", wav[i + 4:i + 8])[0]
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", wav[i + 8:i + 24])
        elif cid == b"data":
            data = wav[i + 8:i + 8 + size]
        i += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise BhashiniError("speech WAV is incomplete")
    tag, channels, rate, _, _, bits = fmt
    if tag == 1 and bits == 16:
        return wav
    if tag == 3 and bits in (32, 64):
        x = np.frombuffer(data, dtype=np.float32 if bits == 32 else np.float64)
        samples = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    else:
        raise BhashiniError(f"unsupported WAV format {tag}/{bits}-bit")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return out.getvalue()


def to_wav16k(audio: bytes) -> bytes:
    """Whatever the browser recorded (webm/opus from Chrome, mp4 from Safari)
    as 16 kHz mono 16-bit WAV, which is what the transcription models take."""
    if not shutil.which("ffmpeg"):
        raise BhashiniError("ffmpeg is not installed, so the recording cannot be converted")
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             "-ac", "1", "-ar", str(ASR_RATE), "-sample_fmt", "s16", "-f", "wav", "pipe:1"],
            input=audio, capture_output=True, timeout=20, check=False)
    except subprocess.TimeoutExpired as e:
        raise BhashiniError("converting the recording took too long") from e
    if p.returncode != 0 or len(p.stdout) <= 44:
        raise BhashiniError("the recording could not be read")
    return p.stdout
