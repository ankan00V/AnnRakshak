"""Darpan, the district's own assistant.

दर्पण — a mirror. Krishi answers a farmer about their field and is not touched
by anything here; Darpan answers an officer about their district, and only an
officer ever reaches it.

The promise is Krishi's promise: it does not invent. Every sentence Darpan says
is built from a number this server has just computed — open cases, what is
building, who is carrying what, what an advisory achieved — and every answer
carries the link that takes the officer to the screen those numbers came from.
A question it cannot answer is answered with what it can, never with a guess.

A language model is used for one job, as in Krishi: reading what was typed and
naming one of the intents below. The reply is checked against that closed list
before it is used, so the worst a misread can do is open the wrong screen.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import llm, office, services
from app.kb import KB, tr
from app.models import Alert, Case, Confirmation, ExpertProfile, Farm, Problem, User

SLA_HOURS = office.SLA_HOURS

# Each intent: what an officer might type, and what Darpan does about it. The
# examples are also what the model is shown when it is asked to route.
INTENTS: dict[str, dict] = {
    "queue": {
        "label": "the state of the queue",
        "says": ["how is the queue", "how many cases are open", "what is overdue", "anything waiting",
                 "pending cases", "backlog", "kitne case pending hai"],
    },
    "district": {
        "label": "how one district is doing",
        "says": ["how is bhandara doing", "status of gondia", "cases in yavatmal", "district report",
                 "what is happening in", "bhandara ka haal"],
    },
    "building": {
        "label": "what is building this week",
        "says": ["what is building", "which pest is rising", "what should i worry about",
                 "outbreak", "risk this week", "kaunsa keeda badh raha hai"],
    },
    "advisories": {
        "label": "what the office has issued and what came of it",
        "says": ["what did we send", "advisories issued", "did anyone check the advisory",
                 "was the advisory useful", "advisory history"],
    },
    "officers": {
        "label": "who is carrying what, and who is waiting to be verified",
        "says": ["who is free", "who has the most cases", "officer load", "staff",
                 "anyone waiting for verification", "kaun free hai"],
    },
    "model": {
        "label": "how the model is doing in the field",
        "says": ["how accurate is the model", "model performance", "gate", "is the ai right",
                 "confidence", "accuracy"],
    },
    "gaps": {
        "label": "problems the model cannot name yet",
        "says": ["what can the model not name", "unknown problems", "gaps", "something else cases",
                 "training backlog"],
    },
    "inputs": {
        "label": "what to stock, and by when",
        "says": ["what should i order", "stock", "tricho cards", "bio inputs", "indent", "procurement"],
    },
    "rainfall": {
        "label": "rain against the IMD normal",
        "says": ["how is the rain", "rainfall", "is it a dry year", "monsoon", "barish"],
    },
    "farm": {
        "label": "one farmer or village",
        "says": ["find sunita", "which farm", "show me the farmer", "village", "farmer detail"],
    },
    "help": {
        "label": "what Darpan can answer",
        "says": ["help", "what can you do", "who are you", "darpan"],
    },
}

GREETING = "Darpan — your district, as it stands. Ask about the queue, what is building, your officers, or an advisory you sent."

CANNOT = ("I only answer from this district's own records. I can tell you about "
          "the queue, what is building this week, your officers, advisories you have "
          "issued, the model's field accuracy, what to stock, and the rain against normal.")


# Words that carry no intent. Without this, "what is the price of urea in
# nagpur" scores against "what is happening in …" on three filler words and is
# answered as a question about a district.
STOP = {
    "a", "an", "and", "any", "are", "as", "at", "be", "can", "did", "do", "does", "for", "from",
    "give", "has", "have", "how", "i", "in", "is", "it", "me", "much", "my", "of", "on", "or",
    "our", "please", "show", "so", "tell", "that", "the", "there", "this", "to", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "why", "with", "you", "your",
    "hai", "kya", "ka", "ki", "ke", "mera", "kitne",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9ऀ-ॿ ]+", " ", (text or "").lower()).strip()


def _content(text: str) -> set[str]:
    """The words that actually say what is being asked."""
    return {w for w in _norm(text).split() if w not in STOP and len(w) > 1}


def route(text: str, db: Session) -> tuple[str, dict]:
    """The intent, and anything named in the question (a district, a farmer).

    Keyword first, because the common questions should not wait on a network
    call; the model is asked only when nothing matches well."""
    t = _norm(text)
    args: dict = {}

    districts = [d for (d,) in db.execute(select(Farm.district).distinct()).all() if d]
    for d in districts:
        if d and _norm(d) in t:
            args["district"] = d
            break

    asked = _content(text)
    scores = Counter()
    for intent, spec in INTENTS.items():
        for example in spec["says"]:
            words = _content(example)
            if not words:
                continue
            hit = len(words & asked)
            if hit:
                scores[intent] = max(scores[intent], hit / len(words))

    if args.get("district") and not scores:
        return "district", args
    if scores:
        best, score = scores.most_common(1)[0]
        if score >= 0.5:
            return best, args

    # Nothing obvious: let the model name one of the intents, and check its reply
    # against the closed list before trusting it.
    if llm.enabled():
        picked = llm.route(text, [(k, v["label"]) for k, v in INTENTS.items()])
        if picked in INTENTS:
            return picked, args
    return ("district" if args.get("district") else "unknown"), args


def _link(label: str, to: str) -> dict:
    return {"label": label, "to": to}


def answer(db: Session, kb: KB, *, text: str, demo: bool, officer: User | None) -> dict:
    """One answer: lines an officer can read out, and the links behind them."""
    intent, args = route(text, db)
    fn = {
        "queue": _queue, "district": _district, "building": _building, "advisories": _advisories,
        "officers": _officers, "model": _model, "gaps": _gaps, "inputs": _inputs,
        "rainfall": _rainfall, "farm": _farm, "help": _help,
    }.get(intent)
    if fn is None:
        return {"intent": "unknown", "lines": [CANNOT],
                "go": [_link("What Darpan can answer", "/officer")], "asked": text}
    out = fn(db, kb, demo=demo, args=args, officer=officer, text=text)
    return {"intent": intent, "asked": text, **out}


# --------------------------------------------------------------------------
# One function per intent. Each reads the same rows the screens read.
# --------------------------------------------------------------------------

def _farms(db: Session, demo: bool, district: str | None = None) -> list[Farm]:
    q = select(Farm).where(Farm.is_demo.is_(demo))
    if district:
        q = q.where(Farm.district == district)
    return list(db.scalars(q).all())


def _open_cases(db: Session, demo: bool, district: str | None = None):
    q = (select(Case, Farm).join(Problem, Problem.id == Case.problem_id)
         .join(Farm, Farm.id == Problem.farm_id)
         .where(Case.status == "open", Farm.is_demo.is_(demo)))
    if district:
        q = q.where(Farm.district == district)
    return db.execute(q).all()


def _queue(db, kb, *, demo, args, officer, text):
    rows = _open_cases(db, demo)
    now = datetime.now()
    overdue = [c for c, _ in rows if c.created_at and (now - c.created_at) > timedelta(hours=SLA_HOURS)]
    unrouted = [c for c, _ in rows if c.assigned_to is None]
    by_district = Counter(f.district for _, f in rows)
    lines = [f"{len(rows)} open case{'s' if len(rows) != 1 else ''} across {len(by_district)} district"
             f"{'s' if len(by_district) != 1 else ''}."]
    if overdue:
        oldest = max(overdue, key=lambda c: now - c.created_at)
        hours = (now - oldest.created_at).total_seconds() / 3600
        lines.append(f"{len(overdue)} past the {SLA_HOURS}-hour mark — the oldest, case #{oldest.id}, "
                     f"has waited {round(hours / 24)} days." if hours > 48 else
                     f"{len(overdue)} past the {SLA_HOURS}-hour mark; the oldest is case #{oldest.id}.")
    else:
        lines.append("Nothing is past the 24-hour mark.")
    if unrouted:
        lines.append(f"{len(unrouted)} are on nobody's desk.")
    if by_district:
        top = ", ".join(f"{d} ({n})" for d, n in by_district.most_common(3))
        lines.append(f"Heaviest: {top}.")
    go = [_link("Open the queue", "/officer/queue")]
    if overdue:
        go.append(_link(f"The {len(overdue)} overdue", "/officer/queue?overdue=1"))
    return {"lines": lines, "go": go}


def _district(db, kb, *, demo, args, officer, text):
    name = args.get("district")
    if not name:
        listed = sorted({f.district for f in _farms(db, demo)})
        return {"lines": ["Which district? I know: " + ", ".join(listed[:12]) + "."],
                "go": [_link("District table", "/officer/map")]}
    farms = _farms(db, demo, name)
    rows = _open_cases(db, demo, name)
    since = date.today() - timedelta(days=7)
    farm_ids = {f.id for f in farms}
    alerts = [a for a in db.scalars(select(Alert).where(Alert.issued_on >= since)).all()
              if a.farm_id in farm_ids]
    high = [a for a in alerts if a.level == "high"]
    pests = Counter(tr(kb.targets[a.target]["names"], "en") for a in high if a.target in kb.targets)
    lines = [f"{name}: {len(farms)} farm{'s' if len(farms) != 1 else ''} monitored, "
             f"{len(rows)} case{'s' if len(rows) != 1 else ''} open."]
    if high:
        lines.append(f"{len(high)} high alerts in the last seven days"
                     + (f", mostly {pests.most_common(1)[0][0]}." if pests else "."))
    else:
        lines.append("No high alert there in the last seven days.")
    answered = [a for a in alerts if a.outcome in ("found", "nothing_found")]
    if alerts:
        lines.append(f"{len(answered)} of {len(alerts)} alerts have been inspected"
                     + (f", {sum(1 for a in answered if a.outcome == 'found')} found something." if answered else "."))
    return {"lines": lines, "go": [
        _link(f"{name}'s queue", f"/officer/queue?district={name}"),
        _link("Advise this district", f"/officer/advisories?district={name}"),
    ]}


def _building(db, kb, *, demo, args, officer, text):
    work = office.worklist(db, kb, demo=demo)
    if not work["building"]:
        return {"lines": ["Nothing is building: no high alert in the last seven days."],
                "go": [_link("Risk outlook", "/officer/advisories")]}
    lines = ["Building this week:"]
    lines += [f"· {b['name']} ({b['crop']}) on {b['farms']} farm{'s' if b['farms'] != 1 else ''}"
              for b in work["building"][:5]]
    top = work["building"][0]
    return {"lines": lines, "go": [
        _link(f"Advise on {top['name']}", f"/officer/advisories?target={top['target']}&crop={top['crop']}"),
        _link("What to stock", "/officer/inputs"),
    ]}


def _advisories(db, kb, *, demo, args, officer, text):
    rows = office.history(db, demo=demo, limit=10)
    if not rows:
        return {"lines": ["This office has not issued an advisory yet."],
                "go": [_link("Issue one", "/officer/advisories")]}
    lines = []
    for r in rows[:4]:
        where = ", ".join(r["districts"]) if r["districts"] else "every district"
        checked = (f"{r['inspected']} checked, {r['found']} found it" if r["inspected"]
                   else "nobody has checked yet")
        lines.append(f"· {r['target'].replace('_', ' ')} in {where} — {r['farms']} farms, {checked}.")
    unchecked = sum(1 for r in rows if not r["inspected"])
    if unchecked:
        lines.append(f"{unchecked} of the last {len(rows)} have had no response at all.")
    return {"lines": ["What the office has sent:"] + lines,
            "go": [_link("Advisories", "/officer/advisories")]}


def _officers(db, kb, *, demo, args, officer, text):
    load = services.workload(db, demo=demo)
    pending = office.pending_officers(db, demo=demo)
    carrying = sorted([o for o in load if o["open_cases"]], key=lambda o: -o["open_cases"])
    lines = []
    if carrying:
        busiest = carrying[0]
        lines.append(f"{busiest['name']} is carrying the most: {busiest['open_cases']} open"
                     + (f", oldest waiting {round(busiest['oldest_wait_hours'] / 24)} days."
                        if busiest["oldest_wait_hours"] and busiest["oldest_wait_hours"] > 48 else "."))
        idle = [o for o in load if not o["open_cases"]]
        lines.append(f"{len(idle)} officer{'s' if len(idle) != 1 else ''} hold nothing.")
    else:
        lines.append("Every desk is clear.")
    if pending:
        lines.append(f"{len(pending)} waiting to be verified: "
                     + ", ".join(o["name"] for o in pending[:3]) + ".")
    return {"lines": lines, "go": [_link("Officers", "/officer/officers")]}


def _model(db, kb, *, demo, args, officer, text):
    from app.engine import vision  # noqa: PLC0415  (loads the model card lazily)

    meta = vision.model_card() if hasattr(vision, "model_card") else {}
    gate = meta.get("gate_on_test") or {}
    confs = db.execute(
        select(Confirmation.verdict, func.count(Confirmation.id))
        .join(Problem, Problem.id == Confirmation.problem_id)
        .join(Farm, Farm.id == Problem.farm_id)
        .where(Farm.is_demo.is_(demo)).group_by(Confirmation.verdict)
    ).all()
    counts = {v: n for v, n in confs}
    lines = []
    if gate:
        lines.append(f"On held-out photos the gate advised on {gate.get('advise_pct')}% and was right "
                     f"{round((gate.get('accuracy_when_advised') or 0) * 100, 1)}% of those times; "
                     f"{gate.get('escalate_pct')}% came to you.")
    agreed, corrected = counts.get("confirmed", 0), counts.get("corrected", 0)
    if agreed + corrected:
        lines.append(f"In the field your officers have confirmed {agreed} and corrected {corrected} "
                     f"— and they only see what the gate was unsure about.")
    else:
        lines.append("No field verdict has been filed yet, so there is no field accuracy to report.")
    return {"lines": lines or ["The model card is not loaded on this machine."],
            "go": [_link("Model and gaps", "/officer/model")]}


def _gaps(db, kb, *, demo, args, officer, text):
    rows = office.gaps(db, demo=demo)
    if not rows:
        return {"lines": ["Nothing yet: every case so far fitted a problem the knowledge base knows."],
                "go": [_link("Model and gaps", "/officer/model")]}
    lines = [f"{len(rows)} case{'s' if len(rows) != 1 else ''} closed as something the model cannot name:"]
    lines += [f"· {r['district']} · {r['crop']} — “{(r['note'] or '').strip()[:90]}”" for r in rows[:4]]
    return {"lines": lines, "go": [_link("The whole list", "/officer/model")]}


def _inputs(db, kb, *, demo, args, officer, text):
    rows = office.indent(db, kb, demo=demo)
    if not rows:
        return {"lines": ["Nothing is building, so there is nothing to order."],
                "go": [_link("Inputs", "/officer/inputs")]}
    lines = ["To stock for what is building:"]
    for r in rows[:3]:
        for s in r["suggested"][:2]:
            by = f", order by {s['order_by']}" if s.get("order_by") else ""
            lines.append(f"· {r['name']}: {s['quantity']} of {s['input']}{by}.")
    if len(lines) == 1:
        lines.append("No ICAR input is listed against the problems building this week.")
    return {"lines": lines, "go": [_link("Inputs", "/officer/inputs")]}


def _rainfall(db, kb, *, demo, args, officer, text):
    normals = services.rainfall_normals()
    lines = []
    for sub in list(normals.get("subdivisions", {}))[:4]:
        lines.append(f"· {sub.title()}: {normals['subdivisions'][sub]['mean'].get('jjas', '—')} mm is the "
                     "1901–2015 monsoon normal.")
    return {"lines": ["Rain against the IMD normal is on the Reference screen; the risk rules read the "
                      "same numbers."] + lines,
            "go": [_link("Reference", "/officer/reference")]}


def _farm(db, kb, *, demo, args, officer, text):
    words = [w for w in _norm(text).split() if len(w) > 2]
    farms = _farms(db, demo)
    hits = [f for f in farms
            if any(w in _norm(f.farmer_name or "") or w in _norm(f.village or "") for w in words)]
    if not hits:
        return {"lines": ["I could not find a farmer or village by that name."],
                "go": [_link("Search the queue", "/officer/queue")]}
    lines = [f"{len(hits)} match{'es' if len(hits) != 1 else ''}:"]
    lines += [f"· {f.farmer_name} — {f.crop}, {f.village or f.district}" for f in hits[:5]]
    return {"lines": lines,
            "go": [_link(f"Open {hits[0].farmer_name}'s field", f"/officer/farm/{hits[0].id}")]}


def _help(db, kb, *, demo, args, officer, text):
    return {"lines": [GREETING, "Try: “what is building”, “how is Bhandara”, “who is free”, "
                      "“did anyone check the advisory”, “what should I order”."],
            "go": [_link("Today", "/officer"), _link("Queue", "/officer/queue")]}


def hello(officer: User | None) -> dict:
    """The greeting and the questions worth starting from."""
    name = (officer.name.split()[-1] if officer and officer.name else None)
    return {
        "greeting": f"Darpan here{', ' + name if name else ''}. Your district, as it stands.",
        "suggestions": [
            {"label": "How is the queue?", "text": "how is the queue"},
            {"label": "What is building?", "text": "what is building this week"},
            {"label": "Who is free?", "text": "who is free"},
            {"label": "Did anyone check the advisory?", "text": "did anyone check the advisory"},
            {"label": "What should I order?", "text": "what should i order"},
        ],
    }
