"""Image classification behind one function: classify(image_bytes, farm_crop).

Real model: when ml/artifacts/ holds a trained checkpoint (produced by
ml/train.py on the ICAR rice & maize dataset), predictions are calibrated
softmax outputs with a Grad-CAM heatmap.

Stub model: until then, a deterministic stand-in returns one of three canned
scenarios (clear / torn between two / unsure) so every gate band can be shown.
It ALWAYS sets is_stub=True and the app must show a banner — a stub that looks
like a real diagnosis is worse than no feature.

The vegetation check is real in both modes: a softmax with no reject class puts
its mass somewhere even for a photo of a shoe, so a photo with almost no plant-
coloured pixels is declared out of scope before any label is trusted.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.config import BACKEND_DIR, CLEARLY_VEGETATION, MIN_VEGETATION_FRACTION
from app.engine.gate import Prediction, TopK

ARTIFACTS = BACKEND_DIR.parent / "ml" / "artifacts"

STUB_SCENARIOS = {
    # Labels are ICAR training classes, so the stub never names something the
    # real model could not.
    "rice": {
        "clear": [("rice_bacterial_leaf_blight", 0.87), ("rice_brown_spot", 0.07), ("rice_sheath_blight", 0.03)],
        "torn": [("rice_brown_spot", 0.51), ("rice_bacterial_leaf_blight", 0.40), ("rice_sheath_blight", 0.05)],
        "unsure": [("rice_sheath_blight", 0.34), ("rice_brown_spot", 0.27), ("rice_false_smut", 0.21)],
    },
    "maize": {
        "clear": [("maize_fall_armyworm", 0.88), ("maize_aphid", 0.06), ("maize_healthy", 0.03)],
        "torn": [("maize_turcicum_leaf_blight", 0.50), ("maize_maydis_leaf_blight", 0.42), ("maize_curvularia_leaf_spot", 0.05)],
        "unsure": [("maize_curvularia_leaf_spot", 0.31), ("maize_turcicum_leaf_blight", 0.28), ("maize_downy_mildew", 0.20)],
    },
}
SCENARIO_ORDER = ("clear", "torn", "unsure")


class UnreadableImage(ValueError):
    pass


# A photograph of a leaf is a few megapixels; a 48 MP phone sensor is 48. Past
# that it is not a farmer's camera, and the arithmetic matters: a decoded pixel
# costs three bytes of RAM whatever the file cost to send, so a 200 KB PNG can
# ask for a gigabyte. PIL only warns at its own limit and errors at twice it,
# so the size is read from the header — Image.open parses it without decoding —
# and the picture is refused before a single row is expanded.
MAX_PIXELS = 60_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # PIL's own backstop, for any other caller


def open_image(image_bytes: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise UnreadableImage(f"image too large to decode: {w}x{h}")
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")
    except UnreadableImage:
        raise
    except Exception as exc:  # PIL raises a zoo of types on bad input
        raise UnreadableImage("not a readable image") from exc


def vegetation_fraction(img: Image.Image) -> float:
    """Share of pixels whose hue is in the green-yellow band with enough
    saturation and brightness to be plant tissue. Lesions are brown, but a
    leaf photo still keeps plenty of green around them."""
    small = img.copy()
    small.thumbnail((160, 160))
    hsv = np.asarray(small.convert("HSV"), dtype=np.int16)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # PIL hue is 0-255 over 360°: 26..130 ≈ 37°..184° (straw-yellow to teal).
    # Starting at 37° rather than 28° keeps wood and cardboard (≈30°) out.
    plant = (h >= 26) & (h <= 130) & (s >= 40) & (v >= 40)
    return float(plant.mean())


@lru_cache
def _real_model():
    """Load the trained checkpoint if present. Returns None when absent, or when
    ANNRAKSHAK_VISION=stub (tests need the deterministic scenarios)."""
    if os.environ.get("ANNRAKSHAK_VISION") == "stub":
        return None
    meta_path = ARTIFACTS / "meta.json"
    if not (meta_path.exists() and (ARTIFACTS / "model.pt").exists()):
        return None
    meta = json.loads(meta_path.read_text())
    if meta.get("quick"):
        return None  # a smoke-run checkpoint is not a model; stay on the labelled stub
    try:
        from app.engine.model import Classifier  # noqa: PLC0415  needs torch
    except ImportError:
        return None
    return Classifier(Path(ARTIFACTS), meta)


CLOSER_LOOK_SCALES = ((0.5, 3), (0.7, 2))
"""(side as a share of the photo's short side, positions along each axis): a
3x3 grid of half-size squares and a 2x2 grid of larger ones, 13 views."""


def _views(img: Image.Image) -> list[tuple[float, float, float, float]]:
    """Square parts of the photo, as (x0, y0, x1, y1) in pixels."""
    w, h = img.size
    boxes = []
    for share, n in CLOSER_LOOK_SCALES:
        side = share * min(w, h)
        xs = [i * (w - side) / (n - 1) for i in range(n)]
        ys = [i * (h - side) / (n - 1) for i in range(n)]
        boxes += [(x, y, x + side, y + side) for y in ys for x in xs]
    return boxes


def _in_frame(box, size: tuple[int, int]) -> list[float] | None:
    """A part of the photo as fractions of the frame the farmer sees: the
    photo's central square, the same square the model reads. None when the
    part lies outside it."""
    w, h = size
    s = min(w, h)
    ox, oy = (w - s) / 2, (h - s) / 2
    x0, y0, x1, y1 = box
    f = [max(0.0, (x0 - ox) / s), max(0.0, (y0 - oy) / s), min(1.0, (x1 - ox) / s), min(1.0, (y1 - oy) / s)]
    if f[2] - f[0] < 0.1 or f[3] - f[1] < 0.1:
        return None
    return [round(v, 3) for v in f]


def closer_region(model, img: Image.Image) -> list[float] | None:
    """Where a close-up would help, in a plant photo the model found unfamiliar
    as a whole.

    A wide shot of a field is unlike the close-ups the model learnt from, even
    when the problem is plainly in it: an early false smut panicle, a few orange
    balls in a green canopy. The photo is cut into parts and the part most like
    the training photos is marked, so the farmer can photograph that part up
    close. It is not used to answer. Read from a part, held-out photos the
    model found unfamiliar were advised correctly 10 times in 29, and 158 of
    600 photos of other plants (beans, weeds, PlantVillage's other crops) went
    on to advice (2026-11-18, data/fetch_ood.py) — a close-up the farmer takes
    goes through every check from the start instead."""
    boxes = _views(img)
    surveyed = model.survey([img.crop(tuple(round(v) for v in b)) for b in boxes])
    order = sorted(range(len(boxes)), key=lambda i: surveyed[i][1] if surveyed[i][1] is not None else -1, reverse=True)
    for i in order:
        if not model.is_familiar(surveyed[i][1]):
            return None
        region = _in_frame(boxes[i], img.size)
        if region is not None:
            return region
    return None


def model_status() -> dict:
    m = _real_model()
    return {"is_stub": m is None, "model_version": m.version if m else "stub-0"}


def classify(image_bytes: bytes, farm_crop: str, scenario: str | None = None) -> TopK:
    img = open_image(image_bytes)
    veg = vegetation_fraction(img)

    model = _real_model()
    if model is not None:
        preds, heatmap, fam = model.analyse(img)
        topk = TopK([Prediction(t, c) for t, c in preds], model.version, is_stub=False, heatmap=heatmap)
        if not model.is_familiar(fam):
            # Two very different photos score low here, and they need different
            # answers. A face, a room, a document is not a crop photo and the
            # farmer should take another. A photo that is mostly plant is a crop
            # photo unlike the ones the model was trained on — a wide phone shot
            # of a chewed whorl, say — and sending that farmer back to retake it
            # is wrong, so an expert looks at it instead. The heatmap is kept in
            # that case because the expert can use it.
            if veg < CLEARLY_VEGETATION:
                return TopK(topk.predictions, topk.model_version, False,
                            out_of_scope=True, oos_reason="NOT_A_CROP_PHOTO", heatmap=None)
            region = closer_region(model, img)
            if region is not None and heatmap is not None:
                heatmap = {**heatmap, "closer_region": region}
            return TopK(topk.predictions, topk.model_version, False,
                        out_of_scope=True, oos_reason="UNFAMILIAR_PHOTO", heatmap=heatmap)
    else:
        crop = farm_crop if farm_crop in STUB_SCENARIOS else "rice"
        if scenario not in SCENARIO_ORDER:
            digest = hashlib.sha256(image_bytes).digest()
            scenario = SCENARIO_ORDER[digest[0] % len(SCENARIO_ORDER)]
        preds = [Prediction(t, c) for t, c in STUB_SCENARIOS[crop][scenario]]
        topk = TopK(preds, "stub-0", is_stub=True)

    if veg < MIN_VEGETATION_FRACTION:
        return TopK(
            topk.predictions, topk.model_version, topk.is_stub,
            out_of_scope=True, oos_reason="NOT_A_CROP_PHOTO", heatmap=None,
        )
    return topk
