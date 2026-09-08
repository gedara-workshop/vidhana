"""PDF -> text, plus the page health check that decides what needs OCR.

Two Phase 0 findings drive this module:
  * `-layout` is required. Without it clause numbers detach from their clauses,
    which destroys the numbering of a legal instrument.
  * Every page carries a bilingual running header, and the legacy-Sinhala half
    extracts as plausible-looking ASCII. It has to go before an LLM sees the text.
"""
from __future__ import annotations

import re
import subprocess

PAGE_BREAK = "\x0c"

# Thresholds for the needs-OCR test; see page_report().
IMAGE_MIN_PX = 1000      # "large" image: a rasterised form or a page scan
TEXT_MAX_CHARS = 1200    # well under the 2,000-3,700 a real body page carries
EMPTY_TEXT_CHARS = 120   # essentially no text at all

# Lines present in all 21 documents read in Phase 0.
BOILERPLATE = (
    "the gazette of the democratic socialist republic of sri lanka",
    "extraordinary",
    "(published by authority)",
    "part i : section (i) — general",
    "part i : section (i) - general",
    "government notifications",
    "printed at the department of government printing, sri lanka.",
)

# Running page header, print-run codes, and the download footer.
NOISE_RE = re.compile(
    r"(gazette\s+extraordinary\s+of\s+the\s+democratic"
    r"|part\s+i\s*:\s*sec\.?\s*\(i\)"
    r"|this\s+gazette\s+extraordinary\s+can\s+be\s+downloaded"
    r"|^\s*\d*a?\s*[-–—]?\s*(pg|g)\s*\d+"
    r"|^\s*eog\s*\d+\s*[-–]\s*\d+\s*$"
    r"|^\s*\d{2}\s*-\s*\d{3,4}\s*$"
    r"|^\s*\d+a\s*$)", re.I)

# Legacy-font Sinhala. Two distinct encodings across the corpus: 2011+ renders as
# ASCII symbol soup (Y%S ,xld m%cd;dka;%sl), 2007-era as Latin-1 accents (Êòé Èâ¨å).
# Neither is detectable by isascii(), which is why this is structural.
_LEGACY_MARKS = re.compile(r"[%$^&;`]")
# Full Latin-1 supplement, not just the accented letters: the legacy fonts also
# emit ¾ § ¨ ¡ etc. English text in these gazettes uses none of them (its dashes
# and curly quotes are U+2014 / U+2018-201D, outside this range).
_LATIN1 = re.compile(r"[\u00a1-\u00ff]")


def is_legacy_sinhala(line: str) -> bool:
    """Heuristic, because neither encoding is detectable by charset.

    Three signals, any of which is enough:
      0. a gazette number written with '$' -> the Sinhala header line
      1. dense Latin-1 accents  -> the 2007-era font (Êòé Èâ¨å Àò°åºå¾àºòè¨)
      2. a Latin-1 accent *and* a soup symbol -> the 2011+ font, which mixes both
         (Y%S ,xld ... iudcjd§, w;s úfYI, wxl 2463$05 ... fkdjeïn¾)
      3. symbols repeatedly wedged inside words -> pure-ASCII stretches of it

    English legal prose here uses ';' and '&' freely but effectively never carries
    Latin-1 accents, so signal 2 needs both halves to avoid eating real text.
    """
    s = line.strip()
    if len(s) < 6:
        return False
    # Structural: the Sinhala header line writes the gazette number with '$' for
    # '/' ("wxl 2334$21 - 2023 uehs ui 31 jeks nodod"). Some of these carry no
    # accents at all, so the heuristics below can't see them. '$' between digits
    # does not occur in the English text of this corpus.
    if re.search(r"\d\s*\$\s*\d", s):
        return True
    latin1 = len(_LATIN1.findall(s))
    if latin1 / len(s) > 0.15:
        return True
    if latin1 and _LEGACY_MARKS.search(s):
        return True
    wedged = len(re.findall(r"[A-Za-z][%$^&;`][A-Za-z]|[%$^&;`][a-z]{2,}", s))
    return wedged >= 2


def to_text(pdf_path: str, layout: bool = True) -> str:
    cmd = ["pdftotext", "-q"] + (["-layout"] if layout else []) + [pdf_path, "-"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout


def clean(text: str) -> str:
    """Strip boilerplate, running headers and legacy-Sinhala lines."""
    out = []
    for raw in text.replace(PAGE_BREAK, "\n").splitlines():
        s = raw.strip()
        if not s:
            out.append("")
            continue
        if s.lower() in BOILERPLATE or NOISE_RE.search(s) or is_legacy_sinhala(s):
            continue
        out.append(raw.rstrip())
    # collapse runs of blank lines
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def page_report(pdf_path: str) -> list[dict]:
    """Per-page character count and widest embedded image.

    A page with a big image and far less text than a normal body page is a
    rasterised form: its content is invisible to pdftotext and needs OCR.

    Two cases, both of which occur in the 137-document corpus:

      * a rasterised form inside a text PDF (2414/14 pp.5-7): a large image and
        far less text than a normal body page;
      * a genuine full-page scan (1599/13): no text at all, and an image that may
        be modest in pixel terms — that one is only 810px wide, so a size
        threshold alone misses it.

    Both halves still matter. A sparse page alone is not enough: 2217/07 p.21 has
    233 chars but is a real near-empty table with no image. An image alone is not
    enough either: page 1 of most gazettes carries the government crest at ~720px
    alongside full text.
    """
    pages = to_text(pdf_path).split(PAGE_BREAK)
    widths: dict[int, int] = {}
    try:
        listing = subprocess.run(["pdfimages", "-list", pdf_path],
                                 capture_output=True, text=True, timeout=120).stdout
        for line in listing.splitlines()[2:]:
            parts = line.split()
            if len(parts) > 3 and parts[0].isdigit() and parts[3].isdigit():
                p = int(parts[0])
                widths[p] = max(widths.get(p, 0), int(parts[3]))
    except Exception:
        pass

    report = []
    for i, body in enumerate(pages, start=1):
        if i == len(pages) and not body.strip():
            continue                      # trailing empty split after last \f
        chars = len(body.strip())
        w = widths.get(i, 0)
        report.append(dict(page=i, chars=chars, max_image_width=w,
                           needs_ocr=int(bool(w) and (
                               chars < EMPTY_TEXT_CHARS
                               or (w > IMAGE_MIN_PX and chars < TEXT_MAX_CHARS)))))
    return report
