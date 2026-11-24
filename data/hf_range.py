"""Read a Parquet file on the Hugging Face Hub a byte range at a time, so a
script can take the rows it needs from a multi-gigabyte shard without
downloading the shard. The token comes from the environment (HF_TOKEN) and is
never written anywhere."""

from __future__ import annotations

import io
import os
import time
import urllib.request

HUB = "https://huggingface.co/datasets/{repo}/resolve/main/{path}"


class RangeFile(io.RawIOBase):
    def __init__(self, repo: str, path: str, size: int):
        self.url, self.size, self.pos = HUB.format(repo=repo, path=path), size, 0
        self.fetched = 0
        self._signed: str | None = None

    def _resolve(self) -> str:
        # The Hub answers with a redirect to signed storage; resolve it once.
        if self._signed is None:
            req = urllib.request.Request(self.url, method="GET",
                                         headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}",
                                                  "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                self._signed = r.geturl()
        return self._signed

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        if n <= 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        for attempt in range(10):
            try:
                req = urllib.request.Request(self._resolve(), headers={"Range": f"bytes={self.pos}-{end}"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = r.read()
                break
            except Exception:  # noqa: BLE001  a signed link can expire mid-run: sign again
                # Also a connection that fails certificate verification: retried,
                # never accepted — the token travels with these requests.
                self._signed = None
                time.sleep(min(30, 2 * (attempt + 1)))
        else:
            raise OSError(f"could not read {self.url} bytes {self.pos}-{end}")
        self.pos += len(data)
        self.fetched += len(data)
        return data

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)
