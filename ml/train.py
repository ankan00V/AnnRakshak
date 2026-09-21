"""Train, compare, calibrate and report the ICAR rice & maize classifier.

    .venv/bin/python ml/train.py            # full run (~15-25 min on an M-series Mac)
    .venv/bin/python ml/train.py --quick    # smoke run, 1 epoch each

Pipeline
  1. Stratified 70/15/15 train/val/test split of the 835 de-duplicated images
     (data/processed/icar_images.csv, from data/ingest.py). The test split is
     touched only for the final numbers.
  2. Benchmark, following Singh et al. (IJCISIM 2026): frozen ImageNet
     backbones (DenseNet201, EfficientNetV2-S, MobileNetV3) + a
     1024-512-256-128 ANN head trained on pooled features.
  3. Fine-tune, following Haider et al. (VTSE 2024): EfficientNetV2-S end to
     end with rotation/flip/crop augmentation.
  4. Deploy the candidate with the best validation macro-F1; fit a softmax
     temperature on validation so a 0.8 means right ~80% of the time.
  5. Run the real confidence gate over the test set: how often it advises,
     asks or escalates, and how accurate it is when it does advise.

Writes ml/artifacts/{model.pt,meta.json} (gitignored) and ml/reports/
(MODEL_REPORT.md stays local — only READMEs are committed; the confusion
matrix and Grad-CAM gallery images are committed).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from PIL import Image  # noqa: E402
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.engine.gate import Prediction, TopK, decide  # noqa: E402
from app.engine.model import Net, best_device, gradcam, test_transform, train_transform  # noqa: E402
from app.kb import get_kb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from composite import composite  # noqa: E402

MANIFEST = ROOT / "data" / "processed" / "icar_images.csv"
EXTRA_MANIFEST = ROOT / "data" / "processed" / "extra_images.csv"
MORE_MANIFEST = ROOT / "data" / "processed" / "more_images.csv"
ART = ROOT / "ml" / "artifacts"
REP = ROOT / "ml" / "reports"
SEED = 42
IMG = 300
# --with-extra: how many extra-source images per class may enter each split.
# Classes the ICAR set already has get fewer, so its field photos keep weight.
EXTRA_CAP_NEW = {"train": 300, "val": 40, "test": 80}
EXTRA_CAP_EXISTING = {"train": 150, "val": 30, "test": 60}
# --with-more: the cotton, soybean and extra maize/rice sets (data/ingest_more.py).
# Cotton and soybean have no ICAR photos at all — their classes are carried by
# this source alone, so it may bring as much as it has. Raised from 420 after the
# first cotton/soybean candidate missed the deploy bar on soybean rust, septoria
# and caterpillar recall: those classes have 300-865 images and were being cut in
# half for no reason.
MORE_CAP_NEW = {"train": 700, "val": 100, "test": 150}
MORE_CAP_EXISTING = {"train": 350, "val": 50, "test": 90}
COMPOSITE_P = 0.85


def seed_all(s: int = SEED) -> None:
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)


class Images(Dataset):
    """backgrounds: {crop: [paths]} of healthy field photos. Rows flagged
    bg=plain are pasted onto one of them — with probability p when training,
    always (and deterministically per index) for evaluation."""

    def __init__(self, rows, class_idx, tf, backgrounds=None, p=0.0, deterministic=False):
        self.rows, self.class_idx, self.tf = rows, class_idx, tf
        self.backgrounds, self.p, self.deterministic = backgrounds or {}, p, deterministic

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]
        with Image.open(ROOT / r["path"]) as im:
            im = im.convert("RGB")
            pool = self.backgrounds.get(r["crop"])
            if pool and r.get("bg") == "plain":
                rng = random.Random(SEED * 100003 + i) if self.deterministic else random
                if self.deterministic or rng.random() < self.p:
                    with Image.open(ROOT / rng.choice(pool)) as bg:
                        im = composite(im, bg, rng)
            x = self.tf(im)
        return x, self.class_idx[r["train_class"]]


def load_split():
    rows = list(csv.DictReader(MANIFEST.open()))
    labels = [r["train_class"] for r in rows]
    train, rest = train_test_split(rows, test_size=0.30, stratify=labels, random_state=SEED)
    val, test = train_test_split(rest, test_size=0.50, stratify=[r["train_class"] for r in rest],
                                 random_state=SEED)
    return train, val, test


# 2 workers, not 4: on a 16 GB laptop the extra copies of the dataset cost more
# in memory pressure than they save in decode time (an item takes ~4 ms).
WORKERS = int(os.environ.get("ANNRAKSHAK_WORKERS", "2"))


def loader(rows, class_idx, tf, shuffle, bs=16, sampler=None, **ds):
    return DataLoader(Images(rows, class_idx, tf, **ds), batch_size=bs, shuffle=shuffle and sampler is None,
                      sampler=sampler, num_workers=WORKERS, persistent_workers=WORKERS > 0)


def balanced_sampler(rows, epoch_size, icar_share=0.5):
    """Every class equally likely per epoch; inside a class that has both ICAR
    and extra-source photos, the ICAR field photos get `icar_share` of the
    class's weight and the extra sources split the rest."""
    by_class: dict[str, Counter] = {}
    for r in rows:
        by_class.setdefault(r["train_class"], Counter())[r.get("source", "icar")] += 1
    w = []
    def field(s):  # real field photos: ICAR's, and farmers' photos an expert labelled
        return s in ("icar", "confirmed")

    for r in rows:
        src = by_class[r["train_class"]]
        s = r.get("source", "icar")
        n_field = sum(v for k, v in src.items() if field(k))
        n_other = sum(v for k, v in src.items() if not field(k))
        if not n_field or not n_other:
            share, pool = 1.0, (n_field or n_other)
        elif field(s):
            share, pool = icar_share, n_field
        else:
            share, pool = 1.0 - icar_share, n_other
        w.append(share / pool)
    return WeightedRandomSampler(torch.tensor(w, dtype=torch.double), num_samples=epoch_size, replacement=True)


