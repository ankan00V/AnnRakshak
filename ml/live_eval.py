"""End-to-end accuracy of what a farmer actually uses, on held-out images the
model never trained on — through the real API, the real gate and the deployed
model, not the notebook:

  1. Photo:  POST /api/farms/{id}/diagnose for every held-out image.
  2. Live:   one full video-call session per class over the real WebSocket
             (/api/live/{id}): frames stream in, the walk's steps, quality
             checks and the two-close-up evidence rule decide the verdict.

    .venv/bin/python ml/live_eval.py            -> ml/reports/LIVE_EVAL.md

A throwaway SQLite database; weather and soil are stubbed (their accuracy is
not what is measured here); no paid voice calls.
"""

from __future__ import annotations

import base64
import io
import json
import os
import random
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_tmp = tempfile.mkdtemp(prefix="annrakshak-eval-")
os.environ.update({"ANNRAKSHAK_DATA_DIR": _tmp, "ANNRAKSHAK_DB_URL": f"sqlite:///{_tmp}/eval.db",
                   "ANNRAKSHAK_WATCH": "off", "REDIS_URL": "", "SARVAM_API_KEY": "", "SARVAM_API_KEYS": "",
                   "OPENWEATHER_API_KEY": "", "AGRO_API_KEY": "", "SMTP_HOST": ""})
os.environ.pop("ANNRAKSHAK_VISION", None)  # the real model
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, str(ROOT / "ml"))
from composite import composite, is_plain  # noqa: E402
from PIL import ImageEnhance  # noqa: E402

from app import services  # noqa: E402
from app.routers import farmer as farmer_router  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.engine import fieldnow, vision  # noqa: E402
from app.engine.weather import Day, Window  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Farm  # noqa: E402

ART = ROOT / "ml" / "artifacts"
OUT = ROOT / "ml" / "reports" / "LIVE_EVAL.md"
random.seed(7)


def stub_weather():
    days = [Day(date.today() - timedelta(6 - i), 70, 22, 31, 0.0) for i in range(10)]
    services.fetch_window = lambda lat, lon: Window(days, "stub", datetime.now())
    services.fetch_month_rain = lambda lat, lon: None
    fieldnow.conditions_now = lambda lat, lon, lang, **kw: {"weather": None, "soil_model": None}
    fieldnow.soilgrids = lambda lat, lon, **kw: None


def jpeg(path: Path | Image.Image, max_side: int = 512) -> bytes:
    im = path if isinstance(path, Image.Image) else Image.open(path)
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return buf.getvalue()


STEP_KIND = {"overview": "scene", "plant": "plant", "base": "base"}  # every other step is a close-up


def camera_view(im: Image.Image, rng: random.Random) -> Image.Image:
    """The phone moving over the same subject: a slightly different crop,
    angle, mirror and light each frame."""
    w, h = im.size
    k = rng.uniform(0.78, 0.95)
    cw, ch = int(w * k), int(h * k)
    x, y = rng.randint(0, w - cw), rng.randint(0, h - ch)
    v = im.crop((x, y, x + cw, y + ch)).rotate(rng.uniform(-10, 10), resample=Image.BILINEAR)
    if rng.random() < 0.5:
        v = v.transpose(Image.FLIP_LEFT_RIGHT)
    return ImageEnhance.Brightness(v).enhance(rng.uniform(0.88, 1.12))


