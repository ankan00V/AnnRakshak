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
    "mine": {
        "label": "what is on this officer's own desk",
        "says": ["what is on my desk", "my cases", "what do i have", "my queue", "what should i do next",
                 "mera kaam", "my work", "anything assigned to me"],
    },
    "brief": {
        "label": "the whole district in one briefing",
        "says": ["brief me", "morning briefing", "where do we stand", "summary", "catch me up",
                 "what do i need to know", "status", "aaj ka haal"],
    },
    "trend": {
        "label": "whether things are getting better or worse",
        "says": ["is it getting worse", "trend", "compared to last week", "are cases going up",
                 "better or worse", "this week vs last week", "pichle hafte se"],
    },
    "performance": {
        "label": "how each officer is actually doing",
        "says": ["how are my officers doing", "who is slow", "response time", "how fast are cases closed",
                 "officer performance", "turnaround"],
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

    # An example phrase routes to its own intent, always. Scoring strips filler
    # words, and some of these questions are nothing but filler: "what can you
    # do" is what, can, you and do, every one of them a stop word, so it scored
    # against nothing and fell through to the model — which answered correctly
    # wherever there was an API key, and left CI, an offline laptop and a
    # rate-limited morning answering "unknown" to the one question a new officer
    # is most likely to ask first.
    for intent, spec in INTENTS.items():
        if any(_norm(example) == t for example in spec["says"]):
            return intent, args

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


def _short_name(name: str | None) -> str | None:
    """What to call them. 'Dr. S. Kale' is greeted by surname; 'Demo expert'
    would be greeted as 'expert', which is nobody's name, so a short name is
    kept whole."""
    name = (name or "").strip()
    if not name:
        return None
    return name if len(name) <= 20 else name.split()[-1]


def _me(db: Session, officer: User | None, demo: bool) -> dict:
    """Who is asking, and what they are carrying.

    Darpan was given the officer from the first day and did nothing with it, so
    every answer read the same for a Bhandara reviewer and a state supervisor.
    An officer's own districts are the default scope of every answer below, and
    their own desk is a question they can ask outright."""
    blank = {"name": None, "last": None, "designation": None, "organisation": None,
             "districts": [], "crops": [], "specialities": [], "supervisor": False,
             "open": 0, "overdue": 0, "oldest_hours": None}
    if officer is None:
        return blank
    prof = db.get(ExpertProfile, officer.id)
    mine = db.execute(
        select(Case).join(Problem, Problem.id == Case.problem_id)
        .join(Farm, Farm.id == Problem.farm_id)
        .where(Case.assigned_to == officer.id, Case.status == "open", Farm.is_demo.is_(demo))
    ).scalars().all()
    now = datetime.now()
    waits = [(now - c.created_at).total_seconds() / 3600 for c in mine if c.created_at]
    return {
        "name": officer.name,
        "last": _short_name(officer.name),
        "designation": prof.designation if prof else None,
        "organisation": prof.organisation if prof else None,
        "districts": list(prof.districts or []) if prof else [],
        "crops": list(prof.crops or []) if prof else [],
        "specialities": list(prof.specialities or []) if prof else [],
        "supervisor": bool(prof and prof.supervisor),
        "open": len(mine),
        "overdue": sum(1 for h in waits if h > SLA_HOURS),
        "oldest_hours": max(waits) if waits else None,
    }


def _scope(args: dict, me: dict) -> tuple[list[str], str]:
    """Which districts an answer covers: the one named in the question, else the
    officer's own, else everywhere. Returned with how it was chosen, because an
    answer should say which patch of ground it is talking about."""
    if args.get("district"):
        return [args["district"]], "named"
    if me.get("districts"):
        return list(me["districts"]), "mine"
    return [], "all"


def _where(districts: list[str], how: str) -> str:
    """'In Bhandara and Gondia' — the phrase an answer opens with.

    A state-level officer covers all thirty-six, and naming them is a wall of
    text where a count is the useful thing. Three is where a list stops reading
    as a place and starts reading as a list."""
    if not districts:
        return "Across every district"
    if len(districts) == 1:
        return f"In {districts[0]}"
    if len(districts) <= 3:
        listed = ", ".join(districts[:-1]) + f" and {districts[-1]}"
        return f"In {listed}" + (" (your districts)" if how == "mine" else "")
    return f"Across your {len(districts)} districts" if how == "mine" else f"Across {len(districts)} districts"


def _elsewhere(db: Session, demo: bool, districts: list[str], shown: int) -> str | None:
    """Narrowing an answer to an officer's districts must not make a case
    disappear. Whatever is open outside them is still counted, and said."""
    if not districts:
        return None
    total = len(_open_cases(db, demo))
    rest = total - shown
    if rest <= 0:
        return None
    return (f"{rest} more open case{'s' if rest != 1 else ''} outside your districts "
            "— ask about one by name.")


def _link(label: str, to: str) -> dict:
    return {"label": label, "to": to}


def answer(db: Session, kb: KB, *, text: str, demo: bool, officer: User | None) -> dict:
    """One answer: lines an officer can read out, and the links behind them."""
    intent, args = route(text, db)
    fn = {
        "queue": _queue, "district": _district, "building": _building, "advisories": _advisories,
        "officers": _officers, "model": _model, "gaps": _gaps, "inputs": _inputs,
        "rainfall": _rainfall, "farm": _farm, "mine": _mine, "brief": _brief,
        "trend": _trend, "performance": _performance, "help": _help,
    }.get(intent)
    if fn is None:
        return {"intent": "unknown", "lines": [CANNOT],
                "go": [_link("What Darpan can answer", "/officer")], "asked": text}
    out = fn(db, kb, demo=demo, args=args, officer=officer, text=text)
    return {"intent": intent, "asked": text, **out}


# --------------------------------------------------------------------------
# One function per intent. Each reads the same rows the screens read.
# --------------------------------------------------------------------------

def _farms(db: Session, demo: bool, districts: list[str] | str | None = None) -> list[Farm]:
    q = select(Farm).where(Farm.is_demo.is_(demo))
    names = [districts] if isinstance(districts, str) else (districts or [])
    if names:
        q = q.where(Farm.district.in_(names))
    return list(db.scalars(q).all())


def _open_cases(db: Session, demo: bool, districts: list[str] | str | None = None):
    q = (select(Case, Farm).join(Problem, Problem.id == Case.problem_id)
         .join(Farm, Farm.id == Problem.farm_id)
         .where(Case.status == "open", Farm.is_demo.is_(demo)))
    names = [districts] if isinstance(districts, str) else (districts or [])
    if names:
        q = q.where(Farm.district.in_(names))
    return db.execute(q).all()


def _queue(db, kb, *, demo, args, officer, text):
    me = _me(db, officer, demo)
    districts, how = _scope(args, me)
    rows = _open_cases(db, demo, districts)
    now = datetime.now()
    overdue = [c for c, _ in rows if c.created_at and (now - c.created_at) > timedelta(hours=SLA_HOURS)]
    unrouted = [c for c, _ in rows if c.assigned_to is None]
    by_district = Counter(f.district for _, f in rows)
    lines = [f"{_where(districts, how)}: {len(rows)} open case{'s' if len(rows) != 1 else ''}"
             + (f", spread over {len(by_district)} districts." if len(by_district) > 1 else ".")]
    if me["open"]:
        lines.append(f"{me['open']} of them {'is' if me['open'] == 1 else 'are'} yours"
                     + (f", {me['overdue']} past {SLA_HOURS} hours." if me["overdue"] else "."))
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
    if by_district and len(by_district) > 1:
        top = ", ".join(f"{d} ({n})" for d, n in by_district.most_common(3))
        lines.append(f"Heaviest: {top}.")
    elsewhere = _elsewhere(db, demo, districts, len(rows))
    if elsewhere:
        lines.append(elsewhere)
    here = f"?district={districts[0]}" if how == "named" and districts else ""
    go = [_link("Open the queue", f"/officer/queue{here}")]
    if me["open"]:
        go.append(_link(f"Your {me['open']}", "/officer/queue?scope=mine"))
    if overdue:
        go.append(_link(f"The {len(overdue)} overdue", "/officer/queue?overdue=1"))
    if unrouted:
        go.append(_link(f"{len(unrouted)} unassigned", "/officer/queue?scope=unassigned"))
    return {"lines": lines, "go": go}


def _district(db, kb, *, demo, args, officer, text):
    me = _me(db, officer, demo)
    name = args.get("district") or (me["districts"][0] if len(me["districts"]) == 1 else None)
    if not name:
        listed = sorted({f.district for f in _farms(db, demo, me["districts"])})
        known = me["districts"] or listed[:12]
        return {"lines": ["Which district? " + ("Yours are: " if me["districts"] else "I know: ")
                          + ", ".join(known) + "."],
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
    """Who is free, who is loaded, who is waiting to be let in — the district's
    staffing, which is a supervisor's business. An officer asking gets their
    own desk instead, which is what they can actually act on."""
    if not services.is_supervisor(db, officer):
        return _mine(db, kb, demo=demo, args=args, officer=officer, text=text)
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
    """The monsoon normal where this officer works. It used to read out the
    first four subdivisions in the file, which are Maharashtra's, to an officer
    anywhere in the country."""
    normals = services.rainfall_normals()
    to_sub = normals.get("district_to_subdivision", {})
    prof = db.get(ExpertProfile, officer.id) if officer else None
    mine = list(prof.districts or []) if prof else []
    subs = sorted({to_sub[d] for d in mine if d in to_sub})
    if mine and not subs:
        where = ", ".join(sorted(mine)[:4])
        return {"lines": [f"The IMD subdivision normals do not cover {where} yet — they map "
                          "Maharashtra's districts so far. The risk rules still read live weather "
                          "at every field."],
                "go": []}
    lines = [f"· {sub.title()}: {normals['subdivisions'][sub]['mean'].get('jjas', '—')} mm is the "
             "1901–2015 monsoon normal." for sub in (subs or list(normals.get("subdivisions", {}))[:4])]
    return {"lines": ["Rain against the IMD normal, which is what the risk rules read:"] + lines,
            "go": []}


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


def _mine(db, kb, *, demo, args, officer, text):
    """This officer's own desk — the question they ask before any other."""
    me = _me(db, officer, demo)
    if officer is None:
        return {"lines": ["I do not know who is asking."], "go": [_link("Queue", "/officer/queue")]}
    districts, how = _scope(args, me)
    rows = _open_cases(db, demo, districts)
    unrouted = [c for c, _ in rows if c.assigned_to is None]
    lines = []
    if me["open"]:
        oldest = round((me["oldest_hours"] or 0) / 24)
        waited = (f", the oldest waiting {oldest} day{'s' if oldest != 1 else ''}"
                  if (me["oldest_hours"] or 0) > 48 else "")
        lines.append(f"{me['open']} case{'s' if me['open'] != 1 else ''} on your desk{waited}.")
        if me["overdue"]:
            lines.append(f"{me['overdue']} of them {'is' if me['overdue'] == 1 else 'are'} past the "
                         f"{SLA_HOURS}-hour mark — those first.")
        else:
            lines.append(f"None of them is past {SLA_HOURS} hours yet.")
    else:
        lines.append("Nothing is assigned to you.")
    if unrouted:
        lines.append(f"{len(unrouted)} case{'s' if len(unrouted) != 1 else ''} in "
                     f"{_where(districts, how).lower().removeprefix('in ')} "
                     f"{'is' if len(unrouted) == 1 else 'are'} on nobody's desk.")
    if me["supervisor"]:
        pending = office.pending_officers(db, demo=demo)
        if pending:
            lines.append(f"{len(pending)} officer{'s' if len(pending) != 1 else ''} waiting for you to verify.")
    go = [_link("My queue", "/officer/queue?scope=mine")]
    if me["overdue"]:
        go.append(_link("My overdue", "/officer/queue?scope=mine&overdue=1"))
    if unrouted:
        go.append(_link("Unassigned", "/officer/queue?scope=unassigned"))
    return {"lines": lines, "go": go}


def _brief(db, kb, *, demo, args, officer, text):
    """Everything an officer would otherwise open five screens to learn."""
    me = _me(db, officer, demo)
    districts, how = _scope(args, me)
    rows = _open_cases(db, demo, districts)
    now = datetime.now()
    overdue = [c for c, _ in rows if c.created_at and (now - c.created_at) > timedelta(hours=SLA_HOURS)]
    opening = f"{_where(districts, how)}, {len(rows)} case{'s' if len(rows) != 1 else ''} open"
    lines = [opening + (f", {len(overdue)} overdue." if overdue else ", none overdue.")]
    if me["open"]:
        lines.append(f"Yours: {me['open']}" + (f", {me['overdue']} overdue." if me["overdue"] else "."))
    outside = _elsewhere(db, demo, districts, len(rows))
    if outside:
        lines.append(outside)

    work = office.worklist(db, kb, demo=demo)
    building = work.get("building") or []
    if building:
        top = building[:2]
        lines.append("Building: " + "; ".join(
            f"{b['name']} on {b['farms']} farm{'s' if b['farms'] != 1 else ''}" for b in top) + ".")
    else:
        lines.append("Nothing is building: no high alert in the last seven days.")

    sent = office.history(db, demo=demo, limit=10)
    unchecked = [r for r in sent if not r["inspected"]]
    if sent:
        lines.append(f"{len(unchecked)} of the last {len(sent)} advisories "
                     f"{'has' if len(unchecked) == 1 else 'have'} had no response."
                     if unchecked else "Every recent advisory has been inspected by someone.")
    if me["supervisor"]:
        pending = office.pending_officers(db, demo=demo)
        if pending:
            lines.append(f"{len(pending)} officer{'s' if len(pending) != 1 else ''} waiting to be verified.")

    go = [_link("Today", "/officer")]
    if overdue:
        go.append(_link(f"{len(overdue)} overdue", "/officer/queue?overdue=1"))
    if building:
        b = building[0]
        go.append(_link(f"Advise on {b['name']}", f"/officer/advisories?target={b['target']}&crop={b['crop']}"))
    return {"lines": lines, "go": go}


def _trend(db, kb, *, demo, args, officer, text):
    """A number without a direction is a poster — this week against the last."""
    t = office.trends(db, demo=demo)

    def say(what: str, part: dict) -> str:
        change = part.get("change_pct")
        if change is None:
            return f"{what}: {part['this_week']} this week, none the week before."
        way = "up" if change > 0 else "down" if change < 0 else "level"
        return (f"{what}: {part['this_week']} this week against {part['last_week']} "
                f"— {way}{f' {abs(change)}%' if change else ''}.")

    lines = [say("Cases", t["cases"]), say("Alerts issued", t["alerts"]), say("Expert verdicts", t["verdicts"])]
    rising = t["cases"].get("change_pct")
    if rising and rising > 25:
        lines.append("Cases are climbing faster than last week — worth a look at what is building.")
    return {"lines": lines, "go": [_link("Today", "/officer"), _link("What is building", "/officer/advisories")]}


def _performance(db, kb, *, demo, args, officer, text):
    """How desks are doing: what they cleared and how long it took. Named
    colleagues, so: supervisors. Anyone else is told about their own."""
    if not services.is_supervisor(db, officer):
        return _mine(db, kb, demo=demo, args=args, officer=officer, text=text)
    rows = office.performance(db, demo=demo)
    done = [r for r in rows if r.get("resolved")]
    if not done:
        return {"lines": ["No case has been resolved yet, so there is nothing to measure."],
                "go": [_link("Officers", "/officer/officers")]}
    lines = []
    for r in sorted(done, key=lambda r: -(r.get("resolved") or 0))[:4]:
        median = r.get("median_hours")
        pace = f", median {round(median)} h on the desk" if median else ""
        lines.append(f"· {r['name']}: {r['resolved']} resolved{pace}.")
    slowest = max(done, key=lambda r: r.get("median_hours") or 0)
    if (slowest.get("median_hours") or 0) > SLA_HOURS:
        lines.append(f"{slowest['name']}'s cases sit longest — median "
                     f"{round(slowest['median_hours'])} hours, past the {SLA_HOURS}-hour mark.")
    return {"lines": ["What desks have cleared:"] + lines,
            "go": [_link("Officers", "/officer/officers")]}


def _help(db, kb, *, demo, args, officer, text):
    me = _me(db, officer, demo)
    mine = (f" Your districts are {', '.join(me['districts'])}, and that is what I answer about "
            "unless you name another.") if me["districts"] else ""
    return {"lines": [GREETING + mine,
                      "Try: “brief me”, “what is on my desk”, “what is building”, "
                      "“how is Bhandara”, “who is free”, “what should I order”."],
            "go": [_link("Today", "/officer"), _link("Queue", "/officer/queue")]}


def hello(db: Session, officer: User | None, *, demo: bool = False) -> dict:
    """The greeting and the questions worth starting from.

    The greeting carries the two numbers an officer opens the panel to find —
    what is waiting, and how much of it is theirs — so the first useful thing
    arrives before they have typed anything."""
    me = _me(db, officer, demo)
    districts, how = _scope({}, me)
    rows = _open_cases(db, demo, districts)
    now = datetime.now()
    overdue = sum(1 for c, _ in rows if c.created_at and (now - c.created_at) > timedelta(hours=SLA_HOURS))

    who = f", {me['last']}" if me["last"] else ""
    if not me["districts"]:
        where = None
    elif len(me["districts"]) <= 3:
        where = ", ".join(me["districts"])
    else:
        where = f"All {len(me['districts'])} of your districts"
    opening = f"Darpan here{who}." + (f" {where}, as it stands." if where else " Your district, as it stands.")
    standing = (f"{len(rows)} case{'s' if len(rows) != 1 else ''} open"
                + (f", {overdue} past {SLA_HOURS} hours" if overdue else ", none overdue")
                + (f"; {me['open']} on your desk." if me["open"] else "."))

    suggestions = [
        {"label": "Brief me", "text": "brief me"},
        {"label": "What is on my desk?", "text": "what is on my desk"},
        {"label": "What is building?", "text": "what is building this week"},
        {"label": "Who is free?", "text": "who is free"},
        {"label": "Did anyone check the advisory?", "text": "did anyone check the advisory"},
    ]
    if me["districts"]:
        suggestions.insert(2, {"label": f"How is {me['districts'][0]}?",
                               "text": f"how is {me['districts'][0]} doing"})
    # Six fit in the panel. A supervisor's own question is one of them, not the
    # one trimmed off the end.
    if me["supervisor"]:
        suggestions = suggestions[:5] + [
            {"label": "Anyone waiting to be verified?", "text": "anyone waiting for verification"}]
    return {"greeting": f"{opening} {standing}", "suggestions": suggestions[:6]}