def load_extra_split(manifest=None, cap_new=None, cap_existing=None, known=None):
    """Extra-source rows split per class (seeded, stratified), capped. A class
    the ICAR set already covers gets the smaller cap, so ICAR's field photos
    keep their weight."""
    rows = list(csv.DictReader((manifest or EXTRA_MANIFEST).open()))
    icar_classes = known if known is not None else {r["train_class"] for r in csv.DictReader(MANIFEST.open())}
    cap_new, cap_existing = cap_new or EXTRA_CAP_NEW, cap_existing or EXTRA_CAP_EXISTING
    rng = random.Random(SEED)
    by_class: dict[str, list] = {}
    for r in rows:
        by_class.setdefault(r["train_class"], []).append(r)
    out = {"train": [], "val": [], "test": []}
    for cls, items in sorted(by_class.items()):
        items = sorted(items, key=lambda r: r.get("sha1") or r["dhash"] + r["path"])
        rng.shuffle(items)
        n = len(items)
        cut1, cut2 = int(n * 0.70), int(n * 0.85)
        caps = cap_existing if cls in icar_classes else cap_new
        for split, part in (("train", items[:cut1]), ("val", items[cut1:cut2]), ("test", items[cut2:])):
            out[split] += part[: caps[split]]
    return out["train"], out["val"], out["test"]


@torch.no_grad()
def logits_of(net, dl, device):
    net.train(False)
    out, ys = [], []
    for x, y in dl:
        out.append(net(x.to(device)).float().cpu())
        ys.append(y)
    return torch.cat(out), torch.cat(ys)


def scores(y, pred):
    p, r, f, _ = precision_recall_fscore_support(y, pred, average="macro", zero_division=0)
    return {"accuracy": float((np.asarray(y) == np.asarray(pred)).mean()),
            "precision": float(p), "recall": float(r), "f1": float(f)}


# --------------------------------------------------------------------------
# Paper 2 method: frozen backbone features + ANN head
# --------------------------------------------------------------------------

@torch.no_grad()
def extract(net, rows, class_idx, tf, device, views=1):
    net.train(False)
    feats, ys = [], []
    for _ in range(views):
        for x, y in loader(rows, class_idx, tf, shuffle=False, bs=32):
            feats.append(net.pooled(x.to(device)).float().cpu())
            ys.append(y)
    return torch.cat(feats), torch.cat(ys)


def train_ann(backbone, train, val, class_idx, device, quick):
    n = len(class_idx)
    net = Net(backbone, n, "ann").to(device)
    t0 = time.time()
    views = 1 if quick else 4
    xtr, ytr = extract(net, train, class_idx, train_transform(IMG), device, views)
    xva, yva = extract(net, val, class_idx, test_transform(IMG), device)
    head = net.head.cpu()
    opt = torch.optim.Adam(head.parameters(), lr=1e-3, weight_decay=1e-4)
    best, best_state, patience = -1.0, None, 0
    for epoch in range(5 if quick else 300):
        head.train()
        perm = torch.randperm(len(xtr))
        for i in range(0, len(perm), 64):
            idx = perm[i:i + 64]
            loss = F.cross_entropy(head(xtr[idx]), ytr[idx], label_smoothing=0.1)
            opt.zero_grad()
            loss.backward()
            opt.step()
        head.train(False)
        with torch.no_grad():
            f1 = scores(yva.numpy(), head(xva).argmax(1).numpy())["f1"]
        if f1 > best:
            best, best_state, patience = f1, {k: v.clone() for k, v in head.state_dict().items()}, 0
        else:
            patience += 1
            if patience >= 40:
                break
    head.load_state_dict(best_state)
    net.head = head.to(device)
    print(f"  {backbone}+ANN: val macro-F1 {best:.3f} ({time.time() - t0:.0f}s, {epoch + 1} epochs)")
    return net, best


# --------------------------------------------------------------------------
# Paper 1 method: fine-tune end to end
# --------------------------------------------------------------------------

def warm_start(net, state: dict, old_classes: list[str], class_idx: dict[str, int]) -> list[str]:
    """Continual learning: load a deployed model's backbone, and copy its head
    rows for every class it already knows. Only new classes start from scratch,
    so what the old model learnt from the ICAR photos is kept, not relearnt."""
    net.features.load_state_dict({k[len("features."):]: v for k, v in state.items() if k.startswith("features.")})
    w_old, b_old = state["head.1.weight"], state["head.1.bias"]
    lin = net.head[1]
    new = []
    with torch.no_grad():
        for c, i in class_idx.items():
            if c in old_classes:
                j = old_classes.index(c)
                lin.weight[i].copy_(w_old[j])
                lin.bias[i].copy_(b_old[j])
            else:
                new.append(c)
    return new