def main() -> None:
    stub_weather()
    farmer_router.limit = lambda *a, **k: None  # the eval uploads hundreds a minute; a farmer never does
    meta = json.loads((ART / "meta.json").read_text())
    c2t = meta["class_to_target"]
    split = json.loads((ART / "split.json").read_text())
    icar = [ROOT / p for p in split["test"]]
    extra = [ROOT / p for p in split.get("extra_test", [])]
    by_class: dict[str, list[Path]] = defaultdict(list)
    for p in icar + extra:
        by_class[p.parent.name].append(p)

    crops = sorted({cls.split("_")[0] for cls in by_class})  # every crop the model knows
    with TestClient(app) as c, SessionLocal() as db:
        farms = {}
        for crop in crops:
            f = Farm(farmer_name=f"eval-{crop}", crop=crop, sowing_date=date.today() - timedelta(days=60),
                     district="Pune", lat=18.52, lon=73.85, area_acres=2, lang="en")
            db.add(f)
            db.commit()
            farms[crop] = f.id
        status = vision.model_status()
        print("model:", status["model_version"], "stub" if status["is_stub"] else "real")
        if status["is_stub"]:
            sys.exit("the real model is not loaded (ml/artifacts/model.pt)")

        # ---------------- 1. photo -------------------------------------------------
        photo = []
        for cls, paths in sorted(by_class.items()):
            sample = paths if cls in {p.parent.name for p in icar} else random.sample(paths, min(20, len(paths)))
            crop = cls.split("_")[0]
            for p in sample:
                r = c.post(f"/api/farms/{farms[crop]}/diagnose", files={"image": ("x.jpg", jpeg(p, 1280), "image/jpeg")},
                           data={"lang": "en"}).json()
                gate = r.get("gate") or {}
                alts = gate.get("alternatives") or [{}]
                photo.append({"cls": cls, "truth": c2t[cls], "outcome": gate.get("outcome"),
                              "top": alts[0].get("id"), "src": "icar" if p in icar else "extra"})
        # ---------------- 2. live ---------------------------------------------------
        live = []
        rng = random.Random(11)
        # Field frames for the walk: held-out healthy photos of that crop (ICAR's where
        # there are any, otherwise the new field sets for cotton and soybean).
        field = {crop: [p for p in icar if p.parent.name == f"{crop}_healthy"]
                 or [p for p in extra if p.parent.name == f"{crop}_healthy"] for crop in crops}
        for cls, paths in sorted(by_class.items()):
            crop = cls.split("_")[0]
            # Close-ups: this class's held-out leaves; lab photos on plain paper are
            # pasted on a held-out field photo, as in the model report's swap test.
            leaves = []
            for p in paths:
                with Image.open(p) as im:
                    im = im.convert("RGB")
                    if is_plain(im):
                        with Image.open(rng.choice(field[crop])) as bg:
                            im = composite(im, bg.convert("RGB"), rng)
                    leaves.append(im.copy())
            with c.websocket_connect(f"/api/live/{farms[crop]}") as ws:
                ws.send_json({"type": "start", "lang": "en"})
                ready = ws.receive_json()
                assert ready["type"] == "ready", ready
                step = ready["guide"]["step"]
                sent, done, asked = 0, False, None
                for i in range(80):
                    kind = STEP_KIND.get(step, "close")
                    src = rng.choice(field[crop]) if kind != "close" else leaves[i % len(leaves)]
                    im = Image.open(src).convert("RGB") if isinstance(src, Path) else src
                    frame = camera_view(im, rng)
                    ws.send_json({"type": "frame", "seq": i, "data": base64.b64encode(jpeg(frame)).decode()})
                    sent += 1
                    while True:
                        m = ws.receive_json()
                        if m["type"] == "ask":
                            asked = m
                            continue
                        if m["type"] == "steps_done":
                            done = True
                            break
                        if m["type"] == "frame":
                            step = (m.get("guide") or {}).get("step") or step
                            break
                        if m["type"] == "error":
                            break
                    if done:
                        break
                if asked:  # the farmer can't tell: the honest answer for an eval
                    ws.send_json({"type": "answer", "cue_id": asked["cue_id"], "answer": "unknown"})
                    ws.receive_json()
                ws.send_json({"type": "finish"})
                m = ws.receive_json()
                while m["type"] != "summary":
                    m = ws.receive_json()
                s = m["summary"]
            live.append({"cls": cls, "truth": c2t[cls], "frames": sent, "completed": done,
                         "verdict": s["verdict"], "seen": [x["target"] for x in s["seen"]],
                         "possible": [x["target"] for x in s["possible"]], "src": "icar" if paths[0] in icar else "extra"})
            print(f"  live {cls:32s} frames {sent:2d} verdict {s['verdict']:8s} seen {live[-1]['seen']} possible {live[-1]['possible']}")

    report(photo, live, status)


