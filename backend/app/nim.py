"""NVIDIA NIM, used for one job: understanding what a farmer typed.

Krishi's promise is that it never invents an answer. A language model is very
good at reading "mera dhan me patta pila ho raha hai kya karu" and very willing
to invent a pesticide dose, so it is given only the first job:

  route(question, topics)  -> the id of one authored topic, or None

The reply is checked against the closed list of topic ids before it is used, so
the worst a wrong answer can do is send the farmer to the wrong help page —
never to a made-up fact. Everything the farmer then reads still comes from
kb/krishi.json or from their own field's data.

`say()` is the other half: it phrases facts the server has already computed, in
the farmer's language, and callers check every number in the reply against
those facts (see krishi.grounded).

The key is optional. Without it, and on any timeout, error or odd reply, these
return None and Krishi falls back to its own matcher — which is why nothing
here raises.
"""

from __future__ import annotations

import json
import re

import httpx

from app.config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL, NVIDIA_TIMEOUT_S

ROUTE_SYSTEM = """You route a farmer's question to one help topic in an Indian \
crop-advisory app called AnnRakshak.

You are given a numbered list of topics. Reply with ONLY the id of the single \
best topic, exactly as written, and nothing else.

The farmer may write in English, Hindi, Marathi, Bengali, Tamil, Telugu, \
Kannada, Malayalam, Gujarati, Punjabi or Odia, in that language's own script or \
in Latin letters, with typos and mixed languages. Read the intent, not the \
spelling.

Reply with the single word none if the question is not about this app, this \
farmer's field, or growing these crops — for example market prices, politics, \
general chat, or anything you would have to invent an answer for."""

SAY_SYSTEM = """You are Krishi, the helper inside AnnRakshak, an Indian crop \
advisory app. You are talking to one farmer about their own field.

Answer using ONLY the facts given below. Never add a number, name, date or \
recommendation that is not in them. If the facts do not answer the question, \
set "text" to a short sentence saying you do not have that, and leave "points" \
empty.

Never name a pesticide, a dose or a chemical: the app has a separate checked \
advisory for that. Never mention any other farmer.

Write for someone reading a small phone screen in bright sun, who may read \
slowly. Reply in {language} as JSON and nothing else:

{{"text": "one short sentence answering the question, at most 20 words",
  "points": ["a short line per detail, at most 12 words each, no more than 3"]}}

Use "points" only when the answer really has separate parts, such as one line \
per field. For a one-fact question leave it empty. Never repeat in "points" \
what "text" already says. No markdown, no greeting, no sign-off."""

LANG_NAME = {"en": "English", "hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "ta": "Tamil",
             "te": "Telugu", "kn": "Kannada", "ml": "Malayalam", "gu": "Gujarati", "pa": "Punjabi",
             "od": "Odia"}


def enabled() -> bool:
    return bool(NVIDIA_API_KEY)


def _chat(messages: list[dict], *, max_tokens: int, temperature: float, key: str | None = None,
          timeout: float | None = None) -> str | None:
    key = key or NVIDIA_API_KEY
    if not key:
        return None
    try:
        r = httpx.post(
            f"{NVIDIA_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            # A farmer is waiting, so the model answers instead of thinking about
            # it: left to reason, this one takes 16 s over "read it out to me"
            # and 1 s with reasoning off, for the same answer.
            json={"model": NVIDIA_MODEL, "messages": messages, "max_tokens": max_tokens,
                  "temperature": temperature, "top_p": 0.9, "stream": False,
                  "reasoning_effort": "low", "chat_template_kwargs": {"thinking": False}},
            timeout=timeout or NVIDIA_TIMEOUT_S,
        )
        if r.status_code != 200:
            return None
        out = r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
        return None
    return _strip_thinking(out or "")


def _strip_thinking(text: str) -> str:
    """Reasoning models emit their working in <think> tags; keep the answer."""
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S | re.I)
    return re.sub(r"</?think>", " ", text, flags=re.I).strip()