def finetune(backbone, train, val, class_idx, device, quick, epochs, backgrounds=None, val_backgrounds=None,
             epoch_size=None, init=None, icar_share=0.5, freeze_all=False, lr_override=None):
    net = Net(backbone, len(class_idx), "finetune").to(device)
    lr_feat, lr_head, warm = 1.5e-4, 1e-3, 3
    if init is not None:  # (state_dict, class list) of the deployed model
        new = warm_start(net, init[0], init[1], class_idx)
        net.to(device)
        # A gentle rate protects what the model already knows, and is right when a
        # run only refreshes known classes. Bringing in a whole new crop is not
        # that: those head rows start from noise, and at 5e-5 the backbone never
        # moves far enough to grow features for them. So the rate follows how much
        # is actually new (this is why the first cotton/soybean candidate plateaued).
        share_new = len(new) / max(len(class_idx), 1)
        if share_new > 0.1:
            lr_feat, lr_head, warm = 1.2e-4, 1e-3, 3
        else:
            lr_feat, lr_head, warm = 5e-5, 5e-4, 2
        if freeze_all:
            # The backbone stays exactly as the deployed model learnt it, so the
            # rice and maize features that model was trusted for cannot be
            # damaged; only the head learns, and it is the only thing that has to.
            lr_feat, lr_head, warm = 0.0, 2e-3, 0
        if lr_override:  # a continuation that must barely move the backbone
            lr_feat, lr_head, warm = lr_override[0], lr_override[1], 1
        print(f"  warm start from the deployed model; new classes ({len(new)}): {new}")
        print(f"  lr feat {lr_feat:g} head {lr_head:g} ({share_new:.0%} of classes are new)")
    if backgrounds:
        dl_tr = loader(train, class_idx, train_transform(IMG), shuffle=True,
                       sampler=balanced_sampler(train, epoch_size or len(train), icar_share),
                       backgrounds=backgrounds, p=COMPOSITE_P)
        dl_va = loader(val, class_idx, test_transform(IMG), shuffle=False,
                       backgrounds=val_backgrounds, deterministic=True)
    else:
        dl_tr = loader(train, class_idx, train_transform(IMG), shuffle=True)
        dl_va = loader(val, class_idx, test_transform(IMG), shuffle=False)
    n_seen = len(dl_tr.sampler) if backgrounds else len(train)
    epochs = 1 if quick else epochs
    warm = 0 if quick else warm
    params = [
        {"params": net.features.parameters(), "lr": lr_feat},
        {"params": net.head.parameters(), "lr": lr_head},
    ]
    opt = torch.optim.AdamW(params, weight_decay=0.02)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=[lr_feat, lr_head], total_steps=(epochs + warm) * len(dl_tr), pct_start=0.15)
    best, best_state, history = -1.0, None, []
    t0 = time.time()
    for epoch in range(warm + epochs):
        frozen = freeze_all or epoch < warm
        for p in net.features.parameters():
            p.requires_grad = not frozen
        net.train()
        if frozen:
            # requires_grad=False stops the weights moving; it does NOT stop
            # batch-norm updating its running mean and variance, and in training
            # mode it does that on every batch. The backbone would drift while
            # being called frozen — exactly what this run exists to prevent — so
            # the feature extractor is put in inference mode as well.
            net.features.train(False)
        total = 0.0
        for x, y in dl_tr:
            x, y = x.to(device), y.to(device)
            if frozen:  # no gradients through the backbone: the forward pass is
                with torch.no_grad():  # then the only cost, and epochs halve
                    feats = net.pooled(x)
                logits = net.head(feats)
            else:
                logits = net(x)
            loss = F.cross_entropy(logits, y, label_smoothing=0.1)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(y)
        lv, yv = logits_of(net, dl_va, device)
        s = scores(yv.numpy(), lv.argmax(1).numpy())
        history.append({"epoch": epoch + 1, "frozen_backbone": frozen,
                        "train_loss": round(total / n_seen, 4), "val_f1": round(s["f1"], 4),
                        "val_acc": round(s["accuracy"], 4)})
        print(f"  {backbone} fine-tune epoch {epoch + 1:2d}{' (head only)' if frozen else ''}: "
              f"loss {total / n_seen:.3f}  val acc {s['accuracy']:.3f}  F1 {s['f1']:.3f}  "
              f"[{time.time() - t0:.0f}s]")
        if s["f1"] > best:
            best, best_state = s["f1"], {k: v.detach().clone() for k, v in net.state_dict().items()}
        if device.type == "mps":  # a 16 GB laptop swaps without this
            torch.mps.empty_cache()
    net.load_state_dict(best_state)
    return net, best, history


# --------------------------------------------------------------------------
# Calibration and the gate
# --------------------------------------------------------------------------

def fit_temperature(logits: torch.Tensor, y: torch.Tensor) -> float:
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / log_t.exp(), y)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp().clamp(0.05, 20.0))


