"""Download files from Dryad, which needs an API account and one small trick.

Dryad's public file links sit behind a bot wall (a plain curl gets an
interstitial page, not the file), so downloads go through the API with a token
minted from the team's client credentials in .env. The trick: the API answers a
download with a redirect to a presigned S3 link, and S3 refuses a request that
carries both its own signature and our bearer token, so the Authorization
header is dropped when the redirect is followed.

    from dryad import files, download
    for f in files("doi:10.5061/dryad.41ns1rnj3"):
        print(f["path"], f["size"], f["id"])
    download(1916024, Path("README.md"))
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://datadryad.org/api/v2"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
ENV = Path(__file__).resolve().parents[1] / ".env"


class _StripAuth(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Authorization")
        return new


_opener = urllib.request.build_opener(_StripAuth)
_token: str | None = None


def _creds() -> tuple[str, str]:
    env = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.startswith("DRYAD_"):
                env[k] = v
    cid = os.environ.get("DRYAD_CLIENT_ID") or env.get("DRYAD_CLIENT_ID")
    secret = os.environ.get("DRYAD_CLIENT_SECRET") or env.get("DRYAD_CLIENT_SECRET")
    if not cid or not secret:
        raise SystemExit("set DRYAD_CLIENT_ID and DRYAD_CLIENT_SECRET in .env")
    return cid, secret


def token() -> str:
    """A bearer token, minted once per process (Dryad's last ten hours)."""
    global _token
    if _token is None:
        cid, secret = _creds()
        body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                       "client_id": cid, "client_secret": secret}).encode()
        req = urllib.request.Request("https://datadryad.org/oauth/token", data=body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded",
                                              "User-Agent": UA})
        _token = json.load(_opener.open(req, timeout=60))["access_token"]
    return _token


def _get(path: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers={"User-Agent": UA})
    return json.load(_opener.open(req, timeout=60))


def files(doi: str) -> list[dict]:
    """[{path, size, id}] for the newest version of a dataset ('doi:10.5061/dryad.xxxxx')."""
    ds = _get(f"/datasets/{urllib.parse.quote(doi, safe='')}")
    version = ds["_links"]["stash:version"]["href"].rsplit("/", 1)[-1]
    out = []
    for f in _get(f"/versions/{version}/files?per_page=100")["_embedded"]["stash:files"]:
        out.append({"path": f["path"], "size": f["size"],
                    "id": int(f["_links"]["stash:download"]["href"].split("/")[-2])})
    return out


def download(file_id: int, dst: Path, chunk: int = 1 << 20) -> Path:
    req = urllib.request.Request(f"{API}/files/{file_id}/download",
                                 headers={"Authorization": f"Bearer {token()}", "User-Agent": UA})
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_suffix(dst.suffix + ".part")
    with _opener.open(req, timeout=600) as r, part.open("wb") as f:
        while block := r.read(chunk):
            f.write(block)
    part.rename(dst)
    return dst
