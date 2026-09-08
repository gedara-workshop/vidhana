"""Fetch and parse the IRD gazette listing.

Phase 0: the page is one flat HTML document — an <h4>YEAR</h4> per year, each
followed by a 3-column table. Non-current years are display:none and expanded
client-side, so every row is already in the response. There is no pagination,
no JS requirement, and no robots.txt.
"""
from __future__ import annotations

import html
import re
import urllib.request

from .util import normalise_no, parse_date, quote_url

LISTING_URL = "https://www.ird.gov.lk/en/publications/sitepages/gazette.aspx?menuid=1602"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch(url: str = LISTING_URL, timeout: int = 60) -> str:
    req = urllib.request.Request(quote_url(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def parse(page: str) -> list[dict]:
    """-> [{no, year, published_date, title, source_url}], skipping malformed rows."""
    out: list[dict] = []
    parts = re.split(r"<h4>.*?</i>\s*(\d{4})\s*</h4>", page, flags=re.S)
    for i in range(1, len(parts), 2):
        year, body = parts[i], parts[i + 1].split("<h4>")[0]
        for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 3:
                continue
            no = normalise_no(_text(tds[1]))
            m = re.search(r'href="([^"]+)"', tds[2])
            date = parse_date(_text(tds[0]))
            if not (no and m and date):
                continue          # the empty <tr> under 2006, and any future malformed row
            out.append(dict(no=no, year=int(year), published_date=date,
                            title=_text(tds[2]), source_url=m.group(1)))
    return out
