"""Krishi and Darpan as assistants: they look things up, then answer.

Before this, each question was matched to one kind of answer — the weather, a
pest, an app topic — and a question with two parts ("can I spray my rice today,
and what for?") or one that fitted no kind got half an answer or none. Here the
language model is given the app's own lookups as tools, decides which a
question needs, reads what they return, and answers in the user's language.

What it may say is fenced, because a farmer acts on it:

  * Every lookup reads this app's records and knowledge base and nothing else,
    through the same functions the screens use. A farmer's lookups see only
    that farmer's fields (the router resolves them from the session); an
    officer's see only what Darpan already shows them.
  * The answer is checked before anyone sees it (`grounded`): every number in
    it must appear in what the lookups returned or in the question, and every
    pesticide it names must be one a lookup returned. An answer that fails is
    dropped and the caller's fixed answer is given instead — the same answer
    the app gave before any of this existed.
  * No model, a timeout, a malformed reply: None, and the fixed answer stands.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from app import llm
from app.kb import KB, tr

log = logging.getLogger("annrakshak.assistant")

MAX_ROUNDS = 3
"""Lookups, then an answer: three rounds covers "check the weather and the
pest, then answer" without letting a confused model loop."""
MAX_TOOL_CHARS = 2000
"""What one lookup may hand back to the model; the rest is cut, not summarised."""


@dataclass
class Tool:
    name: str
    description: str
    params: dict           # JSON schema properties
    required: list[str]
    fn: Callable[..., dict]  # -> {"text"/"lines"/"steps"/..., "go": [...]}
    verbatim: bool = False
    """The lookup's own sentence is shown to the user as it is, first, and the
    model is told not to restate it: a spray or water instruction is too
    important to be paraphrased ("not now, tomorrow 13:00" once came back as
    "spray 13:00–18:00")."""

    def spec(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "properties": self.params, "required": self.required}}}


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[float]:
    out = set()
    for n in NUMBER.findall(text or ""):
        try:
            out.add(round(float(n.replace(",", ".")), 3))
        except ValueError:
            continue
    return out


def grounded(kb: KB, answer: str, evidence: str) -> bool:
    """Every number and every pesticide in `answer` is in `evidence`."""
    have = _numbers(evidence)
    if not _numbers(answer) <= have:
        return False
    low_answer, low_evidence = answer.lower(), evidence.lower()
    for p in kb.pesticides.values():
        for name in [p["name"], *p.get("aliases", [])]:
            n = name.lower()
            if len(n) >= 5 and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", low_answer) and n not in low_evidence:
                return False
    return True


CONJUNCTIONS = (" and ", " aur ", " ani ", " आणि ", " और ", " also ", " bhi ", " तसेच ", " then ", " plus ",
                " as well", " साथ ही ")


def compound(text: str) -> bool:
    """A question with more than one part, which a single fixed answer cannot cover."""
    t = f" {' '.join((text or '').lower().split())} "
    return len(t.split()) >= 5 and (any(c in t for c in CONJUNCTIONS) or t.count("?") > 1)


