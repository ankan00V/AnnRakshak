"""AIKosh, the Government of India's AI datasets repository.

Searched on 1 Oct 2026 for the classes the model is thinnest on — maize maydis
leaf blight, curvularia, downy mildew, aphid; rice false smut, skipper, white
stem borer. It has no new crop imagery for any of them. Its one crop-disease
image dataset is the ICAR rice and maize set this repo is already built on
(971 MB there against the 933 MB copy in data/raw, the same release).

That is still worth having established, for two reasons.

The first is provenance. The ICAR images now have an official government home
to cite — AIKosh dataset 2448fb9b-d9c5-4f68-a3e2-dea280d6a73d, published by
DARE/ICAR — rather than "downloaded by the team from a public repository".
For a dataset that carries the deploy checks, that matters.

The second is what else is in there. "Farmer Query Signal Intent Dataset"
(25169990-a8fb-41b4-978c-8113a7e418a6) is hand-written agricultural queries in
Hindi, which is the shape of the problem Krishi's intent routing solves and
the labelled set that routing has never had.

    AIKOSH_API_KEY=... in .env   (My Profile -> Account Settings -> Create API Key)
    .venv/bin/python data/aikosh_search.py "rice disease"

Named aikosh_search and not aikosh: a script run directly puts its own folder
first on the import path, so a file called aikosh.py imports itself instead of
the SDK it means to call, and says the SDK has no attribute "datasets".

Read-only: the key is used to search, read metadata and fetch download links,
and nothing here writes to AIKosh.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"
ICAR_DATASET = "2448fb9b-d9c5-4f68-a3e2-dea280d6a73d"
"""The rice and maize set data/raw/icar_rice_maize came from, on its home platform."""


def key() -> str:
    """The API key, from the environment or .env. Never printed."""
    if os.environ.get("AIKOSH_API_KEY"):
        return os.environ["AIKOSH_API_KEY"]
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if line.startswith("AIKOSH_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("set AIKOSH_API_KEY in .env (AIKosh -> My Profile -> Account Settings)")


def search(keyword: str, size: int = 20) -> list[dict]:
    """Datasets matching `keyword`, newest API shape flattened to a list."""
    import aikosh  # noqa: PLC0415  an optional dependency: only this script needs it

    out = aikosh.datasets.list_datasets(access_key=key(), keyword=keyword, size=size)
    if isinstance(out, dict):
        out = out.get("data") or out.get("results") or []
    return [x for x in out if isinstance(x, dict)]


def main() -> None:
    words = sys.argv[1:] or ["crop disease"]
    for word in words:
        rows = search(word)
        print(f"\n{word!r}: {len(rows)} dataset(s)")
        for r in rows:
            org = (r.get("organization") or {}).get("name", "")
            size = ((r.get("stats") or {}).get("size") or 0) / 1e6
            print(f"  {str(r.get('name'))[:62]:64s} {size:8.0f} MB  {org[:28]}")


if __name__ == "__main__":
    main()
