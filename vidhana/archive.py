"""Recover gazettes the IRD listing omits, from the Internet Archive.

Phase 0 left corpus completeness as an open question. Answering it turned up
three facts, in order of how much they matter:

1. **The official source is gone.** `documents.gov.lk`, the Department of
   Government Printing's portal and the canonical index of Extraordinary
   Gazettes, no longer serves its archive: the host returns an unconfigured
   proxy default page, and the old `/view/egz/egz_YYYY.html` index paths return
   a CMS 404. There is currently no authoritative enumeration to check against.

2. **The IRD listing is incomplete inside its own range.** Eight gazettes
   referenced by documents we hold sit between 1439 and 2500 — the range the
   listing covers — and are absent from ird.gov.lk entirely. That is not a
   parsing artefact: probing 123 URL spellings found none of them, while the
   same probe found every control.

3. **The Internet Archive holds a mirror.** Snapshots of documents.gov.lk carry
   the gazette number in the filename, under two layouts across the years, so a
   specific gazette can be looked up by number rather than by crawling.

What this module does *not* do is claim the corpus is complete. It closes holes
it can see. The dangerous case — a gazette nobody lists that rescinds one we
hold — stays invisible by construction, which is why `search` and the feed
disclose an incomplete chain rather than quietly asserting "in force".
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from .fetch import UA

CDX = "http://web.archive.org/cdx/search/cdx"
WAYBACK = "https://web.archive.org/web/{ts}if_/{url}"

# The two filename layouts documents.gov.lk used. Both put the gazette number in
# the path, which is the only reason lookup by number is possible at all.
#   /files/egz/2012/12/1791-08_E.pdf
#   /Extgzt/2006/Pdf/Jun/1447-42/1447-42E.pdf
_NUM = r"(\d{3,4})[-_](\d{1,3})"
LAYOUTS = (
    re.compile(rf"/files/egz/\d{{4}}/\d{{1,2}}/{_NUM}_E\.pdf$", re.I),
    re.compile(rf"/Extgzt/\d{{4}}/PDF/\w+/{_NUM}/{_NUM}\s*\(?E\)?\.pdf$", re.I),
)


class ArchiveUnavailable(RuntimeError):
    """The archive could not be reached or would not answer.

    Deliberately distinct from "no snapshots exist". A completeness check whose
    network error is indistinguishable from an authoritative absence is worse
    than no completeness check at all — it reports a gap it never looked for.
    """


def _get(url: str, timeout: int = 60, attempts: int = 3) -> bytes:
    """GET with backoff. The Internet Archive rate-limits, and it does so most
    readily in the middle of exactly the kind of bulk lookup this module makes."""
    import time

    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                      # network, 429, 5xx alike
            last = e
            if i < attempts - 1:
                time.sleep(2 ** i * 3)
    raise ArchiveUnavailable(f"{url}: {type(last).__name__}: {last}") from last


def _norm(no: str) -> tuple[str, str]:
    n, _, s = no.partition("/")
    return n, s


def find(no: str, timeout: int = 60) -> list[dict]:
    """Snapshots of the English PDF for one gazette number, newest first.

    Queried by number rather than by crawling the archive: the CDX API takes a
    regex over the original URL, and both layouts carry the number in the path.
    """
    n, s = _norm(no)
    # Both a zero-padded and an unpadded sub-number appear across the years, and
    # the separator is sometimes `-` and sometimes `_`.
    subs = dict.fromkeys([f"{int(s):02d}", str(int(s))]) if s.isdigit() else {s: None}
    out: list[dict] = []
    seen = set()
    for sub in subs:
        q = urllib.parse.urlencode({
            "url": "documents.gov.lk*", "output": "json",
            "fl": "original,timestamp,statuscode", "collapse": "urlkey",
            "limit": "20000", "filter": f"original:.*{n}[-_]{sub}.*"})
        # No try/except here on purpose. An unreachable archive must propagate
        # as ArchiveUnavailable, never be folded into an empty result.
        raw = _get(f"{CDX}?{q}", timeout=timeout)
        try:
            rows = json.loads(raw or b"[]")
        except ValueError as e:
            raise ArchiveUnavailable(f"CDX returned non-JSON: {raw[:120]!r}") from e
        for orig, ts, status in rows[1:] if rows and rows[0][0] == "original" else rows:
            if status != "200" or not any(p.search(orig) for p in LAYOUTS):
                continue
            if orig in seen:
                continue
            seen.add(orig)
            out.append(dict(no=no, url=orig, timestamp=ts,
                            snapshot=WAYBACK.format(ts=ts, url=orig)))
    out.sort(key=lambda r: r["timestamp"], reverse=True)
    return out
