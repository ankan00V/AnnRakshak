"""The language model (openai/gpt-oss-20b on Groq), used for one job:
understanding what a farmer typed.

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

import hashlib
import itertools
import json
import logging
import re
import threading
import time

import httpx

from app.config import GROQ_API_KEYS, GROQ_MODEL, GROQ_URL, LLM_TIMEOUT_S

log = logging.getLogger("annrakshak.llm")

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
    return bool(GROQ_API_KEYS)


BENCH_S = 300
"""A key that timed out sits out this long: a farmer should not wait out a
struggling server's timeout on every question."""
BLIP_S = 60
"""A key that was refused quickly (the free tier's rate limit) sits out briefly."""
_turn = itertools.count()
_benched: dict[str, float] = {}


def _chat(messages: list[dict], *, max_tokens: int, temperature: float, timeout: float | None = None) -> str | None:
    """Groq keys take turns, so each key's free-tier limit shares the load: each
    call starts one key further on and walks the rest if one is limited. All
    of them failing returns None, and every caller has its own fallback."""
    if not GROQ_API_KEYS:
        return None
    start = next(_turn) % len(GROQ_API_KEYS)
    for k in GROQ_API_KEYS[start:] + GROQ_API_KEYS[:start]:
        slot = hashlib.sha1(k.encode()).hexdigest()[:8]  # never hold a raw key
        if _benched.get(slot, 0) > time.monotonic():
            continue
        started = time.monotonic()
        out = _groq(messages, key=k, max_tokens=max_tokens, temperature=temperature, timeout=timeout)
        if out is not None:
            return out
        slow = time.monotonic() - started >= (timeout or LLM_TIMEOUT_S) - 0.5
        _benched[slot] = time.monotonic() + (BENCH_S if slow else BLIP_S)
        log.warning("a Groq key sits out %ss", BENCH_S if slow else BLIP_S)
    return None


def _groq(messages: list[dict], *, max_tokens: int, temperature: float, key: str,
          timeout: float | None) -> str | None:
    try:
        r = httpx.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"},
                       # reasoning kept low: a farmer is waiting, and for this
                       # model more thinking bought no better answers
                       json={"model": GROQ_MODEL, "messages": messages, "max_tokens": max_tokens,
                             "temperature": temperature, "top_p": 0.9, "reasoning_effort": "low"},
                       timeout=timeout or LLM_TIMEOUT_S)
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


def route(question: str, topics: list[tuple[str, str]], before: str | None = None) -> str | None:
    """The id of the topic that best answers `question`, or None.

    `topics` is [(id, what the topic covers)]. The reply is only accepted when it
    is one of those ids, so this can never introduce a topic that does not exist.
    `before` is the chat so far (the farmer's last question and the topic that
    answered it), so a follow-up such as "no, it's not that" is read in context.
    """
    question = " ".join((question or "").split())[:300]
    if not question or not topics:
        return None
    listing = "\n".join(f"{tid}: {example}" for tid, example in topics)
    earlier = (f"Earlier in this chat: {before}. Read the new question as a follow-up to that if it is one — "
               "for example 'no, it's not that' after a list of likely diseases means the farmer wants to find "
               "out what their crop actually has.\n\n") if before else ""
    _said_none.value = False
    out = _chat(
        [{"role": "system", "content": ROUTE_SYSTEM},
         {"role": "user", "content": f"Topics:\n{listing}\n\n{earlier}Farmer's question: {question}\n\nTopic id:"}],
        max_tokens=800, temperature=0.0)
    if not out:
        return None
    word = re.findall(r"[a-z_]+", out.lower())
    known = {tid for tid, _ in topics}
    for w in reversed(word):  # the id is the last thing it says
        if w in known:
            return w
        if w == "none":
            _said_none.value = True
            return None
    return None


_said_none = threading.local()


def answered_none() -> bool:
    """True when the last route() on this thread was the model saying 'off
    topic' — as opposed to no model answering at all."""
    return getattr(_said_none, "value", False)


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


