"""Build a demo history by running the REAL flows — nothing is inserted directly.

    .venv/bin/python backend/demo_story.py            # reset DB, seed, play the story
    .venv/bin/python backend/demo_story.py --keep     # play on top of the current DB

What it does, through the public API only:
  1. seeds the demo farms (backend/seed.py) and runs a live risk sweep;
  2. for each farm, uploads held-out TEST photos of that crop (never seen in
     training, from ml/artifacts/split.json) to /diagnose;
  3. answers any Doubt Doctor question the way a farmer who knows the truth
     would (the ICAR label says which lesion it is);
  4. resolves escalated cases with the ICAR ground-truth label, under a
     reviewer name that says exactly that — except a few left open for the
     expert console.

So the officials' dashboard shows the model's real behaviour on unseen photos:
how often it advised, asked or escalated, and how often the "expert" (ground
truth) confirmed or corrected it. Needs a trained model in ml/artifacts/.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fastapi.testclient import TestClient  # noqa: E402

import seed  # noqa: E402
from app.engine import vision  # noqa: E402
from app.kb import get_kb  # noqa: E402
from app.main import app  # noqa: E402

ROOT = HERE.parent
REVIEWER = "Demo reviewer (ICAR ground-truth label)"
PHOTOS_PER_FARM = 2
LEAVE_OPEN = 3  # escalated cases left unresolved, so the expert console has a queue


def class_to_target() -> dict[str, str]:
    meta = json.loads((vision.ARTIFACTS / "meta.json").read_text())
    return meta["class_to_target"]


def main() -> None:
    if vision.model_status()["is_stub"]:
        sys.exit("No trained model in ml/artifacts — run ml/train.py first (the story would only replay the stub).")
    if "--keep" not in sys.argv:
        sys.argv.append("--reset")
        seed.main()
    kb = get_kb()
    c2t = class_to_target()
    test = json.loads((vision.ARTIFACTS / "split.json").read_text())["test"]
    by_crop: dict[str, list[str]] = {}
    for path in test:
        cls = path.split("/")[-2]
        by_crop.setdefault(cls.split("_")[0], []).append(path)
    rng = random.Random(26131)
    for paths in by_crop.values():
        rng.shuffle(paths)

    stats = Counter()
    with TestClient(app) as c:
        sweep = c.post("/api/officials/risk/run-all").json()
        print(f"risk sweep: {sweep}")
        farms = c.get("/api/farms").json()
        for farm in farms:
            if not farm["photo_diagnosis"]:
                continue
            pool = by_crop.get(farm["crop"], [])
            for _ in range(PHOTOS_PER_FARM):
                if not pool:
                    break
                path = pool.pop()
                truth = c2t[path.split("/")[-2]]
                img = (ROOT / path).read_bytes()
                r = c.post(f"/api/farms/{farm['id']}/diagnose",
                           files={"image": ("leaf.jpg", img, "image/jpeg")},
                           data={"lang": farm["lang"]}).json()
                outcome = r["gate"]["outcome"]
                top = r["gate"]["alternatives"][0]["id"] if r["gate"]["alternatives"] else None
                stats[outcome] += 1
                case_id = r.get("case", {}).get("id") if r.get("case") else None

                if outcome == "clarify":
                    cue = next(x for x in kb.cues if x["id"] == r["clarify"]["cue_id"])
                    answer = "yes" if truth == cue["yes_means"] else "no" if truth in cue["pair"] else "unknown"
                    out = c.post(f"/api/problems/{r['problem_id']}/clarify",
                                 json={"cue_id": cue["id"], "answer": answer, "lang": farm["lang"]}).json()
                    stats[f"clarify→{out['outcome']}"] += 1
                    case_id = out.get("case", {}).get("id") if out.get("case") else None

                if case_id and truth in kb.targets and stats["left_open"] < LEAVE_OPEN and rng.random() < 0.35:
                    stats["left_open"] += 1  # keep a live queue for the expert console
                elif case_id and truth in kb.targets:
                    res = c.post(f"/api/cases/{case_id}/resolve", json={
                        "verdict": "confirmed" if truth == top else "corrected",
                        "final_label": truth, "expert_name": REVIEWER,
                        "notes": "Resolved with the ICAR dataset's label for this held-out photo.",
                    }).json()
                    stats[f"expert_{res['verdict']}"] += 1
                    stats["spread_alerts"] += res["spread_alerts"]
                elif outcome == "advise" and truth in kb.targets:
                    stats["advised_correct" if top == truth else "advised_wrong"] += 1
                print(f"  {farm['farmer_name']:22s} {farm['crop']:6s} truth={truth:32s} "
                      f"top={top:32s} → {outcome}")
    print("\nstory:", dict(stats))


if __name__ == "__main__":
    main()