def report(photo: list[dict], live: list[dict], status: dict) -> None:
    def healthy(t):
        return t.endswith("_healthy")

    lines = [f"# End-to-end accuracy — photo and live video call\n",
             f"Generated {datetime.now():%Y-%m-%d %H:%M} by `ml/live_eval.py` with model `{status['model_version']}`, "
             "through the real API (confidence gate, Doubt Doctor, live walk). Held-out images only: the ICAR test split "
             "(same as the model report) and up to 20 held-out images per class from the extra sources.\n"]
    # photo
    adv = [r for r in photo if r["outcome"] == "advise"]
    right = [r for r in adv if r["top"] == r["truth"]]
    oc = Counter(r["outcome"] for r in photo)
    lines += ["## 1. Photo diagnosis\n",
              f"| Images | Advised | Right when advised | Asked a question | Sent to expert | Asked for a retake |",
              "|---|---|---|---|---|---|",
              f"| {len(photo)} | {len(adv)} ({100 * len(adv) / len(photo):.0f}%) | **{100 * len(right) / max(1, len(adv)):.1f}%** "
              f"| {oc['clarify']} | {oc['escalate']} | {oc['retake']} |\n"]
    for src in ("icar", "extra"):
        sub = [r for r in photo if r["src"] == src]
        a = [r for r in sub if r["outcome"] == "advise"]
        if sub:
            lines.append(f"- {'ICAR field photos' if src == 'icar' else 'Extra sources (blast, rust, field FAW…)'}: {len(sub)} images, "
                         f"advised {len(a)}, right when advised {100 * sum(r['top'] == r['truth'] for r in a) / max(1, len(a)):.1f}%")
    wrong = [r for r in adv if r["top"] != r["truth"]]
    if wrong:
        lines += ["", "Advised but wrong (what a farmer would have been told):", ""]
        lines += [f"- {r['cls']} → {r['top']}" for r in wrong]
    # live
    lines += ["\n## 2. Live video call — one full session per class\n",
              "A session walks the real steps: held-out healthy field photos for the field, plant and base steps, and "
              "that class's held-out leaves for the close-ups (lab photos pasted on held-out field backgrounds), each "
              "frame a slightly moved, turned and relit view, as a phone gives. "
              "**Right** = the true problem is reported as seen (≥ 2 separate close-ups agreeing) — or, for a healthy "
              "class, nothing is reported as seen. **Cautious** = shown as *possible* and sent to an expert. "
              "**Wrong** = a different problem reported as seen.\n",
              "| Class | Frames | Verdict | Seen | Possible | Result |", "|---|---|---|---|---|---|"]
    tally = Counter()
    for r in live:
        if healthy(r["truth"]):
            res = "right" if not r["seen"] else "wrong"
        elif r["truth"] in r["seen"]:
            res = "right" if len(r["seen"]) == 1 else "right (+ another)"
        elif r["truth"] in r["possible"] and not r["seen"]:
            res = "cautious"
        elif r["seen"]:
            res = "wrong"
        else:
            res = "missed"
        tally[res.split(" ")[0]] += 1
        lines.append(f"| {r['cls']} | {r['frames']} | {r['verdict']} | {', '.join(r['seen']) or '—'} | "
                     f"{', '.join(r['possible']) or '—'} | {res} |")
    n = len(live)
    lines += ["", f"**Right {tally['right']}/{n}** · cautious {tally['cautious']} · missed {tally['missed']} · "
              f"wrong {tally['wrong']}.\n",
              "## Read this before quoting the numbers\n",
              "- Held-out images are still curated datasets; a phone in a real field adds blur, glare and mixed plants — "
              "which the live walk's quality checks and the two-close-up rule exist to absorb.",
              "- A live session here streams still images of one class; a real field can hold two problems at once.",
              "- Expert confirmations on the officials' dashboard are the field accuracy that counts."]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print("\n".join(lines[3:8]))
    print(f"live: right {tally['right']}/{n}, cautious {tally['cautious']}, missed {tally['missed']}, wrong {tally['wrong']}")


if __name__ == "__main__":
    main()
