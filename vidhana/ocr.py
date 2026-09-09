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
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

DPI = 300
LANG = "eng"

# Marks OCR-derived text in the assembled document, so anything downstream — a
# reader, a prompt, a future parser — can tell it apart from the text layer.
BEGIN = "[OCR BEGIN — text below is machine-read from a page image and may contain errors]"
END = "[OCR END]"


def available() -> bool:
    return bool(shutil.which("tesseract") and shutil.which("pdftoppm"))


def ocr_page(pdf_path: str, page: int, dpi: int = DPI, lang: str = LANG) -> str:
    """Render one page and read it. Returns "" if the tooling is missing or fails."""
    if not available():
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        stem = os.path.join(tmp, "pg")
        r = subprocess.run(
            ["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-png", pdf_path, stem],
            capture_output=True, timeout=300)
        if r.returncode != 0:
            return ""
        pngs = [f for f in os.listdir(tmp) if f.endswith(".png")]
        if not pngs:
            return ""
        out = subprocess.run(
            ["tesseract", os.path.join(tmp, pngs[0]), "-", "-l", lang],
            capture_output=True, text=True, timeout=300)
        return _tidy(out.stdout)


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
