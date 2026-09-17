"""One-off: give alerts issued before reasons were stored as parts ('_parts')
their parts, recovered from the English sentence, so they re-render in every
language (a translation that arrived after the alert was issued included).

    ../.venv/bin/python backfill_reasons.py            # dry run: counts only
    ../.venv/bin/python backfill_reasons.py --write

Alerts whose English doesn't match a known template are left as they are.
"""

from __future__ import annotations

import argparse
import re
from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.engine.risk import REASONS, reason_of
from app.kb import get_kb
from app.models import Alert, Farm

SUFFIXES = ("forecast", "sensor", "history")


def _pattern(key: str) -> re.Pattern:
    out, last = "", 0
    en = REASONS[key]["en"]
    for m in re.finditer(r"\{(\w+)\}", en):
        out += re.escape(en[last:m.start()]) + f"(?P<{m.group(1)}>.+?)"
        last = m.end()
    return re.compile("^" + out + re.escape(en[last:]))


PATTERNS = {k: _pattern(k) for k in ("weather", "phenology", "trap", "spread")}


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _iso(text: str, issued: date) -> str:
    """'09 Sep' in an alert issued on `issued` -> ISO date. A date more than ten
    days after the issue date belongs to the year before (a run across New Year)."""
    day, mon = text.split()
    d = date(issued.year, MONTHS.index(mon) + 1, int(day))
    if d > issued + timedelta(days=10):
        d = d.replace(year=issued.year - 1)
    return d.isoformat()


def parts_for(kb, alert: Alert, farm: Farm) -> list[dict] | None:
    en = (alert.reason or {}).get("en")
    if not en or alert.target not in kb.targets:
        return None
    rest, tail = en, []
    for key in reversed(SUFFIXES):  # history is appended last, forecast first
        s = REASONS[key]["en"]
        if rest.endswith(s):
            rest, tail = rest[: -len(s)], [{"key": key}, *tail]
    for key, pat in PATTERNS.items():
        m = pat.fullmatch(rest)
        if not m:
            continue
        args: dict = dict(m.groupdict())
        names = kb.targets[alert.target]["names"]
        if "name" in args:
            if args["name"] != names["en"]:
                return None
            args["name"] = names
        if "stage" in args:
            stage = next((s for s in kb.crops[farm.crop]["stages"] if s["names"]["en"] == args["stage"]), None)
            if stage is None:
                return None
            args["stage"] = stage["names"]
        if "crop" in args:
            crop = next((c for c in kb.crops.values() if c["names"]["en"] == args["crop"]), None)
            if crop is None:
                return None
            args["crop"] = crop["names"]
        for k in ("first", "last"):
            if k in args:
                args[k] = _iso(args[k], alert.issued_on)
        for k in ("rh", "tlo", "thi", "run", "das", "n"):
            if k in args:
                args[k] = int(args[k])
        for k in ("rate", "etl"):
            if k in args:
                args[k] = float(args[k]) if "." in args[k] else int(args[k])
        return [{"key": key, "args": args}, *tail]
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    write = ap.parse_args().write
    kb = get_kb()
    done = skipped = unmatched = 0
    with SessionLocal() as db:
        farms = {f.id: f for f in db.scalars(select(Farm)).all()}
        for a in db.scalars(select(Alert)).all():
            if (a.reason or {}).get("_parts"):
                skipped += 1
                continue
            parts = parts_for(kb, a, farms[a.farm_id])
            if parts is None:
                unmatched += 1
                continue
            new = reason_of(parts)
            if new["en"] != a.reason["en"]:  # the round trip must reproduce the English exactly
                unmatched += 1
                continue
            if write:
                a.reason = new
            done += 1
        if write:
            db.commit()
    print(f"{'updated' if write else 'would update'} {done}; already had parts {skipped}; left as they are {unmatched}")


if __name__ == "__main__":
    main()
