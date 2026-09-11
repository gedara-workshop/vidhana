"""OCR for the pages `extract.page_report` flagged as image-borne.

Three documents in 137 need this, and they need it for two different reasons:

  * 1599/13 is a genuine full-page scan with no text layer at all;
  * 2414/14 pp.5-7 and 2064/59 embed rasterised forms inside an otherwise
    normal text PDF.

Both are handled the same way — render the page and read it — but the second case
is why OCR runs per page rather than per document: re-OCRing a page that already
has good embedded text would replace it with a worse copy.

OCR output is materially noisier than the native text layer ("ae virtue" for "BY
virtue"), so it is stored separately and marked, never silently merged into the
same field as extracted text.

**Raw OCR output is tracked in data/ocr.json and reused.** Tesseract is not
reproducible across machines: the version on GitHub's Ubuntu runner reads the
same page differently from the one on a Mac, so a corpus rebuilt in one place
and published from the other changed its text on every run, and the nightly
job committed OCR noise as if the law had moved. Keyed by the PDF's sha256 and
the page, so a changed PDF is read afresh and an unchanged one never is.
Stored raw, before `_tidy`, so improving the tidy never needs a re-OCR. A
machine without tesseract can still build the whole corpus from the store.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

STORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "ocr.json")

DPI = 300
LANG = "eng"

# Marks OCR-derived text in the assembled document, so anything downstream — a
# reader, a prompt, a future parser — can tell it apart from the text layer.
BEGIN = "[OCR BEGIN — text below is machine-read from a page image and may contain errors]"
END = "[OCR END]"


def available() -> bool:
    return bool(shutil.which("tesseract") and shutil.which("pdftoppm"))


def engine(lang: str = LANG, dpi: int = DPI) -> str:
    """What produced a stored reading — provenance, not a cache key."""
    try:
        v = subprocess.run(["tesseract", "--version"], capture_output=True, text=True,
                           timeout=30).stdout.splitlines()[0].strip()
    except (OSError, IndexError, subprocess.SubprocessError):
        v = "tesseract (unknown version)"
    return f"{v}, {lang}, {dpi}dpi"


def _tesseract(pdf_path: str, page: int, dpi: int = DPI, lang: str = LANG) -> str | None:
    """Render one page and read it. None if the tooling is missing or fails."""
    if not available():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        stem = os.path.join(tmp, "pg")
        r = subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", pdf_path, stem],
            capture_output=True, timeout=300)
        if r.returncode != 0:
            return None
        pngs = [f for f in os.listdir(tmp) if f.endswith(".png")]
        if not pngs:
            return None
        out = subprocess.run(
            ["tesseract", os.path.join(tmp, pngs[0]), "-", "-l", lang],
            capture_output=True, text=True, timeout=300)
        return out.stdout if out.returncode == 0 else None


def ocr_page(pdf_path: str, page: int, dpi: int = DPI, lang: str = LANG) -> str:
    """Render one page and read it, tidied. "" if the tooling is missing or fails.
    Bypasses the store; the pipeline uses `read_page`."""
    return _tidy(_tesseract(pdf_path, page, dpi, lang) or "")


def load_store(path: str = STORE) -> dict[tuple[str, int], dict]:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {(r["sha256"], r["page"]): r for r in json.load(f)}


def save_store(store: dict[tuple[str, int], dict], path: str = STORE) -> None:
    """Sorted by gazette then page, one reading per record, so a new gazette's
    OCR is a readable diff. Merge-only: nothing here ever removes a reading."""
    rows = sorted(store.values(), key=lambda r: (r["no"], r["page"], r["sha256"]))
    with open(path, "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_page(pdf_path: str, sha256: str, no: str, page: int, path: str = STORE) -> str:
    """The tidied text of one image page, from the store if it has been read before.

    Only a page the store has never seen reaches tesseract, and its raw output
    is recorded immediately, so every machine that builds the corpus afterwards
    produces the same text.
    """
    store = load_store(path)
    hit = store.get((sha256, page))
    if hit is None:
        raw = _tesseract(pdf_path, page)
        if raw is None:
            return ""
        store[(sha256, page)] = dict(no=no, page=page, sha256=sha256, engine=engine(), text=raw)
        save_store(store, path)
        hit = store[(sha256, page)]
    return _tidy(hit["text"])


def _tidy(text: str) -> str:
    """Drop the debris OCR produces on these pages.

    Tesseract renders the legacy-Sinhala half of each gazette as short runs of
    nonsense ("Goth) Geant wore) cndded od oad"), which is noise in every case —
    the English half carries the content.
    """
    kept = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            kept.append("")
            continue
        letters = sum(c.isalpha() for c in s)
        if letters < 3:
            continue
        # a line with almost no vowels is not English prose
        vowels = sum(c.lower() in "aeiou" for c in s)
        if letters > 8 and vowels / letters < 0.12:
            continue
        kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


# --- what reaches search and the site -----------------------------------------
#
# `_tidy` judges one line at a time with nothing to compare it to, and lets
# through exactly the lines it was written for: the legacy-Sinhala masthead on
# every scanned page ("Goth) Geant wore) cndded od oad") has plenty of vowels.
# Rotated form pages come out as mirror-text ("(opjuonezteas soueuoyureat") that
# passes too. All of it went into the search index and the site's full text.
#
# The corpus itself says what English looks like here: 141 documents carry a
# real text layer. A line of OCR is kept for search when at least half its
# words are words those documents use. The masthead and the mirror-text score
# zero; "Cost of improvements/ maintenance/ repairs" scores a half and stays.
#
# This runs where the whole corpus is visible — `reindex` and `web.build` —
# and never in the per-document pipeline: the vocabulary depends on every
# other document, so filtering one document at a time would depend on the
# order they were processed in. Parsing still reads the unfiltered text, so no
# parsed field can change because of it.

_WORD = re.compile(r"[A-Za-z]{3,}")
_BLOCK = re.compile(rf"({re.escape(BEGIN)}[^\n]*\n)(.*?)(\n{re.escape(END)})", re.S)
KEEP_RATIO = 0.5


def vocabulary(con) -> frozenset[str]:
    """Words used at least twice across the documents with a real text layer."""
    import collections

    seen: collections.Counter = collections.Counter()
    for r in con.execute(
            "SELECT text_path FROM gazette WHERE needs_ocr = 0 AND text_path IS NOT NULL"):
        try:
            with open(r["text_path"]) as f:
                seen.update(w.lower() for w in _WORD.findall(f.read()))
        except FileNotFoundError:
            continue
    return frozenset(w for w, n in seen.items() if n >= 2)


def _english(line: str, vocab: frozenset[str]) -> bool:
    words = [w.lower() for w in _WORD.findall(line)]
    return bool(words) and sum(w in vocab for w in words) / len(words) >= KEEP_RATIO


def searchable(text: str, vocab: frozenset[str]) -> str:
    """`text` with OCR blocks reduced to the lines that read as English.

    Only inside the OCR markers; the text layer is never touched. With no
    vocabulary — no text layer anywhere yet — the text is returned as it is
    rather than emptied.
    """
    if not vocab or BEGIN not in text:
        return text

    def keep(m: re.Match) -> str:
        lines = [l for l in m.group(2).split("\n") if not l.strip() or _english(l, vocab)]
        body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n")
        return m.group(1) + body + m.group(3)

    return _BLOCK.sub(keep, text)