def route(question: str, topics: list[tuple[str, str]]) -> str | None:
    """The id of the topic that best answers `question`, or None.

    `topics` is [(id, what the topic covers)]. The reply is only accepted when it
    is one of those ids, so this can never introduce a topic that does not exist.
    """
    question = " ".join((question or "").split())[:300]
    if not question or not topics:
        return None
    listing = "\n".join(f"{tid}: {example}" for tid, example in topics)
    out = _chat(
        [{"role": "system", "content": ROUTE_SYSTEM},
         {"role": "user", "content": f"Topics:\n{listing}\n\nFarmer's question: {question}\n\nTopic id:"}],
        max_tokens=800, temperature=0.0)
    if not out:
        return None
    word = re.findall(r"[a-z_]+", out.lower())
    known = {tid for tid, _ in topics}
    for w in reversed(word):  # the id is the last thing it says
        if w in known:
            return w
        if w == "none":
            return None
    return None


LEAD_WORDS = 26
POINT_WORDS = 16
MAX_POINTS = 3


def _trim(s: object, words: int) -> str:
    """One clean line, cut to length on a word boundary rather than mid-word."""
    text = " ".join(str(s or "").replace("*", "").replace("#", "").split())
    parts = text.split(" ")
    return text if len(parts) <= words else " ".join(parts[:words]).rstrip(",;:") + "…"


def say(question: str, facts: str, lang: str) -> tuple[str, list[str]] | None:
    """(a sentence, up to three short lines) answering `question` from `facts`
    and nothing else. The caller must still check it against the facts.

    Kept short and split on purpose: this is read on a phone in a field, so one
    plain answer first and the details as separate lines, never a paragraph."""
    question = " ".join((question or "").split())[:300]
    if not question or not facts.strip():
        return None
    system = SAY_SYSTEM.format(language=LANG_NAME.get(lang, "English"))
    out = _chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"Facts about this farmer's field:\n{facts}\n\nQuestion: {question}"}],
        max_tokens=900, temperature=0.2)
    if not out:
        return None
    got = json_reply(out)
    if got is None:  # it answered in prose after all: keep the first sentence
        lead, points = _trim(out, LEAD_WORDS), []
    else:
        raw = got.get("points")
        points = [_trim(p, POINT_WORDS) for p in raw[:MAX_POINTS]] if isinstance(raw, list) else []
        lead = _trim(got.get("text"), LEAD_WORDS)
    points = [p for p in points if p]
    return (lead, points) if lead else None


SUGGEST_SYSTEM = """You help a farmer in India who typed something into a \
pesticide checker that the app has no record of. The app has already refused to \
endorse it. Your only job is to tell them what the thing they typed actually is, \
and whether it treats their crop problem.

Crop: {crop}. Problem being treated: {problem}.

Rules you must not break:
- NEVER name any pesticide, fungicide, insecticide or chemical as something to \
use. Not one. If asked what to use instead, say the app's own advice for this \
problem is the place to look.
- NEVER give a dose, quantity, concentration, or mixing ratio.
- If the thing is dangerous to spray on a crop or on a person, say so plainly \
and first.
- If you do not know what it is, say so. Do not invent a product.

Reply in {language} as JSON and nothing else:

{{"text": "one or two short sentences: what it is, and whether it works for \
this problem. At most 35 words."}}

Plain words a farmer can read on a phone. No markdown, no lists, no greeting."""


def suggest(product: str, crop: str, problem: str, lang: str, *, key: str | None = None,
            timeout: float | None = None) -> str | None:
    """What an unrecognised thing actually is — explanation only, never a
    recommendation. The caller must still run it past the guards in
    labelcheck.safe_suggestion() before showing it."""
    product = " ".join((product or "").split())[:80]
    if not product:
        return None
    system = SUGGEST_SYSTEM.format(crop=crop, problem=problem, language=LANG_NAME.get(lang, "English"))
    out = _chat([{"role": "system", "content": system},
                 {"role": "user", "content": f'The farmer typed: "{product}"'}],
                max_tokens=900, temperature=0.1, key=key, timeout=timeout)
    if not out:
        return None
    got = json_reply(out)
    text = _trim((got or {}).get("text") if got else out, 40)
    return text or None


def json_reply(text: str) -> dict | None:
    """Parse a JSON object out of a reply, tolerating fences and stray prose."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        got = json.loads(m.group(0))
    except ValueError:
        return None
    return got if isinstance(got, dict) else None
