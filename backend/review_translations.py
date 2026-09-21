"""Hand the machine-translated languages to a native speaker, and take the
corrections back.

    ../.venv/bin/python review_translations.py --export ta          # -> reviews/ta.csv
    ../.venv/bin/python review_translations.py --import reviews/ta.csv
    ../.venv/bin/python review_translations.py --safety ta          # -> reviews/ta_safety.csv

--safety is for the lines where a wrong word can hurt someone: the spray check's
pesticide warnings. Those are never shown machine-translated — the app shows
the English until a native speaker approves a line (app.i18n.lookup_reviewed).
The sheet has the machine translation and a back-translation into English, so a
reviewer (or anyone) can see at a glance where the meaning drifted. Write the
corrected line in `correction`, or `ok` to approve the machine line as it is.

The CSV opens in any spreadsheet: `english`, `machine` (what the app shows
today) and an empty `correction` column. The reviewer fills in only the lines
that are wrong and sends the file back; importing writes those lines into
backend/kb/i18n/<lang>.json and frontend/landing/src/locales/<lang>.json and
marks them reviewed, so the translation job never touches them again.

A correction is refused (and reported) when it drops or renames a placeholder
such as {crop} or {dep:+.0f} — that would break the sentence, or the request
that formats it.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from app.i18n import MACHINE, MEMORY_DIR, NATIVE_NAMES, same_placeholders

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "frontend" / "landing" / "src" / "locales"
OUT = Path(__file__).resolve().parent / "reviews"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def export(lang: str) -> Path:
    from translate_i18n import ui_strings  # noqa: PLC0415  (imports the KB)

    kb = load(MEMORY_DIR / f"{lang}.json")
    ui, ui_src = load(UI_DIR / f"{lang}.json"), ui_strings()
    reviewed = set(kb.get("reviewed") or [])
    rows = [("kb", en, machine) for en, machine in sorted(kb.get("strings", {}).items())]
    rows += [(f"ui:{k}", ui_src[k], v) for k, v in sorted(ui.items()) if k in ui_src]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{lang}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel opens Indic scripts correctly
        w = csv.writer(f)
        w.writerow(["where", "english", "machine", "correction", "already_reviewed"])
        for where, en, machine in rows:
            w.writerow([where, en, machine, "", "yes" if en in reviewed else ""])
    print(f"{path}  {len(rows)} lines for a {NATIVE_NAMES[lang]} speaker "
          f"({len(reviewed)} already reviewed)")
    return path


def apply(csv_path: Path) -> None:
    lang = csv_path.stem.removesuffix("_safety")
    if lang not in MACHINE:
        sys.exit(f"{csv_path}: expected a file named <lang>.csv, one of {MACHINE}")
    kb_path, ui_path = MEMORY_DIR / f"{lang}.json", UI_DIR / f"{lang}.json"
    kb, ui = load(kb_path), load(ui_path)
    from translate_i18n import ui_strings  # noqa: PLC0415

    ui_src = ui_strings()
    reviewed = set(kb.get("reviewed") or [])
    changed = refused = 0
    with csv_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            fix = (row.get("correction") or "").strip()
            if not fix:
                continue
            english = row["english"]
            if fix.lower() == "ok":  # approved as it stands
                fix = (row.get("machine") or "").strip()
                if not fix:
                    continue
            if not same_placeholders(english, fix):
                print(f"  refused (placeholders changed): {english[:60]}…")
                refused += 1
                continue
            where = row["where"]
            if where == "kb":
                kb.setdefault("strings", {})[english] = fix
            elif where.startswith("ui:"):
                key = where[3:]
                if ui_src.get(key) != english:
                    print(f"  skipped (the English changed since the export): {key}")
                    continue
                ui[key] = fix
            reviewed.add(english)
            changed += 1
    kb["reviewed"] = sorted(reviewed)
    kb_path.write_text(json.dumps(kb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ui_path.write_text(json.dumps(dict(sorted(ui.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{lang}: {changed} corrections applied, {refused} refused, {len(reviewed)} lines reviewed in total")


SAFETY_UI = ("neverSafeNote",)
"""The spray check's standing note. Its headings are in labelcheck.TITLES."""


def safety_strings() -> list[str]:
    from app.engine.labelcheck import CLASS_WORDS, PROBLEM_KIND, TITLES, VERDICTS  # noqa: PLC0415

    return [d["en"] for group in (TITLES, VERDICTS, CLASS_WORDS, PROBLEM_KIND) for d in group.values()]


def export_safety(lang: str) -> Path:
    """Translate the pesticide warnings (kept out of the automatic job), back-
    translate every line, and write a sheet for a native speaker."""
    from app import voice  # noqa: PLC0415
    from app.i18n import machine_translate  # noqa: PLC0415
    from translate_i18n import ui_strings  # noqa: PLC0415

    kb_path = MEMORY_DIR / f"{lang}.json"
    kb, ui = load(kb_path), load(UI_DIR / f"{lang}.json")
    strings = kb.setdefault("strings", {})
    reviewed = set(kb.get("reviewed") or [])
    ui_src = ui_strings()
    rows = []
    for en in safety_strings():
        if en not in strings:
            got = machine_translate(en, lang)
            if got:
                strings[en] = got
        rows.append(("kb", en, strings.get(en, "")))
    kb_path.write_text(json.dumps(kb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rows += [(f"ui:{k}", ui_src[k], ui.get(k, "")) for k in SAFETY_UI if k in ui_src]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{lang}_safety.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["where", "english", "machine", "back_to_english", "correction", "already_reviewed"])
        for where, en, machine in rows:
            try:
                back = voice.translate(machine, lang, "en") if machine else ""
            except Exception:  # noqa: BLE001  the sheet is still useful without it
                back = ""
            w.writerow([where, en, machine, back, "", "yes" if en in reviewed else ""])
    print(f"{path}  {len(rows)} safety lines for a {NATIVE_NAMES[lang]} speaker")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", metavar="LANG", help=f"one of {', '.join(MACHINE)}")
    ap.add_argument("--import", dest="import_", metavar="CSV", help="a reviewed CSV to apply")
    ap.add_argument("--safety", metavar="LANG", help="the pesticide warnings, with back-translations")
    args = ap.parse_args()
    if args.safety:
        if args.safety not in MACHINE:
            sys.exit(f"{args.safety} is hand-authored or unknown; machine-translated: {', '.join(MACHINE)}")
        export_safety(args.safety)
    elif args.export:
        if args.export not in MACHINE:
            sys.exit(f"{args.export} is hand-authored or unknown; machine-translated: {', '.join(MACHINE)}")
        export(args.export)
    elif args.import_:
        apply(Path(args.import_))
    else:
        ap.error("give --export LANG or --import CSV")


if __name__ == "__main__":
    main()
