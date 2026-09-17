"""All 785 Indian districts from the Government's Local Government Directory.

    .venv/bin/python data/lgd_pull.py     -> backend/kb/india_districts.json

data.gov.in resource 37231365-78ba-44d5-ac22-3deec40b9197 ("Local Government
Directory (LGD) - Districts"), the official state and district master. Names
are kept exactly as published, in English and in the state's own script, so a
farmer sees their district written the way the government writes it.

The OGD API answers only over IPv4 with a browser User-Agent from this
network, so the request forces both (see data/kcc_pull.py for the same dance).
"""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "kb" / "india_districts.json"
RESOURCE = "37231365-78ba-44d5-ac22-3deec40b9197"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"


def _clean(s: str | None) -> str:
    return " ".join((s or "").split())


def main() -> None:
    key = os.environ.get("DATA_GOV_IN_API_KEY") or next(
        (line.split("=", 1)[1].strip() for line in (ROOT / ".env").read_text().splitlines()
         if line.startswith("DATA_GOV_IN_API_KEY=")), "")
    if not key:
        sys.exit("DATA_GOV_IN_API_KEY is not set")
    transport = httpx.HTTPTransport(local_address="0.0.0.0")  # IPv4 only
    rows: list[dict] = []
    with httpx.Client(transport=transport, timeout=30, headers={"User-Agent": UA}) as c:
        offset, total = 0, None
        while total is None or offset < total:
            r = c.get(f"https://api.data.gov.in/resource/{RESOURCE}",
                      params={"api-key": key, "format": "json", "limit": 500, "offset": offset})
            r.raise_for_status()
            page = r.json()
            total = int(page["total"])
            rows += page["records"]
            offset += len(page["records"])
            print(f"  {offset}/{total}", flush=True)
            if not page["records"]:
                break
    by_state: dict[str, dict] = {}
    for r in rows:
        state = _clean(r["state_name_english"]).title() if _clean(r["state_name_english"]).isupper() \
            else _clean(r["state_name_english"])
        d = by_state.setdefault(state, {"code": r["state_code"], "districts": []})
        name = _clean(r["district_name_english"])
        local = _clean(r["district_name_local"])
        d["districts"].append({"name": name.title() if name.isupper() else name,
                               "local": local if local and local.upper() != name.upper() else None,
                               "code": r["district_code"]})
    for s in by_state.values():
        s["districts"].sort(key=lambda d: d["name"])
    out = {"_source": ("Local Government Directory (LGD) — Districts, data.gov.in resource "
                       f"{RESOURCE}, Government of India. Names as published."),
           "states": dict(sorted(by_state.items()))}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(by_state)} states and union territories, "
          f"{sum(len(s['districts']) for s in by_state.values())} districts")


if __name__ == "__main__":
    main()
