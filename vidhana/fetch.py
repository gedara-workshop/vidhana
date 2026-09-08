"""Download gazette PDFs. Serial and unhurried on purpose.

The whole corpus is 137 documents on a single government host with no robots.txt.
There is nothing to gain from concurrency and something to lose.
"""
from __future__ import annotations

import hashlib
import os
import time
import urllib.request

from .util import quote_url, slug

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DELAY_SECONDS = 1.5


def pdf_path(pdf_dir: str, no: str) -> str:
    return os.path.join(pdf_dir, slug(no) + ".pdf")


def download(url: str, dest: str, timeout: int = 120) -> None:
    req = urllib.request.Request(quote_url(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if not data[:5].startswith(b"%PDF"):
        raise ValueError(f"not a PDF: {url}")
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)          # never leave a half-written PDF in place


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure(url: str, dest: str, force: bool = False) -> bool:
    """Download unless already present. -> True if a request was made."""
    if os.path.exists(dest) and not force:
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    download(url, dest)
    time.sleep(DELAY_SECONDS)
    return True
