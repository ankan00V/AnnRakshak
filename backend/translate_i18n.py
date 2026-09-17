"""Build the machine-translated languages (Bengali, Tamil, Telugu, Kannada,
Malayalam, Gujarati, Punjabi, Odia) from the approved English.

    ../.venv/bin/python translate_i18n.py --count            # what would be sent, nothing sent
    ../.venv/bin/python translate_i18n.py --lang ta,bn       # translate what is missing
    ../.venv/bin/python translate_i18n.py                    # all eight

Two outputs per language, both committed and reviewable:
  backend/kb/i18n/<lang>.json              English source -> translation (KB + backend messages)
  frontend/landing/src/locales/<lang>.json UI key -> translation

Only missing strings are sent, so a re-run after a KB edit costs only the new
text. Placeholders ({crop}, {mm} ...) are protected and checked; a string whose
placeholders don't survive is left out (it shows in English). Pesticide verdicts
(app.engine.labelcheck) are never machine translated.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from app.config import KB_DIR, SARVAM_TRANSLATE_MODEL
from app.i18n import MACHINE, MEMORY_DIR, protect, restore, tidy, translate_many

INDICTRANS2 = "ai4bharat/indictrans2-en-indic-dist-200M"
IT2_CODES = {"bn": "ben_Beng", "ta": "tam_Taml", "te": "tel_Telu", "kn": "kan_Knda", "ml": "mal_Mlym",
             "gu": "guj_Gujr", "pa": "pan_Guru", "od": "ory_Orya"}


class IndicTrans2:
    """AI4Bharat's open English->Indic model (MIT), run locally: no per-string cost.
    Needs HF_TOKEN in .env and the model's terms accepted on huggingface.co."""

    def __init__(self) -> None:
        import os  # noqa: PLC0415

        import torch  # noqa: PLC0415
        from IndicTransToolkit.processor import IndicProcessor  # noqa: PLC0415
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa: PLC0415

        token = os.environ.get("HF_TOKEN")
        self.torch = torch
        self.device = os.environ.get("IT2_DEVICE") or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(INDICTRANS2, trust_remote_code=True, token=token)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(INDICTRANS2, trust_remote_code=True, token=token)
        self.model = self.model.to(self.device).eval()
        self.ip = IndicProcessor(inference=True)

    def translate(self, strings: list[str], lang: str, batch: int = 8, progress=None, save=None,
                  beams: int = 4) -> dict[str, str]:
        tgt = IT2_CODES[lang]
        done: dict[str, str] = {}
        order = sorted(strings, key=len)  # similar lengths per batch: less padding
        for i in range(0, len(order), batch):
            chunk = order[i:i + batch]
            safe = [protect(x) for x in chunk]
            pre = self.ip.preprocess_batch([t for t, _ in safe], src_lang="eng_Latn", tgt_lang=tgt)
            x = self.tok(pre, truncation=True, padding="longest", return_tensors="pt",
                         return_attention_mask=True).to(self.device)
            with self.torch.no_grad():
                # use_cache=False: the model's remote code predates transformers' new cache objects
                out = self.model.generate(**x, use_cache=False, min_length=0, max_length=384, num_beams=beams)
            dec = self.tok.batch_decode(out.detach().cpu().tolist(), skip_special_tokens=True,
                                        clean_up_tokenization_spaces=True)
            for src, (_, names), text in zip(chunk, safe, self.ip.postprocess_batch(dec, lang=tgt)):
                if not re.search(r"[A-Za-z]", src):
                    done[src] = src
                    continue
                text = tidy(src, text)
                text = restore(text, names) if names else text
                if text:
                    done[src] = text
            if progress:
                progress(min(i + batch, len(order)), len(order))
            if save and (i // batch) % 10 == 9:
                save(done)  # a crash loses at most ten batches
            if self.device == "mps":
                self.torch.mps.empty_cache()
        return done

ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / "frontend" / "landing" / "src" / "lib" / "i18n.ts"
UI_OUT = ROOT / "frontend" / "landing" / "src" / "locales"
KB_FILES = ["crops.json", "targets.json", "advisories.json", "cues.json", "risk_rules.json",
            "agromet.json", "icar_technologies.json", "krishi.json"]
MODULES = ["app.services", "app.notify", "app.mailer", "app.live", "app.engine.advisory", "app.engine.risk",
           "app.engine.fieldnow", "app.engine.livescan", "app.routers.weather", "app.auth", "app.routers.auth",
           "app.krishi", "app.live"]
NOTE = ("Machine translated from the approved English (engines under 'models'); placeholders checked. "
        "Pending review by a native speaker — correct any line in place, the job never overwrites an existing entry.")


def _walk(o, out: set[str]) -> None:
    if isinstance(o, dict):
        if "en" in o and ("hi" in o or "mr" in o):
            en = o["en"]
            if isinstance(en, str):
                out.add(en.strip())
            elif isinstance(en, list):
                out.update(x.strip() for x in en if isinstance(x, str))
        for k, v in o.items():
            if not str(k).startswith("_"):
                _walk(v, out)
    elif isinstance(o, (list, tuple)):
        for v in o:
            _walk(v, out)


def backend_strings() -> list[str]:
    out: set[str] = set()
    for f in KB_FILES:
        _walk(json.loads((KB_DIR / f).read_text(encoding="utf-8")), out)
    for m in MODULES:
        mod = importlib.import_module(m)
        for name, val in vars(mod).items():
            if name.isupper():
                _walk(val, out)
    return sorted(s for s in out if s)


UI_LINE = re.compile(r"""^\s{2}(['"]?)([\w+.\-]+)\1:\s*(['"])((?:\\.|(?!\3).)*)\3,?\s*$""")


def ui_strings() -> dict[str, str]:
    src = UI_SOURCE.read_text(encoding="utf-8")
    start = src.index("const en = {")
    body = src[start:src.index("\n}\n", start)]
    out = {}
    for line in body.splitlines()[1:]:
        m = UI_LINE.match(line)
        if m:
            out[m.group(2)] = bytes(m.group(4), "utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8") \
                if "\\" in m.group(4) else m.group(4)
    return out


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(path: Path, text: str) -> None:
    """Write only on change: the frontend dev server reloads the page on every write."""
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def write(lang: str, kb_path: Path, ui_path: Path, kb: dict, ui: dict, engine) -> None:
    old = load(kb_path)
    models = set(old.get("models") or ([old["model"]] if old.get("model") else []))
    models.add(INDICTRANS2 if engine else SARVAM_TRANSLATE_MODEL)
    strings = dict(sorted(kb.items()))
    updated = old.get("updated") if old.get("strings") == strings else date.today().isoformat()
    out = {"_note": NOTE, "models": sorted(models), "source": "en", "updated": updated, "strings": strings}
    if old.get("reviewed"):  # lines a native speaker has corrected (review_translations.py)
        out["reviewed"] = old["reviewed"]
    _save(kb_path, json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    _save(ui_path, json.dumps(dict(sorted(ui.items())), ensure_ascii=False, indent=1) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default=",".join(MACHINE))
    ap.add_argument("--count", action="store_true", help="only count what would be sent")
    ap.add_argument("--beams", type=int, default=4,
                    help="indictrans2 beam search width; 2 is about twice as fast, slightly rougher")
    ap.add_argument("--engine", choices=("sarvam", "indictrans2"), default="sarvam",
                    help="sarvam: Sarvam-Translate API (paid credits); indictrans2: AI4Bharat model run locally")
    args = ap.parse_args()
    langs = [x for x in args.lang.split(",") if x]
    bad = [x for x in langs if x not in MACHINE]
    if bad:
        sys.exit(f"not a machine-translated language: {bad} (choose from {MACHINE})")

    engine = IndicTrans2() if args.engine == "indictrans2" and not args.count else None
    kb_src = backend_strings()
    ui_src = ui_strings()
    print(f"sources: {len(kb_src)} backend strings, {len(ui_src)} UI strings")
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    UI_OUT.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        kb_path, ui_path = MEMORY_DIR / f"{lang}.json", UI_OUT / f"{lang}.json"
        kb_have = load(kb_path).get("strings", {})
        ui_have = load(ui_path)
        kb_todo = [s for s in kb_src if s not in kb_have]
        ui_todo = {k: v for k, v in ui_src.items() if k not in ui_have}
        chars = sum(map(len, kb_todo)) + sum(map(len, ui_todo.values()))
        print(f"{lang}: {len(kb_todo)} backend + {len(ui_todo)} UI strings to translate ({chars} chars)")
        if args.count or (not kb_todo and not ui_todo):
            continue
        t0 = time.time()
        texts = sorted(set(kb_todo) | set(ui_todo.values()))
        report = lambda i, n: print(f"  {lang}: {i}/{n}", flush=True)  # noqa: E731

        def save(partial: dict[str, str]) -> None:
            write(lang, kb_path, ui_path, kb_have | {s: partial[s] for s in kb_todo if s in partial},
                  ui_have | {k: partial[v] for k, v in ui_todo.items() if v in partial}, engine)

        done = engine.translate(texts, lang, progress=report, save=save, beams=args.beams) if engine \
            else translate_many(texts, lang, progress=report)
        kb_have.update({s: done[s] for s in kb_todo if s in done})
        ui_have.update({k: done[v] for k, v in ui_todo.items() if v in done})
        write(lang, kb_path, ui_path, kb_have, ui_have, engine)
        missing = len(texts) - len(done)
        print(f"  {lang}: {len(done)}/{len(texts)} translated in {time.time() - t0:.0f}s"
              f"{f'; {missing} left in English (failed or lost a placeholder)' if missing else ''}")


if __name__ == "__main__":
    main()