def run(kb: KB, *, system: str, question: str, tools: list[Tool], shape: str) -> dict | None:
    """Ask, look up, answer. `shape` is "farmer" ({text, points}) or "officer" ({lines})."""
    if not llm.enabled() or not (question or "").strip():
        return None
    by_name = {t.name: t for t in tools}
    messages: list[dict] = [{"role": "system", "content": system},
                            {"role": "user", "content": " ".join(question.split())[:400]}]
    # What it may quote: the question, its own instructions (the farmer's field
    # sheet, the Kisan Call Centre's number) and what the lookups return.
    evidence: list[str] = [question, system]
    go: list[dict] = []
    used: list[str] = []
    verbatim: list[str] = []
    final: str | None = None
    for round_no in range(MAX_ROUNDS + 1):
        last = round_no == MAX_ROUNDS
        msg = llm.chat_tools(messages, [] if last else [t.spec() for t in tools])
        if msg is None:
            return None
        calls = msg.get("tool_calls") or []
        if not calls or last:
            final = msg.get("content") or ""
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls[:4]:
            fn = c.get("function") or {}
            tool = by_name.get(fn.get("name", ""))
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            if tool is None or not isinstance(args, dict):
                result: dict = {"error": "no such lookup"}
            else:
                try:
                    result = tool.fn(**{k: v for k, v in args.items() if k in tool.params})
                except Exception as e:  # noqa: BLE001 — a lookup that fails is reported, not fatal
                    log.warning("assistant lookup %s failed: %s", tool.name, e)
                    result = {"error": "that lookup is not available right now"}
                used.append(tool.name)
            for g in result.pop("go", []) or []:
                if g not in go:
                    go.append(g)
            if tool is not None and tool.verbatim and result.get("text") and result["text"] not in verbatim:
                verbatim.append(result["text"])
            content = json.dumps(result, ensure_ascii=False, default=str)[:MAX_TOOL_CHARS]
            evidence.append(content)
            messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": content})
    if not final:
        return None
    got = llm.json_reply(final)
    if got is None:
        return None
    if shape == "officer":
        lines = [str(x).strip() for x in (got.get("lines") or []) if str(x).strip()][:8]
        said = " ".join(lines)
        out = {"lines": lines}
    else:
        text = str(got.get("text") or "").strip()
        points = [str(x).strip() for x in (got.get("points") or []) if str(x).strip()][:6]
        said = " ".join([text, *points])
        out = {"text": text, "steps": points}
    if not said or not grounded(kb, said, "\n".join(evidence)):
        log.info("assistant answer dropped: not grounded in its lookups")
        return None
    if verbatim and shape == "farmer":
        out["steps"] = [*verbatim, *[p for p in out["steps"] if p not in verbatim]][:7]
    return {**out, "go": go[:3], "used": used}


# ==========================================================================
# Krishi: one farmer, their own fields
# ==========================================================================

KRISHI_SYSTEM = """You are Krishi, the assistant inside AnnRakshak, an Indian crop-protection app. \
You are talking to one farmer about their own fields and about using the app. Today is {today}.

Their fields (use the field number in lookups; the one open on screen is field {current}):
{fields}

How to work:
- Look things up with the tools before answering. Use as many as the question needs: \
"can I spray today and what for" needs the spray window and the pest risks; \
"what is wrong with my rice" needs their cases and the risks.
- Answer ONLY from what the tools returned. Never add a number, a date, a dose, a product, \
a pesticide or a disease that a tool did not return.
- The spray_window and irrigation answers are shown to the farmer word for word by the app. \
Do not restate or rephrase them; at most say "see the spray advice below".
- Give amounts for their field when the lookup has them ("For your 3 acre field: ...").
- A named pest or disease: use pest_advice. Give organic options first; a chemical only \
as the last resort, and say to check the bottle in Spray check.
- A description of what they see, with no name: use symptom_candidates. Never say which \
disease it is — say what it could be and ask them to photograph it.
- How to use the app, what a screen or a word means: use app_help.
- Anything outside farming and this app (prices, loans, politics, health): say briefly \
you cannot help with that and that the Kisan Call Centre on 1800-180-1551 is free.

Reply in {language}, as JSON and nothing else:
{{"text": "the answer in one or two short sentences", "points": ["one short line per detail, at most 6"]}}
Short, plain words for someone reading a phone in the sun. No markdown, no greeting."""


SPRAY_WORDS = ("spray", "छिड़क", "छिडक", "फवार", "chhidak", "chidak", "favar")


