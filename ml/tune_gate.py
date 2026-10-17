"""What bar each class has to clear before the app advises on it.

`config.TARGET_GATE` holds a per-class threshold above the global `GATE`, for
classes the model names less reliably than the rest. Two entries were measured
on 2026-09-15, when the model knew twenty classes. It knows forty-six now, and
the end-to-end run on 2026-10-16 showed the newer ones are the weak half: the
gate advised on 74% of held-out photos and was right on 89.4% of those, against
95.3% on the ICAR field photos alone.

This measures the same thing those two entries were measured with, for every
class: run the deployed model over the held-out images it has never trained on,
and for each class ask what precision it would have at each candidate bar —

    precision(bar) = right / advised,  advised = top-1 is this class and
                                                 calibrated confidence >= bar

and pick the lowest bar that reaches TARGET_PRECISION, reporting the recall it
costs. A class that cannot reach it at any bar is named: no threshold saves it,
and it wants photos, not arithmetic.

    .venv/bin/python ml/tune_gate.py            # measure and print the table
    .venv/bin/python ml/tune_gate.py --write    # also rewrite TARGET_GATE

Nothing is written without --write, and what it writes is the dict, the date
and the numbers behind each entry, in the shape the file already uses.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_tmp = tempfile.mkdtemp(prefix="annrakshak-gate-")
os.environ.update({"ANNRAKSHAK_DATA_DIR": _tmp, "ANNRAKSHAK_DB_URL": f"sqlite:///{_tmp}/gate.db",
                   "ANNRAKSHAK_WATCH": "off", "REDIS_URL": ""})
os.environ.pop("ANNRAKSHAK_VISION", None)  # the real model, not the stub
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from app.engine import vision  # noqa: E402
from holdout import target_of  # noqa: E402

ART = ROOT / "ml" / "artifacts"
BARS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
TARGET_PRECISION = 0.95
"""The bar the two measured entries were chosen to reach: rice blast went from
0.868 precision at 0.70 to 0.957 at 0.90. A class already above it at the
global gate needs no entry of its own."""

MEANINGFUL_GAIN = 0.02
"""How much precision a higher bar must buy a class that cannot reach the
target before it is worth the recall it costs. Below this the bar is noise on a
handful of held-out images, and the class wants photographs instead."""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="rewrite config.TARGET_GATE with what is measured")
    ap.add_argument("--limit", type=int, default=0, help="images per class, for a quick look")
    ap.add_argument("--from-scan", action="store_true",
                    help="reuse ml/reports/gate_scan.json instead of running the model again")
    args = ap.parse_args()

    meta = json.loads((ART / "meta.json").read_text())
    split = json.loads((ART / "split.json").read_text())
    c2t, targets = meta["class_to_target"], set(meta["class_to_target"].values())

    held_out = [ROOT / p for p in split["test"] + split.get("extra_test", [])]
    by_class: dict[str, list[Path]] = defaultdict(list)
    for p in held_out:
        by_class[p.parent.name].append(p)

    scan_path = ROOT / "ml" / "reports" / "gate_scan.json"
    if args.from_scan:
        cached = json.loads(scan_path.read_text())
        said = [(t, p, c) for t, p, c in cached["said"]]
        print(f"model: {cached['model']} (from {scan_path.relative_to(ROOT)}, {len(said)} predictions)\n")
        report(said, args)
        return

    status = vision.model_status()
    if status["is_stub"]:
        sys.exit("the real model is not loaded (ml/artifacts/model.pt)")
    print(f"model: {status['model_version']}\nheld-out images: {len(held_out)}\n")

    # One pass over every held-out image: what the model says, and how sure.
    said: list[tuple[str, str, float]] = []   # (true target, predicted target, confidence)
    skipped: dict[str, int] = {}
    for folder, paths in sorted(by_class.items()):
        truth = target_of(folder, c2t)
        if truth is None:
            skipped[folder] = len(paths)
            continue
        crop = folder.split("_")[0]
        for p in (paths[: args.limit] if args.limit else paths):
            topk = vision.classify(p.read_bytes(), crop)
            if topk.out_of_scope:
                continue        # the gate never reaches a threshold on these
            top = topk.predictions[0]
            said.append((truth, top.target, top.confidence))
    for folder, n in skipped.items():
        print(f"skipped {folder}: {n} images, no target in this model")
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text(json.dumps({"model": status["model_version"], "said": said}))
    print(f"raw scores: {scan_path.relative_to(ROOT)} ({len(said)} predictions)")
    report(said, args)


def report(said: list, args) -> None:

    # For each class, precision and recall at each candidate bar.
    rows = []
    for target in sorted({t for t, _, _ in said}):
        seen = sum(1 for t, _, _ in said if t == target)
        best = None
        at_bar = {}
        for bar in BARS:
            advised = [(t, p) for t, p, c in said if p == target and c >= bar]
            right = sum(1 for t, p in advised if t == p)
            precision = right / len(advised) if advised else None
            recall = right / seen if seen else 0.0
            at_bar[bar] = (precision, recall, len(advised))
            if best is None and precision is not None and precision >= TARGET_PRECISION:
                best = bar
        base = at_bar[BARS[0]]
        rows.append({"target": target, "seen": seen, "at_gate": base, "bar": best, "at_bar": at_bar})

    print(f"\n{'class':34s} {'held-out':>8s} {'P@0.70':>7s} {'bar':>6s} {'P@bar':>7s} {'recall':>7s}")
    needs: dict[str, float] = {}
    hopeless = []
    for r in rows:
        p0 = r["at_gate"][0]
        if r["bar"] is None:
            hopeless.append(r)
            bar_s, pbar_s, rec_s = "none", "—", "—"
        else:
            p, rec, _ = r["at_bar"][r["bar"]]
            bar_s, pbar_s, rec_s = f"{r['bar']:.2f}", f"{p:.3f}", f"{rec:.3f}"
            if r["bar"] > BARS[0]:
                needs[r["target"]] = r["bar"]
        print(f"{r['target']:34s} {r['seen']:8d} {('—' if p0 is None else f'{p0:.3f}'):>7s} "
              f"{bar_s:>6s} {pbar_s:>7s} {rec_s:>7s}")

    # A class that never reaches the target still gets the bar that does best
    # for it, provided that bar actually buys precision: for the classes with a
    # dozen held-out images the best bar is the global one, and raising it would
    # cost recall for nothing.
    unhelped = []
    for r in hopeless:
        scored = [(b, v) for b, v in r["at_bar"].items() if v[0] is not None]
        if not scored:
            continue
        bar, (p, rec, _) = max(scored, key=lambda kv: kv[1][0])
        base = r["at_gate"][0] or 0.0
        if bar > BARS[0] and p - base >= MEANINGFUL_GAIN:
            needs[r["target"]] = bar
            r["chosen"] = (bar, p, rec, base)
        else:
            unhelped.append(r)

    print(f"\n{len(needs)} class(es) want a bar above the global {BARS[0]:.2f}:")
    for t, bar in sorted(needs.items()):
        p0 = next(r["at_gate"][0] for r in rows if r["target"] == t)
        p1 = r_at = next(r["at_bar"][bar] for r in rows if r["target"] == t)
        print(f"  {t}: {p0:.3f} at {BARS[0]:.2f} -> {p1[0]:.3f} at {bar:.2f} (recall {r_at[1]:.3f})")
    if unhelped:
        print(f"\n{len(unhelped)} class(es) no bar can help — these want photographs, not arithmetic:")
        for r in unhelped:
            best_bar, (best_p, best_rec, _) = max(
                ((b, v) for b, v in r["at_bar"].items() if v[0] is not None),
                key=lambda kv: kv[1][0], default=(None, (None, 0.0, 0)))
            said_best = "—" if best_p is None else f"{best_p:.3f} at {best_bar:.2f} (recall {best_rec:.3f})"
            print(f"  {r['target']}: best {said_best}, on {r['seen']} held-out images")

    if args.write:
        write_config(needs, rows)
        print("\nconfig.TARGET_GATE rewritten.")


def write_config(needs: dict[str, float], rows: list[dict]) -> None:
    """Rewrite the dict in backend/app/config.py, keeping the shape and the
    docstring's habit of carrying the numbers behind each entry."""
    from datetime import date

    cfg = ROOT / "backend" / "app" / "config.py"
    s = cfg.read_text()
    start = s.index("TARGET_GATE = {")
    end = s.index("assert all(v >= GATE for v in TARGET_GATE.values())")

    lines = ["TARGET_GATE = {"]
    for t, bar in sorted(needs.items()):
        lines.append(f'    "{t}": {bar:.2f},')
    lines.append("}")
    detail = []
    for t, bar in sorted(needs.items()):
        r = next(x for x in rows if x["target"] == t)
        p0 = r["at_gate"][0]
        p1, rec, _ = r["at_bar"][bar]
        mark = "" if p1 >= TARGET_PRECISION else " (best)"
        detail.append(f"{t.replace('_', ' ')} {p0:.3f} -> {p1:.3f} at {bar:.2f} (recall {rec:.3f}){mark}")
    body = ";\n".join(detail) if detail else "nothing above the global gate"
    lines += [
        '"""Classes the model names less reliably than the rest must clear a higher',
        "bar before the app advises them — in the photo gate and for a 'strong' view",
        f"in the live walk. Measured by ml/tune_gate.py on held-out images ({date.today()}),",
        f"choosing the lowest bar reaching {TARGET_PRECISION:.2f} precision, or, where no bar",
        "reaches it, the bar that does best — those are marked (best) and want more",
        "field photographs rather than more arithmetic:",
        f"{body}.",
        "Between GATE and this bar the gate asks the look-alike question or sends the",
        "photo to an expert. Drop an entry once expert confirmations show the class",
        'holds up on farmers\' field photos."""',
        "",
    ]
    cfg.write_text(s[:start] + "\n".join(lines) + s[end:])


if __name__ == "__main__":
    main()
