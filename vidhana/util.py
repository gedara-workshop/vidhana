"""Small shared helpers. Mostly normalisation, which Phase 0 showed is load-bearing."""
from __future__ import annotations

import datetime as _dt
import re
import urllib.parse

# Gazette numbers appear three ways: "2217/07" (listing), "2217/7" (PDF header),
# "2295$10" (legacy-font Sinhala line, $ maps to /). Everything normalises to the
# listing's zero-padded form, or graph edges silently fail to connect.
_NO_RE = re.compile(r"^\s*(\d{3,4})\s*[/$]\s*(\d{1,3})\s*$")


def normalise_no(raw: str) -> str | None:
    """'2217/7' -> '2217/07'. Returns None if it isn't a gazette number."""
    if not raw:
        return None
    m = _NO_RE.match(raw.replace("–", "-"))
    if not m:
        return None
    return f"{int(m.group(1))}/{int(m.group(2)):02d}"


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
_MONTHS.update({m[:3].lower(): i for m, i in list(_MONTHS.items())})


def parse_date(raw: str) -> str | None:
    """Parse the date shapes seen across 2006-2026 into ISO yyyy-mm-dd.

    Handles: '06 Aug 2026', 'THURSDAY, AUGUST 06, 2026', 'thursday, april 04, 2024',
    'SUNDAY, APRIL 01 2018' (no comma), '2024'12'11', '11.12.2024', '01st April, 2018'.
    """
    if not raw:
        return None
    s = re.sub(r"\s+", " ", raw).strip().strip(",.")
    s = re.sub(r"^[A-Za-z]+day\s*,?\s*", "", s, flags=re.I)  # drop weekday

    # 2024'12'11  /  11.12.2024  /  2024.12.11
    m = re.search(r"\b(\d{4})['.\-/](\d{1,2})['.\-/](\d{1,2})\b", s)
    if m:
        return _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(\d{1,2})['.\-/](\d{1,2})['.\-/](\d{4})\b", s)
    if m:
        return _iso(int(m.group(3)), int(m.group(2)), int(m.group(1)))

    # 'AUGUST 06, 2026' / 'April 1, 2024' / 'APRIL 01 2018'
    m = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b", s)
    if m and m.group(1).lower() in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))

    # '06 Aug 2026' / '01st April, 2018'
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s*,?\s*(\d{4})\b", s)
    if m and m.group(2).lower() in _MONTHS:
        return _iso(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


def _iso(y: int, mo: int, d: int) -> str | None:
    try:
        return _dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def quote_url(url: str) -> str:
    """IRD hrefs contain raw spaces; encode the path and leave the rest alone."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (p.scheme, p.netloc, urllib.parse.quote(p.path, safe="/%"), p.query, p.fragment))


def load_env(path: str = ".env") -> None:
    """Minimal .env loader so we don't take a python-dotenv dependency.

    Existing environment variables win, so an exported key overrides the file.
    """
    import os
    if not os.path.exists(path):
        return
    for line in open(path):
        m = re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*["\']?([^"\'\n]*)', line)
        if m and m.group(1) not in os.environ:
            os.environ[m.group(1)] = m.group(2).strip()


def slug(no: str) -> str:
    """Local filename stem. Derived, never authoritative."""
    return no.replace("/", "-")