def krishi(db, kb: KB, *, question: str, lang: str, user, farms: list, farm) -> dict | None:
    """Krishi's answer to `question` from this farmer's own fields, or None."""
    from app import cropqa, krishi as k  # noqa: PLC0415  (krishi imports this module)
    from app.engine import labelcheck  # noqa: PLC0415
    from app import services  # noqa: PLC0415

    own = list(farms) or ([farm] if farm is not None else [])
    current = next((i for i, f in enumerate(own, 1) if farm is not None and f.id == farm.id), 1 if own else 0)

    def field(n: int | None):
        if not own:
            return None
        try:
            i = int(n or current or 1)
        except (TypeError, ValueError):
            i = current or 1
        return own[i - 1] if 1 <= i <= len(own) else own[0]

    def live(fn):
        def call(field_no: int | None = None) -> dict:
            f = field(field_no)
            if f is None:
                return {"error": "no field is registered"}
            out = fn(db, kb, f, lang)
            return {"field": own.index(f) + 1, "text": out.get("text"), "lines": out.get("steps"), "go": out.get("go")}
        return call

    def pest_advice(pest: str, field_no: int | None = None, want: str = "control") -> dict:
        f = field(field_no)
        crop = cropqa.crop_named(pest) or (f.crop if f is not None else None)
        hits = cropqa.find(kb, pest, crop) or cropqa.find(kb, pest)
        if not hits:
            return {"error": f"no pest or disease called '{pest}' in the app's knowledge"}
        how = want if want in ("control", "organic", "chemical", "identify") else "control"
        area = f.area_acres if f is not None and kb.targets[hits[0][0]]["crop"] == f.crop else None
        out = cropqa.pest_answer(kb, hits[0][0], how, lang, area)
        return {"pest": tr(kb.targets[hits[0][0]]["names"], lang), "text": out["text"], "lines": out["steps"],
                "go": out["go"]}

    def symptom_candidates(description: str, field_no: int | None = None) -> dict:
        f = field(field_no)
        crop = cropqa.crop_named(description) or (f.crop if f is not None else None)
        if crop is None:
            return {"error": "which crop is it on?"}
        cands = [t for t, _ in cropqa.symptoms(kb, description, crop)[:3]]
        if not cands:
            return {"error": "no sign in the app's knowledge matches that description; ask for a photo",
                    "go": [{"to": "/app/scan", "label": tr(cropqa.TEXT["go_scan"], lang)}]}
        return {"crop": crop, "could_be": [{"name": tr(kb.targets[c]["names"], lang),
                                             "signs": tr(kb.targets[c].get("signature"), lang)} for c in cands],
                "note": "Many look alike; a photo decides.",
                "go": [{"to": "/app/scan", "label": tr(cropqa.TEXT["go_scan"], lang)}]}

    def spray_check(product: str, pest: str | None = None, field_no: int | None = None) -> dict:
        f = field(field_no)
        ing = cropqa._product_in(kb, product) or kb.match_pesticide(product)
        if ing is None:
            return {"error": f"'{product}' is not in the pesticide records"}
        target = None
        if pest:
            hits = cropqa.find(kb, pest, f.crop if f is not None else None) or cropqa.find(kb, pest)
            target = hits[0][0] if hits else None
        crop = kb.targets[target]["crop"] if target else (f.crop if f is not None else "rice")
        v = labelcheck.check(kb, ing, crop, target, lang)
        return {"product": v["product"], "verdict": v["title"], "message": v["message"],
                "go": [{"to": "/app/spray", "label": tr(cropqa.TEXT["go_spray"], lang)}]}

    def recipe(name: str) -> dict:
        prep = cropqa.prep_named(kb, name)
        if prep is None:
            return {"error": f"no home preparation called '{name}'"}
        f = field(None)
        out = cropqa.recipe_answer(kb, prep, lang, f.area_acres if f is not None else None)
        return {"text": out["text"], "lines": out["steps"]}

    def app_help(question: str) -> dict:
        idx = k.index()
        ranked = idx.rank(question, None)
        if not ranked or ranked[0][1] < k.MATCH_MIN:
            return {"error": "nothing in the app's help matches"}
        t = idx.topics[ranked[0][0]]
        if t.get("live"):
            return {"hint": f"use the {ranked[0][0]} lookup instead"}
        return {"topic": ranked[0][0], "text": tr(t["answer"], lang),
                "lines": k.trl(t["steps"], lang) if "steps" in t else [], "go": k._go(t.get("go", []), lang)}

    def harvest(field_no: int | None = None) -> dict:
        f = field(field_no)
        if f is None:
            return {"error": "no field is registered"}
        h = services.expected_harvest(kb, f, date.today())
        return {"field": own.index(f) + 1, "expected_harvest": h.on.isoformat(), "how_sure": h.confidence,
                "worked_out_from": h.basis}

    fields = "\n".join(k.facts(db, kb, user, own, lang).splitlines()) if user is not None else \
        "\n".join(f"Field {i}: {tr(kb.crops[f.crop]['names'], 'en')}, {f.area_acres} acres, {f.district}"
                  for i, f in enumerate(own, 1)) or "No field registered yet."
    F = {"field_no": {"type": "integer", "description": "the field number; leave out for the field on screen"}}
    tools = [
        Tool("field_today", "What to do in this field today: checks due, alerts, follow-ups.", F, [], live(k._today)),
        Tool("weather", "Weather now and the next 3 days at the field.", F, [], live(k._weather)),
        Tool("spray_window", "Whether now is a good time to spray, and the next good time.", F, [], live(k._spray),
             verbatim=True),
        Tool("irrigation", "Whether the field needs water now, from this week's rain and crop use.", F, [],
             live(k._water), verbatim=True),
        Tool("pest_risks", "Pests and diseases the weather and crop stage favour at the field now.", F, [],
             live(k._risks)),
        Tool("my_cases", "The farmer's reported problems on the field, expert answers and their status.", F, [],
             live(k._cases)),
        Tool("harvest", "When the field's crop is expected to be ready to harvest.", F, [], harvest),
        Tool("pest_advice", "What to do about a named pest or disease: organic options first (with amounts "
             "for the field), the registered chemical last, what not to do. want = control | organic | "
             "chemical | identify.",
             {"pest": {"type": "string"}, "want": {"type": "string"}, **F}, ["pest"], pest_advice),
        Tool("symptom_candidates", "Problems whose signs match a description of what the farmer sees.",
             {"description": {"type": "string"}, **F}, ["description"], symptom_candidates),
        Tool("spray_check", "Whether a product is registered for a crop and pest (the official register).",
             {"product": {"type": "string"}, "pest": {"type": "string"}, **F}, ["product"], spray_check),
        Tool("recipe", "How to make a home or natural-farming preparation (neemastra, agniastra, NSKE...).",
             {"name": {"type": "string"}}, ["name"], recipe),
        Tool("app_help", "How to use AnnRakshak: screens, photo checks, alerts, account, language.",
             {"question": {"type": "string"}}, ["question"], app_help),
    ]
    system = KRISHI_SYSTEM.format(today=date.today().isoformat(), current=current or 1, fields=fields,
                                  language=llm.LANG_NAME.get(lang, "English"))
    out = run(kb, system=system, question=question, tools=tools, shape="farmer")
    if out is None:
        return None
    # When to spray is the app's to say, not the model's. If the answer talks
    # about spraying at all, the spray window's own sentence for this field
    # leads, and any spraying claim the model wrote itself is taken out — it
    # once turned "not now, tomorrow 13:00" into "spray today 13:00–18:00".
    said = " ".join([out["text"], *out["steps"]]).lower()
    f = field(None)
    if f is not None and any(w in said for w in SPRAY_WORDS):
        window = k._spray(db, kb, f, lang).get("text")
        if window:
            keep = [p for p in out["steps"] if not any(w in p.lower() for w in SPRAY_WORDS)]
            text = out["text"] if not any(w in out["text"].lower() for w in SPRAY_WORDS) else window
            out["steps"] = ([window] if text != window else []) + [p for p in keep if p != window]
            out["text"] = text
    return {"topic": "assistant", "score": 1.0, "text": out["text"], "steps": out["steps"], "go": out["go"],
            "used": out["used"]}


