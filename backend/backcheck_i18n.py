"""Translate the shipped strings back to English and flag the ones that moved.

    ../.venv/bin/python backcheck_i18n.py bn,ta          # two languages
    ../.venv/bin/python backcheck_i18n.py bn --limit 200 # a sample
    ../.venv/bin/python backcheck_i18n.py ta --grep cob  # one subject

Every mistranslation found by hand was fluent, kept its placeholders and was
still wrong, so nothing that reads only the target text can catch them:

    "when the crop comes off"      -> when the crop falls over      (bn)
    "put on the muriate of potash" -> wear the muriate of potash    (6 of 7)
    "acts on nymphs"               -> acts on apsaras               (bn)
    "the ear husk rots"            -> the earlobe rots              (ta)
    "Come closer to the leaves"    -> come to the pages             (bn)
    "AnnRakshak only warns you"    -> the inspector only warns you  (bn)

Asking the translator to bring the sentence back can. The score is the share of
the source's meaning-bearing words that survive the round trip, near matches
allowed; low scores are where to look, not a verdict — word order and idiom
move the number on their own. Read the pairs.

Fix what it finds in the ENGLISH, not in the translation: the English is the
one source all ten languages come from, so an idiom there is wrong seven times.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from app.i18n import MACHINE, MEMORY_DIR, PLACEHOLDER

STOP = set("a an the and or of to in on for at is are be it its this that with from by as you your we our not do does "
           "no if when then than so there their them they he she his her i me my will would can could should may might "
           "about into over under after before while during each per".split())


def bag(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2}


def score(src: str, back: str) -> float:
    """How much of the source's meaning-bearing vocabulary came home."""
    want = bag(src)
    if not want:
        return 1.0
    got = bag(back)
    exact = len(want & got) / len(want)
    near = sum(1 for w in want - got if difflib.get_close_matches(w, got, n=1, cutoff=0.82)) / len(want)
    return round(min(1.0, exact + near), 3)


def check(lang: str, pairs: list[tuple[str, str]], workers: int = 6) -> list[tuple]:
    from app import voice  # noqa: PLC0415  (network; only when actually running)

    def one(pair):
        en, tr = pair
        try:
            back = voice.translate(PLACEHOLDER.sub("X", tr), lang, "en")
        except Exception as exc:  # noqa: BLE001  one failure must not stop the sweep
            return score(en, ""), lang, en, f"[{exc}]"
        return score(PLACEHOLDER.sub("X", en), back), lang, en, back

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, pairs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("langs", help=f"comma separated, from {','.join(MACHINE)}")
    ap.add_argument("--limit", type=int, default=0, help="check only the first N of each")
    ap.add_argument("--grep", default="", help="only strings whose English contains this")
    ap.add_argument("--show", type=int, default=30, help="how many of the worst to print")
    ap.add_argument("--out", default="", help="write every row to this JSON file")
    args = ap.parse_args()

    rows: list[tuple] = []
    for lang in args.langs.split(","):
        path = MEMORY_DIR / f"{lang}.json"
        if not path.exists():
            sys.exit(f"no translations for {lang}")
        strings = json.loads(path.read_text())["strings"]
        pairs = [(en, tr) for en, tr in strings.items()
                 if len(en) > 25 and re.search(r"[A-Za-z]", en)
                 and (not args.grep or args.grep.lower() in en.lower())]
        if args.limit:
            pairs = pairs[:args.limit]
        print(f"{lang}: {len(pairs)} strings", file=sys.stderr)
        rows += check(lang, pairs)

    rows.sort()
    if args.out:
        json.dump([{"score": s, "lang": l, "en": e, "back": b} for s, l, e, b in rows],
                  open(args.out, "w"), ensure_ascii=False, indent=1)
    print(f"\nworst {min(args.show, len(rows))} of {len(rows)}:")
    for s, lang, en, back in rows[:args.show]:
        print(f"\n  [{s}] {lang}\n    en  : {en[:110]}\n    back: {back[:110]}")


if __name__ == "__main__":
    main()