def ece(probs: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    conf, pred = probs.max(1), probs.argmax(1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(total)


def gate_simulation(probs, rows, classes, class_to_target, model_targets=None):
    """model_targets: targets this model was trained on — treated as
    photo-diagnosable even if the KB still lists them as inspection-only
    (the KB tier is updated when such a model is deployed)."""
    kb = get_kb()
    covered = set(model_targets or ())

    def tier_of(t):
        return "diagnosable" if t in covered else kb.targets.get(t, {}).get("tier")

    out = Counter()
    advised = correct_advised = clarified = pair_has_truth = 0
    for p, r in zip(probs, rows):
        by_t: dict[str, float] = {}
        for c, v in zip(classes, p):
            by_t[class_to_target[c]] = by_t.get(class_to_target[c], 0.0) + float(v)
        ranked = sorted(by_t.items(), key=lambda kv: kv[1], reverse=True)[:3]
        d = decide(TopK([Prediction(t, c) for t, c in ranked], "eval", False), farm_crop=r["crop"],
                   tier_of=tier_of, has_advisory=lambda t: t in kb.advisories, cue_for=kb.cue_for)
        out[d.outcome] += 1
        truth = r["target"]
        if d.outcome == "advise":
            advised += 1
            correct_advised += ranked[0][0] == truth
        elif d.outcome == "clarify":
            clarified += 1
            pair_has_truth += truth in (ranked[0][0], ranked[1][0])
    n = len(rows)
    return {
        "n": n,
        "advise_pct": round(100 * out["advise"] / n, 1),
        "clarify_pct": round(100 * out["clarify"] / n, 1),
        "escalate_pct": round(100 * out["escalate"] / n, 1),
        "accuracy_when_advised": round(correct_advised / advised, 4) if advised else None,
        "clarify_pair_contains_truth": round(pair_has_truth / clarified, 4) if clarified else None,
    }


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

def plot_confusion(y, pred, classes, path):
    cm = confusion_matrix(y, pred, labels=range(len(classes)))
    fig, ax = plt.subplots(figsize=(11, 9))
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(len(classes)), classes, rotation=75, ha="right", fontsize=8)
    ax.set_yticks(range(len(classes)), classes, fontsize=8)
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=8,
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Held-out test set — confusion matrix")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_gradcam(net, rows, classes, device, path, n=12):
    tf = test_transform(IMG)
    picks = rows[:: max(1, len(rows) // n)][:n]
    fig, axes = plt.subplots(3, 4, figsize=(13, 10))
    net = net.to(device)
    for ax, r in zip(axes.flat, picks):
        with Image.open(ROOT / r["path"]) as im:
            im = im.convert("RGB")
            x = tf(im).unsqueeze(0).to(device).requires_grad_(True)
        with torch.no_grad():
            pred = int(net(x).argmax(1))
        with torch.enable_grad():
            cam = gradcam(net, x, pred)
        shown = im.resize((IMG, IMG))
        ax.imshow(shown)
        ax.imshow(np.array(Image.fromarray((cam * 255).astype(np.uint8)).resize((IMG, IMG), Image.BILINEAR)),
                  cmap="jet", alpha=0.4)
        ok = classes[pred] == r["train_class"]
        ax.set_title(f"true: {r['train_class']}\npred: {classes[pred]}", fontsize=8,
                     color="darkgreen" if ok else "crimson")
        ax.axis("off")
    fig.suptitle("Grad-CAM: where the model looked (test images)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--epochs", type=int, default=22)
    ap.add_argument("--skip-benchmark", action="store_true")
    ap.add_argument("--with-confirmed", action="store_true",
                    help="with --with-extra: add expert-labelled field photos from ml/export_confirmed.py")
    ap.add_argument("--warm-start", action="store_true",
                    help="with --with-extra: continue from the deployed model instead of ImageNet weights")
    ap.add_argument("--from-candidate", action="store_true",
                    help="continue from ml/artifacts/candidate (a run that did not pass the deploy gate)")
    ap.add_argument("--per-class", type=int, default=120,
                    help="with --with-extra: samples drawn per class per epoch")
    ap.add_argument("--with-more", action="store_true",
                    help="also the cotton, soybean and extra maize/rice sets (data/processed/more_images.csv)")
    ap.add_argument("--lr-feat", type=float, default=None,
                    help="backbone learning rate for a continuation (with --lr-head)")
    ap.add_argument("--lr-head", type=float, default=3e-4)
    ap.add_argument("--freeze-backbone", action="store_true",
                    help="train only the head; the deployed model's features are left untouched")
    ap.add_argument("--with-extra", action="store_true",
                    help="v2: add the extra sources (blast, rust, field FAW) with background randomisation")
    args = ap.parse_args()
    if args.with_extra:
        return main_extra(args)
    seed_all()
    device = best_device()
    ART.mkdir(parents=True, exist_ok=True)
    REP.mkdir(parents=True, exist_ok=True)

    train, val, test = load_split()
    classes = sorted({r["train_class"] for r in train + val + test})
    class_idx = {c: i for i, c in enumerate(classes)}
    class_to_target = {r["train_class"]: r["target"] for r in train + val + test}
    print(f"device={device}  train={len(train)} val={len(val)} test={len(test)}  classes={len(classes)}")
    (ART / "split.json").write_text(json.dumps(
        {k: [r["path"] for r in v] for k, v in {"train": train, "val": val, "test": test}.items()}, indent=0))

    candidates = []
    if not args.skip_benchmark:
        print("benchmark — frozen backbone + ANN head (Singh et al.):")
        for bb in ("densenet201", "efficientnet_v2_s", "mobilenet_v3_large"):
            net, f1 = train_ann(bb, train, val, class_idx, device, args.quick)
            candidates.append({"name": f"{bb} + ANN (frozen)", "backbone": bb, "head": "ann",
                               "val_f1": f1, "net": net, "history": None})
    print("fine-tune — EfficientNetV2-S end to end (Haider et al.):")
    net, f1, hist = finetune("efficientnet_v2_s", train, val, class_idx, device, args.quick, args.epochs)
    candidates.append({"name": "efficientnet_v2_s fine-tuned", "backbone": "efficientnet_v2_s",
                       "head": "finetune", "val_f1": f1, "net": net, "history": hist})

    dl_va = loader(val, class_idx, test_transform(IMG), shuffle=False)
    dl_te = loader(test, class_idx, test_transform(IMG), shuffle=False)
    table = []
    for c in candidates:
        lt, yt = logits_of(c["net"], dl_te, device)
        s = scores(yt.numpy(), lt.argmax(1).numpy())
        c["test"] = s
        table.append({"model": c["name"], "val_f1": round(c["val_f1"], 4),
                      **{k: round(v, 4) for k, v in s.items()}})
        print(f"  TEST {c['name']:34s} acc {s['accuracy']:.3f}  P {s['precision']:.3f}  "
              f"R {s['recall']:.3f}  F1 {s['f1']:.3f}")

    best = max(candidates, key=lambda c: c["val_f1"])
    net = best["net"]
    lv, yv = logits_of(net, dl_va, device)
    T = fit_temperature(lv, yv)
    lt, yt = logits_of(net, dl_te, device)
    p_raw = torch.softmax(lt, 1).numpy()
    p_cal = torch.softmax(lt / T, 1).numpy()
    y = yt.numpy()
    pred = p_cal.argmax(1)
    gate = gate_simulation(p_cal, test, classes, class_to_target)
    per_class = precision_recall_fscore_support(y, pred, labels=range(len(classes)), zero_division=0)

    version = f"icar-{best['backbone']}-{best['head']}-{datetime.now(UTC):%Y%m%d}"
    meta = {
        "model_version": version,
        "backbone": best["backbone"],
        "head": best["head"],
        "img_size": IMG,
        "classes": classes,
        "class_to_target": class_to_target,
        "temperature": round(T, 4),
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset": "ICAR Crop Disease and Insect-pest Image Dataset for Rice and Maize (835 unique images)",
        "split": {"train": len(train), "val": len(val), "test": len(test), "seed": SEED, "stratified": True},
        "test": {**{k: round(v, 4) for k, v in best["test"].items()},
                 "ece_before": round(ece(p_raw, y), 4), "ece_after": round(ece(p_cal, y), 4)},
        "gate_on_test": gate,
        "benchmark": table,
        "history": best["history"],
        "quick": args.quick,
    }
    torch.save(net.cpu().state_dict(), ART / "model.pt")
    (ART / "meta.json").write_text(json.dumps(meta, indent=1))

    plot_confusion(y, pred, classes, REP / "confusion_matrix.png")
    plot_gradcam(net, test, classes, torch.device("cpu"), REP / "gradcam_samples.png")

    lines = [
        "# AnnRakshak vision model — report",
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `ml/train.py`{' (QUICK smoke run — not real numbers)' if args.quick else ''}.",
        "",
        f"**Data:** {meta['dataset']}; 17 training classes (fall armyworm larvae and damage are separate classes "
        f"merged into one advisory target). Stratified split, seed {SEED}: "
        f"{len(train)} train / {len(val)} validation / {len(test)} test. Exact duplicate images were removed "
        "before splitting so no photo appears on both sides.",
        "",
        "## Model comparison (held-out test set)",
        "",
        "| Model | Val macro-F1 | Test accuracy | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|",
        *[f"| {r['model']} | {r['val_f1']:.3f} | {r['accuracy']:.3f} | {r['precision']:.3f} | "
          f"{r['recall']:.3f} | {r['f1']:.3f} |" for r in table],
        "",
        f"Deployed: **{best['name']}** (best validation macro-F1). Version `{version}`.",
        "",
        "## Calibration",
        "",
        f"Softmax temperature fitted on validation: **T = {T:.3f}**. Expected calibration error on test: "
        f"{meta['test']['ece_before']:.3f} → **{meta['test']['ece_after']:.3f}**. Calibrated confidence is what the "
        "gate compares against its thresholds.",
        "",
        "## The confidence gate on the test set",
        "",
        "Every test image run through the production gate (same code as the API), using the image's own crop as "
        "the farm crop:",
        "",
        f"- Advised directly: **{gate['advise_pct']}%** of images, and **{100 * (gate['accuracy_when_advised'] or 0):.1f}%** "
        f"of those advisories were correct (vs {100 * best['test']['accuracy']:.1f}% raw top-1 accuracy).",
        f"- Sent to the Doubt Doctor: {gate['clarify_pct']}% — the true label was one of the two candidates in "
        f"{100 * (gate['clarify_pair_contains_truth'] or 0):.1f}% of those.",
        f"- Escalated to an expert: {gate['escalate_pct']}%.",
        "",
        "## Per-class results (deployed model, test set)",
        "",
        "| Class | Precision | Recall | F1 | Test images |",
        "|---|---|---|---|---|",
        *[f"| {c} | {per_class[0][i]:.2f} | {per_class[1][i]:.2f} | {per_class[2][i]:.2f} | {per_class[3][i]} |"
          for i, c in enumerate(classes)],
        "",
        "![confusion matrix](confusion_matrix.png)",
        "",
        "![Grad-CAM samples](gradcam_samples.png)",
        "",
        "## Read this before quoting the numbers",
        "",
        "- ~50 images per class and a test set of about 8 images per class: one image is ~12 points of per-class "
        "recall. Treat per-class numbers as indicative.",
        "- The images come from one dataset; field photos from farmers' phones will differ (lighting, framing, "
        "damage rather than the insect). Field accuracy is measured separately, from expert confirmations, on the "
        "officials' dashboard.",
        "- The model cannot recognise diseases it was never shown (e.g. rice blast). Those stay on the risk-alert "
        "and inspection path; see data/DATASETS.md.",
    ]
    (REP / "MODEL_REPORT.md").write_text("\n".join(lines) + "\n")
    print(f"deployed {best['name']} → {ART / 'model.pt'}  T={T:.3f}  gate={gate}")


# --------------------------------------------------------------------------
# v2: ICAR + extra sources, background randomisation, deploy-if-not-worse
# --------------------------------------------------------------------------

def per_class_recall(y, pred, classes):
    out = {}
    for i, c in enumerate(classes):
        m = y == i
        if m.any():
            out[c] = {"n": int(m.sum()), "recall": round(float((pred[m] == i).mean()), 4)}
    return out


def main_extra(args):
    seed_all()
    device = best_device()
    cand_dir = ART / "candidate"
    cand_dir.mkdir(parents=True, exist_ok=True)
    REP.mkdir(parents=True, exist_ok=True)

    icar = {r["path"]: r for r in csv.DictReader(MANIFEST.open())}
    for r in icar.values():
        r["source"], r["bg"] = "icar", "field"
    prev_meta = json.loads((ART / "meta.json").read_text()) if (ART / "meta.json").exists() else None
    split_file = ART / "split.json"
    if split_file.exists():  # keep the deployed model's ICAR split so the test set is identical
        sp = json.loads(split_file.read_text())
        i_tr, i_va, i_te = ([icar[p] for p in sp[k]] for k in ("train", "val", "test"))
    else:
        i_tr, i_va, i_te = load_split()
    e_tr, e_va, e_te = load_extra_split()
    if getattr(args, "with_more", False):
        known = {r["train_class"] for r in list(icar.values()) + e_tr + e_va + e_te}
        m_tr, m_va, m_te = load_extra_split(MORE_MANIFEST, MORE_CAP_NEW, MORE_CAP_EXISTING, known)
        e_tr, e_va, e_te = e_tr + m_tr, e_va + m_va, e_te + m_te
        print(f"with cotton, soybean and more maize/rice: {len(m_tr)}/{len(m_va)}/{len(m_te)} "
              f"images over {len({r['train_class'] for r in m_tr})} classes (data/ingest_more.py)")
    if getattr(args, "with_confirmed", False):
        conf_csv = ROOT / "data" / "processed" / "confirmed.csv"
        if conf_csv.exists():
            known = {r["train_class"] for r in list(icar.values()) + e_tr}
            confirmed = [r for r in csv.DictReader(conf_csv.open()) if r["train_class"] in known]
            e_tr = e_tr + confirmed  # all to training: the held-out sets stay comparable across runs
            print(f"with {len(confirmed)} expert-labelled field photos (ml/export_confirmed.py)")
    train, val = i_tr + e_tr, i_va + e_va
    classes = sorted({r["train_class"] for r in train + val + i_te + e_te})
    class_idx = {c: i for i, c in enumerate(classes)}
    class_to_target = {r["train_class"]: r["target"] for r in train + val + i_te + e_te}
    model_targets = sorted(set(class_to_target.values()))

    def healthy(rows, crop):
        return [r["path"] for r in rows if r["train_class"] == f"{crop}_healthy" and r["bg"] == "field"]

    crops = tuple(sorted({r["crop"] for r in train + val + i_te + e_te}))
    bgs = {"train": {c: healthy(i_tr + e_tr, c) for c in crops},
           "val": {c: healthy(i_va + e_va, c) for c in crops},
           "test": {c: healthy(i_te + e_te, c) for c in crops}}
    epoch_size = 96 if args.quick else args.per_class * len(classes)
    print(f"device={device}  classes={len(classes)}  ICAR {len(i_tr)}/{len(i_va)}/{len(i_te)}  "
          f"extra {len(e_tr)}/{len(e_va)}/{len(e_te)}  epoch={epoch_size or len(train)} samples  "
          f"backgrounds train={ {c: len(v) for c, v in bgs['train'].items()} }")

    init, icar_share = None, 0.5
    if args.warm_start or args.from_candidate:
        # --from-candidate continues a candidate that did not pass the deploy gate,
        # without touching the model the app is serving.
        src = cand_dir if args.from_candidate else ART
        src_meta = json.loads((src / "meta.json").read_text()) if (src / "meta.json").exists() else None
        if not src_meta or not (src / "model.pt").exists():
            sys.exit(f"warm start needs a model in {src}")
        init = (torch.load(src / "model.pt", map_location="cpu"), src_meta["classes"])
        icar_share = 0.75  # the ICAR field photos anchor the classes both sources share
    print("fine-tune — EfficientNetV2-S, ICAR + extra sources, background randomisation"
          f"{', warm start' if init else ''}:")
    net, f1, hist = finetune("efficientnet_v2_s", train, val, class_idx, device, args.quick, args.epochs,
                             backgrounds=bgs["train"], val_backgrounds=bgs["val"], epoch_size=epoch_size or None,
                             init=init, icar_share=icar_share, freeze_all=args.freeze_backbone,
                             lr_override=(args.lr_feat, args.lr_head) if args.lr_feat else None)

    dl_va = loader(val, class_idx, test_transform(IMG), shuffle=False, backgrounds=bgs["val"], deterministic=True)
    lv, yv = logits_of(net, dl_va, device)
    T = fit_temperature(lv, yv)

    def evaluate(rows, backgrounds=None):
        dl = loader(rows, class_idx, test_transform(IMG), shuffle=False, backgrounds=backgrounds, deterministic=True)
        lt, yt = logits_of(net, dl, device)
        return torch.softmax(lt, 1).numpy(), torch.softmax(lt / T, 1).numpy(), yt.numpy()

    p_raw, p_cal, y = evaluate(i_te)
    pred = p_cal.argmax(1)
    icar_test = {**{k: round(v, 4) for k, v in scores(y, pred).items()},
                 "ece_before": round(ece(p_raw, y), 4), "ece_after": round(ece(p_cal, y), 4)}
    gate = gate_simulation(p_cal, i_te, classes, class_to_target, model_targets)

    _, pe_cal, ye = evaluate(e_te)
    plain_te = [r for r in e_te if r["bg"] == "plain"]
    _, ps_cal, ys = evaluate(plain_te, bgs["test"])
    _, po_cal, yo = evaluate(plain_te)
    extra = {
        "original_background": {"accuracy": round(float((pe_cal.argmax(1) == ye).mean()), 4),
                                "per_class": per_class_recall(ye, pe_cal.argmax(1), classes)},
        "plain_rows_original": {"accuracy": round(float((po_cal.argmax(1) == yo).mean()), 4),
                                "per_class": per_class_recall(yo, po_cal.argmax(1), classes)},
        "plain_rows_swapped": {"accuracy": round(float((ps_cal.argmax(1) == ys).mean()), 4),
                               "per_class": per_class_recall(ys, ps_cal.argmax(1), classes)},
        "gate_original": gate_simulation(pe_cal, e_te, classes, class_to_target, model_targets),
        "gate_swapped": gate_simulation(ps_cal, plain_te, classes, class_to_target, model_targets),
    }
    new_classes = [c for c in classes if prev_meta and c not in prev_meta["classes"]]

    # Deploy only if the ICAR field test does not get worse and the new classes
    # survive the background swap (i.e. the model learnt the leaf, not the backdrop).
    checks = []
    if prev_meta:
        pa, pg = prev_meta["test"]["accuracy"], prev_meta["gate_on_test"]["accuracy_when_advised"] or 0
        checks.append(("ICAR test top-1 within 2 points of deployed", icar_test["accuracy"] >= pa - 0.02,
                       f"{icar_test['accuracy']:.3f} vs {pa:.3f}"))
        checks.append(("ICAR accuracy-when-advised within 1 point of deployed",
                       (gate["accuracy_when_advised"] or 0) >= pg - 0.01,
                       f"{gate['accuracy_when_advised']} vs {pg}"))
    MIN_SWAP_ROWS = 10
    for c in new_classes:
        swapped = extra["plain_rows_swapped"]["per_class"].get(c, {})
        if swapped.get("n", 0) >= MIN_SWAP_ROWS:  # enough lab-backdrop photos to swap the backdrop
            r = swapped.get("recall", 0)
            checks.append((f"{c} recall after background swap >= 0.70", r >= 0.70, f"{r:.3f}"))
        else:  # a class learnt from field photos: judge it on its own held-out photos
            r = extra["original_background"]["per_class"].get(c, {}).get("recall", 0)
            checks.append((f"{c} recall on held-out photos >= 0.70", r >= 0.70, f"{r:.3f}"))
    deploy = not args.quick and all(ok for _, ok, _ in checks)

    version = (f"icar+extra{'+more' if getattr(args, 'with_more', False) else ''}-"
               f"efficientnet_v2_s-{'warmstart' if init else 'finetune'}-"
               f"{datetime.now(UTC):%Y%m%d}")
    meta = {
        "model_version": version, "backbone": "efficientnet_v2_s", "head": "finetune", "img_size": IMG,
        "classes": classes, "class_to_target": class_to_target, "model_targets": model_targets,
        "temperature": round(T, 4), "trained_at": datetime.now(UTC).isoformat(),
        "dataset": ("ICAR rice & maize images (835 unique) + Crop Diseases compilation (rice blast, brown spot, "
                    "healthy; PlantVillage maize rust, northern leaf blight, healthy) + CCMT field maize "
                    "(fall armyworm, healthy); lab-backdrop photos trained with background randomisation"),
        "split": {"train": len(train), "val": len(val), "test": len(i_te), "extra_test": len(e_te),
                  "seed": SEED, "stratified": True, "icar_split": "same as previous deployed model"},
        "test": icar_test, "gate_on_test": gate, "extra_test": extra,
        "deploy_checks": [{"check": n, "passed": ok, "value": v} for n, ok, v in checks],
        "deployed": deploy,
        "benchmark": (prev_meta or {}).get("benchmark", []),
        "benchmark_note": "ICAR-only benchmark from the previous run (frozen backbones + ANN vs fine-tune)",
        "previous": ({"model_version": prev_meta["model_version"], "test": prev_meta["test"],
                      "gate_on_test": prev_meta["gate_on_test"]} if prev_meta else None),
        "history": hist, "quick": args.quick,
    }
    split_out = {"train": [r["path"] for r in i_tr], "val": [r["path"] for r in i_va],
                 "test": [r["path"] for r in i_te], "extra_train": [r["path"] for r in e_tr],
                 "extra_val": [r["path"] for r in e_va], "extra_test": [r["path"] for r in e_te]}
    torch.save({k: v.detach().cpu() for k, v in net.state_dict().items()}, cand_dir / "model.pt")
    (cand_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    (cand_dir / "split.json").write_text(json.dumps(split_out, indent=0))

    rep_name = "MODEL_REPORT.md" if deploy else "CANDIDATE_REPORT.md"
    cm_name = "confusion_matrix.png" if deploy else "candidate_confusion.png"
    cam_name = "gradcam_samples.png" if deploy else "candidate_gradcam.png"
    all_te_rows = i_te + e_te
    _, pall, yall = evaluate(all_te_rows)
    plot_confusion(yall, pall.argmax(1), classes, REP / cm_name)
    rng = random.Random(SEED)
    cam_rows = rng.sample(i_te, 6) + rng.sample([r for r in e_te if r["train_class"] in new_classes] or e_te, 6)
    plot_gradcam(net, cam_rows, classes, torch.device("cpu"), REP / cam_name)

    if deploy:
        import shutil  # noqa: PLC0415
        for f in ("model.pt", "meta.json", "split.json"):
            shutil.copy(cand_dir / f, ART / f)

    def pc_table(block):
        return [f"| {c} | {v['n']} | {v['recall']:.2f} |" for c, v in sorted(block["per_class"].items())]

    prev = meta["previous"]
    lines = [
        "# AnnRakshak vision model — report" + ("" if deploy else " (CANDIDATE — not deployed)"),
        "",
        f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `ml/train.py --with-extra`. Version `{version}`.",
        "",
        f"**Data:** {meta['dataset']}. {len(classes)} training classes → {len(model_targets)} targets "
        f"(rice leaf and neck blast, fall armyworm larvae and damage, are separate classes merged into one advisory "
        f"target). The ICAR train/validation/test split is the one the previous model used, so the ICAR test numbers "
        f"below compare like for like. Extra sources are split per class (70/15/15, seed {SEED}) and capped "
        f"(new classes ≤{EXTRA_CAP_NEW['train']} train images, classes ICAR already has ≤{EXTRA_CAP_EXISTING['train']}); "
        f"training samples classes evenly and, inside a class, gives the ICAR field photos {icar_share:.0%} of the weight."
        + (" **Warm start:** training continues from the deployed model — its backbone and its head rows for every "
           "class it already knew — at a third of the usual learning rate, so only the new classes are learnt from "
           "scratch (continual learning)." if init else ""),
        "",
        "**Why background randomisation:** the extra rice photos are single leaves on white paper and the maize ones "
        "are PlantVillage leaves on black/grey — each class with its own backdrop. A network learns the backdrop. "
        f"So {int(COMPOSITE_P * 100)}% of the time in training (and always in validation) the leaf is cut out and "
        "pasted on a healthy ICAR field photo of the same crop (`ml/composite.py`). The background-swap test below "
        "pastes held-out test leaves on held-out field backgrounds: if the model had learnt backdrops, it would fail there.",
        "",
        "## 1. ICAR field test set (same 126 images as the previous model)",
        "",
        "| | Top-1 accuracy | Macro-F1 | Advised | Accuracy when advised | Calibration error |",
        "|---|---|---|---|---|---|",
        (f"| previous ({prev['model_version']}) | {prev['test']['accuracy']:.3f} | {prev['test']['f1']:.3f} | "
         f"{prev['gate_on_test']['advise_pct']}% | {prev['gate_on_test']['accuracy_when_advised']} | "
         f"{prev['test'].get('ece_after')} |") if prev else "",
        f"| **this model** | {icar_test['accuracy']:.3f} | {icar_test['f1']:.3f} | {gate['advise_pct']}% | "
        f"{gate['accuracy_when_advised']} | {icar_test['ece_after']} |",
        "",
        "## 2. Extra-source test images",
        "",
        f"- Original backgrounds: accuracy **{extra['original_background']['accuracy']:.3f}** "
        f"({len(e_te)} images); gate advises {extra['gate_original']['advise_pct']}%, right "
        f"{extra['gate_original']['accuracy_when_advised']} of the time.",
        f"- Plain-backdrop images only: {extra['plain_rows_original']['accuracy']:.3f} on the original backdrop → "
        f"**{extra['plain_rows_swapped']['accuracy']:.3f}** with the backdrop swapped for an unseen field photo "
        f"(gate right {extra['gate_swapped']['accuracy_when_advised']} of the time when it advises).",
        "",
        "Per-class recall, background swapped:",
        "",
        "| Class | Test images | Recall |",
        "|---|---|---|",
        *pc_table(extra["plain_rows_swapped"]),
        "",
        "## 3. Deployment checks",
        "",
        *[f"- {'✅' if ok else '❌'} {n}: {v}" for n, ok, v in checks],
        "",
        f"**{'Deployed' if deploy else 'Not deployed — the previous model stays live.'}**",
        "",
        f"![confusion matrix]({cm_name})",
        "",
        f"![Grad-CAM samples]({cam_name})",
        "",
        "## Read this before quoting the numbers",
        "",
        "- The extra rice and maize photos are lab-style; field photos from farmers' phones will differ more than "
        "the swap test can show. Blast and rust are new photo classes: expert confirmations on the officials' "
        "dashboard are the field test that counts.",
        "- The ICAR test is ~8 images per class; one image is ~12 points of per-class recall.",
        "- The Crop Diseases download lost 1,695 relevant images to a damaged download (data/raw/crop_diseases/"
        "archive_LOST.txt); a clean re-download would add them.",
    ]
    (REP / rep_name).write_text("\n".join(x for x in lines if x is not None) + "\n")
    print(f"{'DEPLOYED' if deploy else 'candidate only'}: {version}  ICAR acc {icar_test['accuracy']:.3f}  "
          f"gate {gate}  swap acc {extra['plain_rows_swapped']['accuracy']:.3f}  checks {checks}")


if __name__ == "__main__":
    main()