# ==========================================================================
# Darpan: one officer, their districts
# ==========================================================================

DARPAN_SYSTEM = """You are Darpan, the assistant for agriculture officers and KVK experts in \
AnnRakshak, an Indian crop-protection app. Today is {today}. {who}

How to work:
- Look things up with the tools before answering, as many as the question needs: \
"brief me and tell me what to stock" needs the briefing and the stock lookup; \
"compare blast in Bhandara and Gondia" needs the pest lookup twice.
- Answer ONLY from what the tools returned. Never add a number, a name, a place or a \
product that a tool did not return. If the records do not have it, say so.
- Pass a district to a lookup only when the question names that district.
- Keep the numbers the lookups give — counts, this week against last, farms, places — \
in your lines; an answer without its numbers is no use to an officer.
- Be direct, like a deputy briefing their officer: the answer first, then the numbers \
behind it, then what to do next.
- Anything outside these records (prices, schemes, other states): say you only answer \
from this district's records.

Reply as JSON and nothing else: {{"lines": ["short line", "..."]}} — at most 8 lines, \
no markdown."""


def darpan(db, kb: KB, *, question: str, demo: bool, officer) -> dict | None:
    """Darpan's answer to `question` from the district's own records, or None."""
    from app import cropqa, darpan as d  # noqa: PLC0415

    def call(fn, **args):
        out = fn(db, kb, demo=demo, args={k: v for k, v in args.items() if v}, officer=officer, text=question)
        return {"lines": out.get("lines"), "go": out.get("go")}

    def district_arg(name: str | None) -> str | None:
        if not name:
            return None
        from sqlalchemy import select  # noqa: PLC0415
        from app.models import Farm  # noqa: PLC0415
        known = [x for (x,) in db.execute(select(Farm.district).distinct()).all() if x]
        return next((x for x in known if x.lower() == name.strip().lower()), None)

    def simple(fn):
        def tool(district: str | None = None) -> dict:
            return call(fn, district=district_arg(district))
        return tool

    def pest(pest: str, district: str | None = None) -> dict:
        hits = cropqa.find(kb, pest, cropqa.crop_named(pest)) or cropqa.find(kb, pest)
        if not hits:
            return {"error": f"no pest or disease called '{pest}'"}
        return call(d._pest, target=hits[0][0], district=district_arg(district))

    def farm(name: str) -> dict:
        out = d._farm(db, kb, demo=demo, args={}, officer=officer, text=name)
        return {"lines": out.get("lines"), "go": out.get("go")}

    D = {"district": {"type": "string", "description": "a district name; leave out for the officer's own"}}
    tools = [
        Tool("brief", "The whole district in one briefing: cases, overdue, what is building.", D, [], simple(d._brief)),
        Tool("queue", "Open and overdue expert cases.", D, [], simple(d._queue)),
        Tool("district", "How one district is doing: farms, cases, alerts and inspections.", D, [],
             simple(d._district)),
        Tool("building", "Pests and diseases building this week, by farms affected.", {}, [], simple(d._building)),
        Tool("pest", "One named pest or disease: reports this week vs last, expert confirmations, alerts, "
             "where it is, and what to advise.", {"pest": {"type": "string"}, **D}, ["pest"], pest),
        Tool("my_desk", "What is assigned to this officer.", {}, [], simple(d._mine)),
        Tool("officers", "Who is carrying what, who is free, who awaits verification.", {}, [], simple(d._officers)),
        Tool("performance", "How fast each officer answers and closes cases.", {}, [], simple(d._performance)),
        Tool("advisories", "Advisories this office issued and what came of them.", {}, [], simple(d._advisories)),
        Tool("trend", "This week against last: cases, alerts, verdicts.", {}, [], simple(d._trend)),
        Tool("rainfall", "Rain against the IMD normal.", D, [], simple(d._rainfall)),
        Tool("stock", "What bio-inputs to order, and by when.", {}, [], simple(d._inputs)),
        Tool("model", "How accurate the photo model has been in the field.", {}, [], simple(d._model)),
        Tool("gaps", "Problems the model cannot name yet.", {}, [], simple(d._gaps)),
        Tool("find_farmer", "One farmer or village by name.", {"name": {"type": "string"}}, ["name"], farm),
    ]
    me = d._me(db, officer, demo)
    who = (f"The officer is {officer.name}, covering {', '.join(me['districts'])}." if officer is not None and
           me.get("districts") else "The officer covers every district.")
    out = run(kb, system=DARPAN_SYSTEM.format(today=date.today().isoformat(), who=who), question=question,
              tools=tools, shape="officer")
    if out is None:
        return None
    return {"intent": "assistant", "lines": out["lines"], "go": out["go"], "used": out["used"], "asked": question}

