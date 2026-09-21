"""Live field walk: a guided, real-time camera session ("a video call with the AI").

The phone keeps the camera open and sends a small still frame about once a
second. Nothing is recorded: each frame is checked and discarded, except the
few that become evidence for a finding. The session:

  1. guides the farmer through views of the field (overview, a whole plant,
     leaf close-ups top and underside, the plant base, a second spot);
  2. checks every frame live (sharp? bright enough? crop in view? a new view?)
     and coaches until the step has enough good views;
  3. runs the photo model on close-ups only, and accumulates evidence per
     problem across views;
  4. adds a step when it glimpses something ("show me more leaves with those
     spots"), and asks the Doubt Doctor question when two problems compete;
  5. reports a problem as seen only when at least two separate close-ups agree
     above the same 0.70 gate the photo path uses. A single weak sighting goes
     to an expert, never to a spray.

Pure: no I/O. The caller injects the classifier and persists the result.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median

import numpy as np
from PIL import Image

from app.config import FLOOR, GATE, MARGIN, gate_for
from app.engine.gate import crop_of, is_healthy
from app.engine.vision import vegetation_fraction
from app.kb import tr

# --- frame quality -----------------------------------------------------------
WORK = 256                 # px, long side used for measuring
DARK, GLARE = 45.0, 235.0  # mean brightness (0-255) outside which a frame is unusable
# Laplacian variance at WORK px. Calibrated on real photos: sharp field close-ups
# (CCMT, ICAR) score >= 26 at the 5th percentile; the same photos blurred by a
# 2 px Gaussian score 6-22 (ICAR ~22 at p5 only because its originals are huge).
SHARP_SCENE = 15.0
SHARP_CLOSE = 35.0
NOVELTY = 7.0              # mean abs difference (0-255) on a 24 px thumb to count as a new view

KINDS = {
    #          min vegetation, min sharpness, run the photo model
    "scene": (0.20, SHARP_SCENE, False),
    "plant": (0.30, SHARP_SCENE, False),
    "close": (0.40, SHARP_CLOSE, True),  # insects on a leaf show less green than a bare leaf
    "base": (0.06, SHARP_SCENE, False),
}

TEXT = {
    "overview": {
        "en": "Stand at the edge of your field and slowly show me the whole field.",
        "hi": "खेत के किनारे खड़े होकर धीरे-धीरे पूरा खेत दिखाइए।",
        "mr": "शेताच्या कडेला उभे राहून हळूहळू संपूर्ण शेत दाखवा.",
    },
    "plant": {
        "en": "Walk into the field. Show me one whole plant, from top to bottom.",
        "hi": "खेत के अंदर जाइए। एक पूरा पौधा ऊपर से नीचे तक दिखाइए।",
        "mr": "शेतात आत चला. एक संपूर्ण रोप वरपासून खालपर्यंत दाखवा.",
    },
    "leaf_top": {
        "en": "Bring the camera close to the leaves, about one hand away. Show the top side.",
        "hi": "कैमरा पत्तियों के पास लाइए, लगभग एक हाथ दूर। पत्ती का ऊपरी भाग दिखाइए।",
        "mr": "कॅमेरा पानांच्या जवळ आणा, सुमारे एक हात अंतरावर. पानाची वरची बाजू दाखवा.",
    },
    "leaf_under": {
        "en": "Now turn a leaf over and show me its underside.",
        "hi": "अब एक पत्ती पलटकर उसका निचला भाग दिखाइए।",
        "mr": "आता एक पान उलटून त्याची खालची बाजू दाखवा.",
    },
    "base": {
        "en": "Show me the base of the plant, where it meets the soil or water.",
        "hi": "पौधे का निचला हिस्सा दिखाइए, जहाँ वह मिट्टी या पानी से मिलता है।",
        "mr": "रोपाचा खालचा भाग दाखवा, जिथे ते माती किंवा पाण्याला मिळते.",
    },
    "second_spot": {
        "en": "Walk about 20 steps to another part of the field and show me leaves close up again.",
        "hi": "लगभग 20 कदम चलकर खेत के दूसरे हिस्से में जाइए और फिर से पत्तियाँ पास से दिखाइए।",
        "mr": "सुमारे 20 पावले चालून शेताच्या दुसऱ्या भागात जा आणि पुन्हा पाने जवळून दाखवा.",
    },
    "confirm": {
        "en": "I think I see {name}. Show me more leaves with those marks, close up.",
        "hi": "मुझे {name} जैसा कुछ दिख रहा है। ऐसे निशान वाली और पत्तियाँ पास से दिखाइए।",
        "mr": "मला {name} सारखे काहीतरी दिसत आहे. असे डाग असलेली आणखी पाने जवळून दाखवा.",
    },
}

HINTS = {
    "too_dark": {"en": "Too dark — turn towards the light.", "hi": "बहुत अँधेरा है — रोशनी की तरफ़ घूमिए।",
                 "mr": "खूप अंधार आहे — उजेडाकडे वळा."},
    "too_bright": {"en": "Too much glare — shade the leaf or turn a little.",
                   "hi": "बहुत चमक है — पत्ती पर छाया कीजिए या थोड़ा घूमिए।",
                   "mr": "खूप चकाकी आहे — पानावर सावली करा किंवा थोडे वळा."},
    "hold_steady": {"en": "Hold the phone steady.", "hi": "फ़ोन स्थिर पकड़िए।", "mr": "फोन स्थिर धरा."},
    "show_crop": {"en": "Point the camera at your crop.", "hi": "कैमरा अपनी फसल की ओर कीजिए।",
                  "mr": "कॅमेरा तुमच्या पिकाकडे करा."},
    "come_closer": {"en": "Come closer to the leaves.", "hi": "पत्तियों के और पास आइए।",
                    "mr": "पानांच्या आणखी जवळ या."},
    "move_a_little": {"en": "Good. Now move a little to show a different part.",
                      "hi": "अच्छा। अब थोड़ा हटकर दूसरा हिस्सा दिखाइए।",
                      "mr": "छान. आता थोडे हलून दुसरा भाग दाखवा."},
    "good": {"en": "Good, keep going.", "hi": "बढ़िया, ऐसे ही दिखाते रहिए।", "mr": "छान, असेच दाखवत राहा."},
}

BASE_STEPS = [("overview", "scene", 3), ("plant", "plant", 2), ("leaf_top", "close", 4),
              ("leaf_under", "close", 2), ("base", "base", 2), ("second_spot", "close", 3)]
CONFIRM_NEED = 3
MAX_EVIDENCE_FRAMES = 3
MIN_SHARE_OF_STRONG = 0.25
"""A second problem must make up at least this share of the walk's strong disease
readings to be reported as seen; below it, it goes to an expert as possible."""


@dataclass
class Quality:
    ok: bool
    hint: str | None
    sharp: float
    bright: float
    veg: float
    novel: bool


@dataclass
class Step:
    id: str
    kind: str
    need: int
    got: int = 0
    name: str | None = None  # for the confirm step


@dataclass
class Sighting:
    target: str
    conf: float
    frame: int


@dataclass
class LiveSession:
    crop: str
    lang: str
    can_classify: bool
    target_name: Callable[[str], str] = lambda t: t
    steps: list[Step] = field(default_factory=list)
    idx: int = 0
    frames: int = 0
    good_frames: int = 0
    classified: int = 0
    sightings: list[Sighting] = field(default_factory=list)
    evidence: dict[str, list[tuple[float, bytes]]] = field(default_factory=dict)
    closeups: list[tuple[float, bytes]] = field(default_factory=list)  # sharpest, for crops without a model
    other_crop: int = 0
    confirm_added: bool = False
    asked: str | None = None
    answer: tuple[str, str] | None = None  # (cue_id, yes/no/unknown)
    _last_thumb: np.ndarray | None = None

    def __post_init__(self):
        if not self.steps:
            self.steps = [Step(i, k, n) for i, k, n in BASE_STEPS]

    # --- public ---------------------------------------------------------------
    @property
    def done(self) -> bool:
        return self.idx >= len(self.steps)

    def guide(self) -> dict:
        if self.done:
            return {"step": None, "index": len(self.steps), "total": len(self.steps)}
        s = self.steps[self.idx]
        text = tr(TEXT[s.id], self.lang)
        return {"step": s.id, "kind": s.kind, "index": self.idx, "total": len(self.steps),
                "need": s.need, "got": s.got, "text": text.format(name=s.name or "")}

    def on_frame(self, img: Image.Image, jpeg: bytes,
                 classify: Callable[[Image.Image], list[tuple[str, float]]] | None) -> dict:
        self.frames += 1
        if self.done:
            return {"quality": None, "counted": False, "advanced": False, "guide": self.guide()}
        step = self.steps[self.idx]
        q = measure(img, step.kind, self._last_thumb)
        out: dict = {"quality": q.__dict__ | {"hint_text": self.hint_text(q.hint)}, "counted": False,
                     "advanced": False, "live": None}
        if not q.ok:
            return out | {"guide": self.guide()}
        self.good_frames += 1
        self._last_thumb = _thumb(img)
        step.got += 1
        out["counted"] = True
        vmin, smin, run_model = KINDS[step.kind]
        if run_model:
            self.closeups.append((q.sharp, jpeg))
            self.closeups = sorted(self.closeups, key=lambda x: -x[0])[:MAX_EVIDENCE_FRAMES]
            if classify is not None and self.can_classify:
                preds = classify(img)
                if not preds:  # the model says this is not a crop view at all
                    step.got -= 1
                    self.good_frames -= 1
                    self.closeups = [c for c in self.closeups if c[1] is not jpeg]
                    q.ok, q.hint = False, "show_crop"
                    return out | {"quality": q.__dict__ | {"hint_text": self.hint_text(q.hint)}, "counted": False,
                                  "guide": self.guide()}
                self.classified += 1
                out["live"] = self._record(preds, jpeg)
        if step.got >= step.need:
            self._maybe_add_confirm()
            self.idx += 1
            out["advanced"] = True
        return out | {"guide": self.guide()}

    def pending_question(self, kb) -> dict | None:
        """A Doubt Doctor question once the close-ups are in, if the two
        strongest problems compete and a field check separates them."""
        if self.asked or self.answer or not self.done:
            return None
        ranked = self._ranked()
        if len(ranked) < 2:
            return None
        (a, ca), (b, cb) = ranked[0], ranked[1]
        if ca - cb > MARGIN or cb < FLOOR:
            return None
        cue = kb.cue_for(a, b)
        if cue:
            self.asked = cue["id"]
            return cue
        return None

    def on_answer(self, cue_id: str, answer: str) -> None:
        if cue_id == self.asked:
            self.answer = (cue_id, answer)

    def findings(self, kb) -> dict:
        """What the walk showed. 'seen' = at least two separate close-ups agree
        above the gate; 'possible' = glimpsed, goes to an expert."""
        seen, possible = [], []
        settled = None
        if self.answer and self.answer[1] in ("yes", "no"):
            cue = next((c for c in kb.cues if c["id"] == self.answer[0]), None)
            if cue:
                a, b = cue["pair"]
                settled = cue["yes_means"] if self.answer[1] == "yes" else (b if cue["yes_means"] == a else a)
        by_target: dict[str, list[float]] = {}
        for s in self.sightings:
            by_target.setdefault(s.target, []).append(s.conf)
        # Strong disease readings across the whole walk. A problem read strongly in
        # only a sliver of them — two frames among fifteen that agree on something
        # else — is more likely a misread than a second disease: it goes to an
        # expert as 'possible', never to the farmer as 'seen'.
        total_strong = sum(sum(c >= gate_for(t) for c in confs) for t, confs in by_target.items()
                           if not is_healthy(t) and crop_of(t) == self.crop)
        for t, confs in sorted(by_target.items(), key=lambda kv: -max(kv[1])):
            if is_healthy(t) or crop_of(t) != self.crop:
                continue
            strong = [c for c in confs if c >= gate_for(t)]
            tier = kb.targets.get(t, {}).get("tier")
            share = len(strong) / total_strong if total_strong else 0.0
            item = {"target": t, "views": len(confs), "strong_views": len(strong),
                    "share_of_strong": round(share, 2),
                    "confidence": round(median(strong) if strong else max(confs), 3)}
            if tier == "diagnosable" and ((len(strong) >= 2 and share >= MIN_SHARE_OF_STRONG)
                                          or (settled == t and max(confs) >= FLOOR)):
                seen.append(item | {"settled_by_answer": settled == t and len(strong) < 2})
            elif max(confs) >= FLOOR:
                reason = "NOT_PHOTO_DIAGNOSABLE" if tier != "diagnosable" else \
                    "MINORITY_VIEWS" if len(strong) >= 2 else "FEW_VIEWS"
                possible.append(item | {"reason": reason})
        # Look-alikes (a Doubt Doctor pair, e.g. blast and brown spot) are exactly what
        # the model confuses; unless the farmer's answer settled it, only the one
        # with more strong views is 'seen' — the other goes to the expert.
        for a in sorted(seen, key=lambda x: -x["strong_views"]):
            for b in list(seen):
                if b is a or b not in seen or a not in seen or b.get("settled_by_answer"):
                    continue
                if kb.cue_for(a["target"], b["target"]) and b["strong_views"] <= a["strong_views"] \
                        and settled != b["target"]:
                    seen.remove(b)
                    possible.append({k: v for k, v in b.items() if k != "settled_by_answer"} | {"reason": "LOOKALIKE"})
        healthy_views = sum(1 for s in self.sightings if is_healthy(s.target) and crop_of(s.target) == self.crop)
        # Healthy at any confidence is not evidence of health: a blurred or
        # half-seen leaf lands on "healthy" as easily as on anything else. Only
        # views the model was sure of may back a "your plants are healthy".
        healthy_confident = sum(1 for s in self.sightings if is_healthy(s.target)
                                and crop_of(s.target) == self.crop and s.conf >= gate_for(s.target))
        return {
            "seen": seen,
            "possible": [p for p in possible if p["target"] not in {s["target"] for s in seen}],
            "classified_views": self.classified,
            "healthy_views": healthy_views,
            "healthy_confident_views": healthy_confident,
            "other_crop_views": self.other_crop,
            "good_frames": self.good_frames,
            "frames": self.frames,
            "answer": {"cue_id": self.answer[0], "answer": self.answer[1]} if self.answer else None,
        }

    def evidence_for(self, target: str) -> list[bytes]:
        return [j for _, j in sorted(self.evidence.get(target, []), key=lambda x: -x[0])]

    def hint_text(self, key: str | None) -> str | None:
        return tr(HINTS[key], self.lang) if key else None

    # --- internals ------------------------------------------------------------
    def _record(self, preds: list[tuple[str, float]], jpeg: bytes) -> dict:
        top, conf = preds[0]
        if crop_of(top) != self.crop:
            self.other_crop += 1
        self.sightings.append(Sighting(top, conf, self.frames))
        if not is_healthy(top) and conf >= FLOOR:
            ev = self.evidence.setdefault(top, [])
            ev.append((conf, jpeg))
            ev.sort(key=lambda x: -x[0])
            del ev[MAX_EVIDENCE_FRAMES:]
        return {"top": [{"target": t, "name": self.target_name(t), "confidence": round(c, 3)} for t, c in preds]}

    def _ranked(self) -> list[tuple[str, float]]:
        acc: dict[str, list[float]] = {}
        for s in self.sightings:
            if not is_healthy(s.target) and crop_of(s.target) == self.crop:
                acc.setdefault(s.target, []).append(s.conf)
        return sorted(((t, float(np.mean(v))) for t, v in acc.items()), key=lambda kv: -kv[1])

    def _maybe_add_confirm(self) -> None:
        """Glimpsed a problem but not yet two strong views: ask for more close-ups once."""
        if self.confirm_added or self.steps[self.idx].kind != "close":
            return
        remaining_close = any(s.kind == "close" for s in self.steps[self.idx + 1:])
        for t, confs in self._by_target().items():
            strong = sum(c >= gate_for(t) for c in confs)
            if strong < 2 and max(confs) >= FLOOR and not remaining_close:
                self.steps.insert(self.idx + 1, Step("confirm", "close", CONFIRM_NEED, name=self.target_name(t)))
                self.confirm_added = True
                return

    def _by_target(self) -> dict[str, list[float]]:
        acc: dict[str, list[float]] = {}
        for s in self.sightings:
            if not is_healthy(s.target) and crop_of(s.target) == self.crop:
                acc.setdefault(s.target, []).append(s.conf)
        return acc


def _thumb(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L").resize((24, 24)), dtype=np.float32)


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian — the standard blur measure."""
    g = gray.astype(np.float32)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0  # too small to have edges (and var() of nothing is NaN, which is not JSON)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def measure(img: Image.Image, kind: str, last_thumb: np.ndarray | None) -> Quality:
    small = img.convert("RGB")
    small.thumbnail((WORK, WORK))
    gray = np.asarray(small.convert("L"), dtype=np.float32)
    bright = float(gray.mean())
    sharp = sharpness(gray)
    veg = vegetation_fraction(small)
    vmin, smin, _ = KINDS[kind]
    novel = True
    if last_thumb is not None:
        novel = float(np.abs(_thumb(small) - last_thumb).mean()) >= NOVELTY
    hint = None
    if bright < DARK:
        hint = "too_dark"
    elif bright > GLARE:
        hint = "too_bright"
    elif sharp < smin:
        hint = "hold_steady"
    elif veg < vmin:
        hint = "come_closer" if kind == "close" and veg >= 0.15 else "show_crop"
    elif not novel:
        hint = "move_a_little"
    return Quality(ok=hint is None, hint=hint, sharp=round(sharp, 1), bright=round(bright, 1),
                   veg=round(veg, 3), novel=novel)


MIN_SIDE = 64  # smaller than this is a camera glitch (a stopped track gives 0-2 px frames)


def decode(jpeg: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(jpeg))
    im.load()
    if min(im.size) < MIN_SIDE:
        raise ValueError(f"frame too small: {im.size}")
    return im.convert("RGB")


