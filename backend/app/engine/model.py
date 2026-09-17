"""Model architecture, preprocessing, inference and Grad-CAM — shared by
ml/train.py and the API so training and serving cannot drift apart.

Two families, following the two reference papers:
  * "finetune": an ImageNet backbone fine-tuned end to end (Haider et al.,
    VTSE 2024, EfficientNetV2 transfer learning).
  * "ann":      a frozen ImageNet backbone feeding a 1024-512-256-128 ANN
    head (Singh et al., IJCISIM 2026, DenseNet201 features + ANN).
Both are one nn.Module (features -> pool -> head), so Grad-CAM works the same
way on either.

Only imported when trained artifacts exist; the API keeps running on the stub
when torch or the artifacts are absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import models, transforms

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)

BACKBONES = {
    # name: (constructor, weights enum, feature dim)
    "efficientnet_v2_s": (models.efficientnet_v2_s, models.EfficientNet_V2_S_Weights.IMAGENET1K_V1, 1280),
    "densenet201": (models.densenet201, models.DenseNet201_Weights.IMAGENET1K_V1, 1920),
    "mobilenet_v3_large": (models.mobilenet_v3_large, models.MobileNet_V3_Large_Weights.IMAGENET1K_V2, 960),
}


class Net(nn.Module):
    def __init__(self, backbone: str, n_classes: int, head: str, pretrained: bool = True):
        super().__init__()
        ctor, weights, dim = BACKBONES[backbone]
        base = ctor(weights=weights if pretrained else None)
        self.features = base.features
        self.needs_relu = backbone == "densenet201"  # torchvision applies it in forward()
        if head == "ann":
            self.head = nn.Sequential(
                nn.Linear(dim, 1024), nn.ReLU(), nn.Dropout(0.4),
                nn.Linear(1024, 512), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
                nn.Linear(256, 128), nn.ReLU(),
                nn.Linear(128, n_classes),
            )
        else:
            self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(dim, n_classes))

    def feature_map(self, x: torch.Tensor) -> torch.Tensor:
        f = self.features(x)
        return F.relu(f) if self.needs_relu else f

    def pooled(self, x: torch.Tensor) -> torch.Tensor:
        return torch.flatten(F.adaptive_avg_pool2d(self.feature_map(x), 1), 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.pooled(x))


def test_transform(size: int):
    return transforms.Compose([
        transforms.Resize(int(size * 1.14)),
        transforms.CenterCrop(size),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])


def train_transform(size: int):
    return transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.45, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomApply([transforms.RandomRotation(90)], p=0.5),
        transforms.ColorJitter(0.3, 0.3, 0.3, 0.03),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])


def best_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _normalise(cam: torch.Tensor) -> np.ndarray:
    """A heatmap scaled to [0, 1]. Dividing by (max + eps) instead would make
    the result depend on the map's absolute scale, and the two ways of
    computing the same map differ by a constant factor."""
    cam = (cam - cam.min()).detach().cpu()
    top = float(cam.max())
    return (cam / top).numpy() if top > 0 else cam.numpy()


def linear_head_weights(model: Net) -> torch.Tensor | None:
    """The class-by-feature weight matrix, when the head is one Linear layer on
    the pooled features (the "finetune" head). None for the deep "ann" head."""
    linear = [m for m in model.head if isinstance(m, nn.Linear)]
    return linear[0].weight if len(linear) == 1 else None


def cam_from_map(model: Net, fmap: torch.Tensor, class_idx: int) -> np.ndarray | None:
    """Grad-CAM without the backward pass.

    Grad-CAM weights each feature channel by the mean gradient of the class
    logit with respect to it. When the head is a single Linear layer on global
    average pooling, that gradient is a constant: d logit_c / d fmap[k] is
    W[c, k] / (H*W) everywhere. So the gradient-weighted sum is just the class's
    own weight row — the identical map, up to the scale that normalising
    removes. The backward pass was 93% of the time a scan took (2845 ms of
    3116 ms), and it was recomputing the forward pass to get there.

    Returns None when the head is not linear, and the caller falls back.
    """
    w = linear_head_weights(model)
    if w is None:
        return None
    return _normalise(F.relu((w[class_idx].view(-1, 1, 1) * fmap[0]).sum(0)))


def gradcam(model: Net, x: torch.Tensor, class_idx: int) -> np.ndarray:
    """Grad-CAM on the last feature map: which regions pushed the score for
    `class_idx` up. Returns an HxW array in [0, 1]."""
    model.zero_grad(set_to_none=True)
    fmap = model.feature_map(x)
    fmap.retain_grad()
    logits = model.head(torch.flatten(F.adaptive_avg_pool2d(fmap, 1), 1))
    logits[0, class_idx].backward()
    weights = fmap.grad.mean(dim=(2, 3), keepdim=True)
    return _normalise(F.relu((weights * fmap).sum(dim=1))[0])


class Classifier:
    """Loads ml/artifacts/{model.pt,meta.json}. predict() returns top-3 KB
    targets with calibrated confidences plus a Grad-CAM grid."""

    def __init__(self, artifacts: Path, meta: dict | None = None):
        meta = meta or json.loads((artifacts / "meta.json").read_text())
        self.meta = meta
        self.version = meta["model_version"]
        self.classes: list[str] = meta["classes"]
        self.class_to_target: dict[str, str] = meta["class_to_target"]
        self.temperature: float = meta.get("temperature", 1.0)
        self.size: int = meta["img_size"]
        self.model = Net(meta["backbone"], len(self.classes), meta["head"], pretrained=False)
        state = torch.load(artifacts / "model.pt", map_location="cpu", weights_only=True)
        self.model.load_state_dict(state)
        self.model.train(False)  # inference mode: dropout off, batch-norm frozen
        self.tf = test_transform(self.size)
        # Familiarity: how close a photo's features are to the training photos'.
        # A softmax always picks a class, even for a face; this says whether the
        # photo is the kind of thing the model knows at all (ml/build_familiarity.py).
        self.bank = None
        self.familiar_min = None
        bank, cfg = artifacts / "familiarity_bank.npy", artifacts / "familiarity.json"
        if bank.exists() and cfg.exists():
            conf = json.loads(cfg.read_text())
            if conf.get("model_version") == self.version:  # a bank from another model means nothing
                self.bank = torch.from_numpy(np.load(bank).astype(np.float32))
                self.familiar_min = float(conf["threshold"])
                self.familiar_k = int(conf.get("k", 5))

    def embed(self, img: Image.Image) -> torch.Tensor:
        x = self.tf(img.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            return F.normalize(self.model.pooled(x), dim=1)[0]

    def familiarity(self, feat: torch.Tensor) -> float | None:
        """Mean cosine similarity to the k nearest training photos (None if no bank)."""
        if self.bank is None:
            return None
        sims = self.bank @ F.normalize(feat, dim=0)
        return float(sims.topk(min(self.familiar_k, len(sims))).values.mean())

    def is_familiar(self, fam: float | None) -> bool:
        return fam is None or self.familiar_min is None or fam >= self.familiar_min

    def predict(self, img: Image.Image, k: int = 3, with_heatmap: bool = True) -> tuple[list[tuple[str, float]], dict | None]:
        preds, heatmap, _ = self.analyse(img, k, with_heatmap)
        return preds, heatmap

    def analyse(self, img: Image.Image, k: int = 3, with_heatmap: bool = True):
        """(top-k targets, Grad-CAM grid or None, familiarity or None) from one forward pass."""
        x = self.tf(img.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            fmap = self.model.feature_map(x)
            feat = torch.flatten(F.adaptive_avg_pool2d(fmap, 1), 1)
            logits = self.model.head(feat)[0]
        fam = self.familiarity(feat[0])
        probs = torch.softmax(logits / self.temperature, dim=0).numpy()
        by_target: dict[str, float] = {}
        for cls, p in zip(self.classes, probs):
            t = self.class_to_target[cls]
            by_target[t] = by_target.get(t, 0.0) + float(p)
        ranked = sorted(by_target.items(), key=lambda kv: kv[1], reverse=True)[:k]
        top_class = int(np.argmax(probs))
        if not with_heatmap:  # live frames: the heatmap is never shown
            return [(t, round(c, 4)) for t, c in ranked], None, fam
        cam = cam_from_map(self.model, fmap, top_class)
        if cam is None:  # the deep "ann" head has no closed form
            with torch.enable_grad():
                cam = gradcam(self.model, x.requires_grad_(True), top_class)
        return [(t, round(c, 4)) for t, c in ranked], {
            "grid": np.round(cam, 3).tolist(),
            "rows": cam.shape[0],
            "cols": cam.shape[1],
            "method": "grad-cam",
            "class": self.classes[top_class],
        }, fam