def suggest(product: str, crop: str, problem: str, lang: str, *, timeout: float | None = None) -> str | None:
    """What an unrecognised thing actually is — explanation only, never a
    recommendation. The caller must still run it past the guards in
    labelcheck.safe_suggestion() before showing it."""
    product = " ".join((product or "").split())[:80]
    if not product:
        return None
    system = SUGGEST_SYSTEM.format(crop=crop, problem=problem, language=LANG_NAME.get(lang, "English"))
    out = _chat([{"role": "system", "content": system},
                 {"role": "user", "content": f'The farmer typed: "{product}"'}],
                max_tokens=900, temperature=0.1, timeout=timeout)
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


RESTYLE_SYSTEM = """A farmer asked a question in {language} written in English \
letters, mixing in English words (for example "aj ka weather kya h"). Below is \
the app's answer in {language} script, one line per item.

Rewrite every line the way that farmer texts: {language} in English letters, \
mixing in everyday English the way people really type — reuse any English word \
the farmer used (they wrote "weather", so say "weather"), and prefer the common \
English word for technical terms (humidity, rain chance, spray, crop, field, \
stage, degree). The sentence itself stays {language}: its grammar and its \
everyday words (for Hindi: abhi, agle, hai, nahi, karein) — only such nouns \
switch to English. Short and natural, like a message from a helpful neighbour. \
Example (Hindi): "अभी 31°C, नमी 69%, अगले 3 घंटों में बारिश की संभावना 68%" \
becomes "Abhi 31°C hai, humidity 69%, agle 3 ghante mein rain chance 68%". \
Every detail stays, including time spans like "next 3 hours". \
Keep every marker like <<0>> exactly as it is — each stands for a name. \
For crop problems use the standard English farming words: blight, rot, root \
rot, rust, wilt, leaf spot, pest, pest damage — never a looser word such as \
"burn" or "scorch". \
Use English letters only — no {language} script anywhere; write units the \
English way (mm, °C, km/h, acres, %). Keep every number, date, name and time \
exactly as written. Do not add, drop or soften anything — especially a \
warning. Keep the same number of lines, in the same order.

Reply as JSON and nothing else: {{"lines": ["...", "..."]}}"""


INDIC = re.compile("[\u0900-\u0D7F]")


def restyle(question: str, lines: list[str], lang: str) -> list[str] | None:
    """The answer lines rewritten in the farmer's romanised style, or None. A
    rewrite that changes, adds or drops any number is refused — the facts must
    survive the style."""
    lines = [x for x in lines if x and x.strip()]
    if not lines:
        return None
    for _ in range(3):  # retries: a rewrite that drops a detail is refused, not shown
        got = _restyle_once(question, lines, lang)
        if got:
            return got
    return None


def _restyle_once(question: str, lines: list[str], lang: str) -> list[str] | None:
    out = _chat([{"role": "system", "content": RESTYLE_SYSTEM.format(language=LANG_NAME.get(lang, "Hindi"))},
                 {"role": "user", "content": f"Farmer's question: {question[:200]}\n\nAnswer lines:\n"
                                             + "\n".join(lines)}],
                max_tokens=900, temperature=0.0)
    got = (json_reply(out or "") or {}).get("lines")
    if not isinstance(got, list) or not got or not all(isinstance(x, str) and x.strip() for x in got):
        return None
    if len(lines) == 1 and len(got) > 1:
        got = [" ".join(got)]  # one answer line split at its full stop: still one line
    if len(got) != len(lines) or INDIC.search(" ".join(got)):
        return None  # a line lost, or half left in the original script
    numbers = lambda t: sorted(re.findall(r"\d+(?:[.,:]\d+)?", t))  # noqa: E731
    if numbers(" ".join(lines)) != numbers(" ".join(got)):
        return None
    return [" ".join(x.split()) for x in got]
