"""Knowledge base: crops, targets, advisories, Doubt Doctor cues, risk rules,
pesticide registry, and the ICAR technologies linked to them. Loaded once and validated as a whole — a KB with one bad
entry is refused entirely, because a partially loaded KB silently drops advice
and nothing downstream would notice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.config import KB_DIR
from app.i18n import AUTHORED, lookup, lookup_reviewed

LANGS = ("en", "hi", "mr")
TIER_ORDER = {"cultural": 0, "biological": 1, "chemical": 2}
MIN_TASKS = 2
TECH_TYPES = ("biocontrol", "variety", "practice", "monitoring", "app", "reference")
TECH_AUDIENCES = ("farmer", "official")


class KBError(ValueError):
    pass


def tr(text: dict | str | None, lang: str) -> str:
    """Pick a language. Authored languages come from the dict; the machine-
    translated ones from the reviewed translation memory (app.i18n), keyed by
    the English. English is the only fallback — never another language's text
    silently mislabelled."""
    if text is None:
        return ""
    if isinstance(text, str):
        return text
    if text.get(lang):
        return text[lang]
    en = text.get("en", "")
    if lang not in AUTHORED and isinstance(en, str):
        return lookup(en, lang) or en
    return en


def tr_reviewed(text: dict, lang: str) -> str:
    """tr() for safety-critical text: an authored language from the dict, a
    machine-translated one only after a native speaker approved it, otherwise
    the English."""
    if text.get(lang):
        return text[lang]
    en = text.get("en", "")
    return (lookup_reviewed(en, lang) or en) if lang not in AUTHORED else en


def trl(texts: dict | None, lang: str) -> list[str]:
    """tr() for per-language lists (inspection tasks, what-to-do steps)."""
    if not texts:
        return []
    if texts.get(lang):
        return list(texts[lang])
    en = list(texts.get("en", []))
    if lang not in AUTHORED:
        return [lookup(x, lang) or x for x in en]
    return en


@dataclass
class KB:
    crops: dict
    targets: dict[str, dict]
    advisories: dict[str, dict]
    cues: list[dict]
    rules: dict[str, dict]
    pesticides: dict[str, dict]
    institutes: dict[str, dict] = field(default_factory=dict)
    technologies: list[dict] = field(default_factory=list)
    agromet: dict = field(default_factory=dict)
    _cue_index: dict[frozenset, dict] = field(default_factory=dict)

    # --- lookups ---------------------------------------------------------

    def cue_for(self, a: str, b: str) -> dict | None:
        return self._cue_index.get(frozenset((a, b)))

    def stage_for(self, crop: str, sowing: date, today: date | None = None) -> tuple[str, int]:
        das = ((today or date.today()) - sowing).days
        stages = self.crops[crop]["stages"]
        for s in stages:
            lo, hi = s["das"]
            if lo <= das <= hi:
                return s["key"], das
        return (stages[0]["key"] if das < 0 else stages[-1]["key"]), das

    def stage_name(self, crop: str, key: str, lang: str) -> str:
        for s in self.crops[crop]["stages"]:
            if s["key"] == key:
                return tr(s["names"], lang)
        return key

    def target_view(self, target_id: str, lang: str) -> dict:
        t = self.targets[target_id]
        return {
            "id": target_id,
            "crop": t["crop"],
            "kind": t["kind"],
            "tier": t["tier"],
            "name": tr(t["names"], lang),
            "signature": tr(t["signature"], lang),
            "agent": t.get("agent"),
            "trap_etl": (self.rules.get(target_id, {}).get("trap") or {}).get("etl_per_trap_night"),
        }

    def match_pesticide(self, query: str) -> str | None:
        q = query.strip().lower()
        if not q:
            return None
        if q in self.pesticides:
            return q
        for pid, p in self.pesticides.items():
            names = [p["name"].lower(), *[a.lower() for a in p.get("aliases", [])]]
            if any(q == n or q in n or n in q for n in names):
                return pid
        return None

    def technologies_for(
        self, *, target: str | None = None, crop: str | None = None, audience: str | None = None
    ) -> list[dict]:
        """ICAR technologies linked to a target (or, with crop only, to the crop).
        audience='farmer' leaves out items meant for officials."""
        out = []
        for t in self.technologies:
            if target is not None and target not in t["targets"]:
                continue
            if crop is not None and crop not in t["crops"]:
                continue
            if audience == "farmer" and t["audience"] != "farmer":
                continue
            out.append(t)
        return out

    def tech_view(self, t: dict, lang: str) -> dict:
        inst = self.institutes[t["institute"]]
        view = {
            "id": t["id"],
            "type": t["type"],
            "audience": t["audience"],
            "short": t["short"],
            "source_name": t["source_name"],
            "summary": tr(t["summary"], lang),
            "claim": tr(t.get("claim"), lang) or None,
            "supply": tr(t.get("supply"), lang) or None,
            "link_reason": tr(t.get("link_reason"), lang) or None,
            "lead_time_days": t.get("lead_time_days"),
            "crops": t["crops"],
            "targets": t["targets"],
            "institute": {"id": t["institute"], **inst},
        }
        return view

    def registered_uses(self, ingredient: str) -> list[tuple[str, str]]:
        """(crop, target) pairs where our advisories use this ingredient."""
        out = []
        for tid, adv in self.advisories.items():
            for rung in adv["ladder"]:
                if rung.get("ingredient") == ingredient:
                    out.append((self.targets[tid]["crop"], tid))
        return out


def _load(name: str, kb_dir: Path):
    return json.loads((kb_dir / name).read_text(encoding="utf-8"))


def _strip_notes(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def validate(kb: KB) -> list[str]:
    errors: list[str] = []
    crops = kb.crops

    for tid, t in kb.targets.items():
        if t["crop"] not in crops:
            errors.append(f"target {tid}: unknown crop {t['crop']}")
        if not tid.startswith(t["crop"] + "_"):
            errors.append(f"target {tid}: id must be namespaced by crop")
        if t["tier"] not in ("diagnosable", "inspection"):
            errors.append(f"target {tid}: bad tier {t['tier']}")
        if tid not in kb.advisories:
            errors.append(f"target {tid}: no advisory")
        if tid not in kb.rules:
            errors.append(f"target {tid}: no risk rule / inspection tasks")

    for tid, adv in kb.advisories.items():
        if tid not in kb.targets:
            errors.append(f"advisory {tid}: unknown target")
            continue
        ladder = adv.get("ladder") or []
        if not ladder:
            errors.append(f"advisory {tid}: empty ladder")
        order = [TIER_ORDER.get(r.get("tier"), -1) for r in ladder]
        if -1 in order:
            errors.append(f"advisory {tid}: unknown ladder tier")
        if order != sorted(order):
            errors.append(f"advisory {tid}: ladder is not cultural -> biological -> chemical")
        if order and order[0] == TIER_ORDER["chemical"]:
            errors.append(f"advisory {tid}: ladder leads with a chemical")
        for r in ladder:
            if r.get("tier") == "chemical":
                ing = r.get("ingredient")
                if ing not in kb.pesticides:
                    errors.append(f"advisory {tid}: unknown ingredient {ing}")
                elif kb.pesticides[ing]["class"] == "herbicide":
                    errors.append(f"advisory {tid}: herbicide {ing} on a pest/disease ladder")
                if r.get("dose_per_litre") is None and not r.get("dose_basis"):
                    errors.append(f"advisory {tid}: chemical rung {ing} has no dose")
        if not adv.get("citations"):
            errors.append(f"advisory {tid}: no citation")
        if not adv.get("what_to_avoid"):
            errors.append(f"advisory {tid}: no what_to_avoid")

    for cue in kb.cues:
        a, b = cue["pair"]
        for x in (a, b):
            if x not in kb.targets:
                errors.append(f"cue {cue['id']}: unknown target {x}")
        if cue["yes_means"] not in cue["pair"]:
            errors.append(f"cue {cue['id']}: yes_means is not one of the pair")
        if kb.targets.get(a, {}).get("crop") != kb.targets.get(b, {}).get("crop"):
            errors.append(f"cue {cue['id']}: pair spans two crops")

    for tid, rule in kb.rules.items():
        if tid not in kb.targets:
            errors.append(f"rule {tid}: unknown target")
            continue
        crop = kb.targets[tid]["crop"]
        stage_keys = {s["key"] for s in crops[crop]["stages"]}
        for s in rule.get("stages", []):
            if s not in stage_keys:
                errors.append(f"rule {tid}: stage {s} is not a {crop} stage")
        tasks = rule.get("tasks", {})
        if len(tasks.get("en", [])) < MIN_TASKS:
            errors.append(f"rule {tid}: fewer than {MIN_TASKS} inspection tasks")
        for lang in ("hi", "mr"):
            if lang in tasks and len(tasks[lang]) != len(tasks["en"]):
                errors.append(f"rule {tid}: {lang} tasks do not match en")
        if not (rule.get("weather") or rule.get("phenology") or rule.get("trap")):
            errors.append(f"rule {tid}: no trigger (weather, phenology or trap)")

    for inst_id, inst in kb.institutes.items():
        if not inst.get("name") or not (inst.get("phone") or inst.get("email")):
            errors.append(f"institute {inst_id}: needs a name and a phone or email")
    seen: set[str] = set()
    for t in kb.technologies:
        tid = t.get("id", "?")
        if tid in seen:
            errors.append(f"technology {tid}: duplicate id")
        seen.add(tid)
        if t.get("institute") not in kb.institutes:
            errors.append(f"technology {tid}: unknown institute {t.get('institute')}")
        if t.get("type") not in TECH_TYPES:
            errors.append(f"technology {tid}: bad type {t.get('type')}")
        if t.get("audience") not in TECH_AUDIENCES:
            errors.append(f"technology {tid}: bad audience {t.get('audience')}")
        if not t.get("short"):
            errors.append(f"technology {tid}: no short label")
        if not t.get("source_name"):
            errors.append(f"technology {tid}: no source_name (provenance)")
        if not t.get("crops"):
            errors.append(f"technology {tid}: no crop")
        for c in t.get("crops", []):
            if c not in crops:
                errors.append(f"technology {tid}: unknown crop {c}")
        for x in t.get("targets", []):
            if x not in kb.targets:
                errors.append(f"technology {tid}: unknown target {x}")
            elif kb.targets[x]["crop"] not in t.get("crops", []):
                errors.append(f"technology {tid}: target {x} is not on one of its crops")
        needed = LANGS if t.get("audience") == "farmer" else ("en",)
        for key in ("summary", "claim", "supply", "link_reason"):
            text = t.get(key)
            if key == "summary" or text:
                for lang in needed:
                    if not (text or {}).get(lang):
                        errors.append(f"technology {tid}: {key} missing {lang}")

    errors += validate_agromet(kb)
    return errors


AGROMET_SEVERITIES = ("warning", "advice", "info")
AGROMET_CATEGORIES = ("safety", "rain", "wind", "cold", "heat", "spray", "disease", "irrigation", "fog", "crop")


def _fields(text: str) -> set[str]:
    import string  # noqa: PLC0415

    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def validate_agromet(kb: KB) -> list[str]:
    am = kb.agromet
    if not am:
        return []
    errors: list[str] = []
    for crop, table in am.get("kc", {}).items():
        if crop.startswith("_"):
            continue
        stages = {s["key"] for s in kb.crops.get(crop, {}).get("stages", [])}
        if crop not in kb.crops:
            errors.append(f"agromet kc: unknown crop {crop}")
        elif set(table) != stages:
            errors.append(f"agromet kc {crop}: stages {sorted(set(table) ^ stages)} do not match crops.json")
        if any(not (0.1 <= v <= 1.5) for v in table.values()):
            errors.append(f"agromet kc {crop}: a coefficient outside 0.1–1.5")
    for key in ("heat_sensitive_stages", "irrigation_stop_stages"):
        for crop, stages in am.get(key, {}).items():
            if crop.startswith("_"):
                continue
            known = {s["key"] for s in kb.crops.get(crop, {}).get("stages", [])}
            for st in stages:
                if st not in known:
                    errors.append(f"agromet {key}: {st} is not a {crop} stage")
    seen = set()
    for r in am.get("rules", []):
        rid = r.get("id", "?")
        if rid in seen:
            errors.append(f"agromet rule {rid}: duplicate id")
        seen.add(rid)
        if r.get("severity") not in AGROMET_SEVERITIES:
            errors.append(f"agromet rule {rid}: bad severity")
        if r.get("category") not in AGROMET_CATEGORIES:
            errors.append(f"agromet rule {rid}: bad category")
        if not r.get("source"):
            errors.append(f"agromet rule {rid}: no source")
        for part in ("title", "text"):
            en = _fields((r.get(part) or {}).get("en", ""))
            for lang in LANGS:
                text = (r.get(part) or {}).get(lang)
                if not text:
                    errors.append(f"agromet rule {rid}: {part} missing {lang}")
                elif _fields(text) != en:
                    errors.append(f"agromet rule {rid}: {part} {lang} placeholders differ from en")
        do = r.get("do") or {}
        if not do.get("en"):
            errors.append(f"agromet rule {rid}: nothing to do")
        for lang in ("hi", "mr"):
            if len(do.get(lang, [])) != len(do.get("en", [])):
                errors.append(f"agromet rule {rid}: do list {lang} does not match en")
    return errors


def load_kb(kb_dir: Path = KB_DIR) -> KB:
    kb = KB(
        crops=_strip_notes(_load("crops.json", kb_dir)),
        targets={t["id"]: t for t in _load("targets.json", kb_dir)},
        advisories=_strip_notes(_load("advisories.json", kb_dir)),
        cues=_load("cues.json", kb_dir),
        rules=_load("risk_rules.json", kb_dir)["rules"],
        pesticides=_strip_notes(_load("pesticides.json", kb_dir)),
    )
    tech_file = kb_dir / "icar_technologies.json"
    if tech_file.exists():
        tech = _load("icar_technologies.json", kb_dir)
        kb.institutes, kb.technologies = tech["institutes"], tech["technologies"]
    if (kb_dir / "agromet.json").exists():
        kb.agromet = _load("agromet.json", kb_dir)
    errors = validate(kb)
    if errors:
        raise KBError("knowledge base refused:\n  " + "\n  ".join(errors))
    kb._cue_index = {frozenset(c["pair"]): c for c in kb.cues}
    return kb


@lru_cache
def get_kb() -> KB:
    return load_kb()
