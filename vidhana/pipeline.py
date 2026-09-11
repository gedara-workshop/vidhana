"""Phase 1 acquisition pipeline: listing -> PDFs -> text -> metadata -> SQLite."""
from __future__ import annotations

import datetime as dt
import os
import subprocess

from . import db, extract, fetch, listing, ocr, parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_DIR = os.path.join(ROOT, "data", "gazettes")
TEXT_DIR = os.path.join(ROOT, "data", "text")


def sync_listing(con, url: str = listing.LISTING_URL) -> int:
    rows = listing.parse(listing.fetch(url))
    for r in rows:
        # Stamped explicitly rather than left to the column default: a gazette
        # backfilled from the archive that later shows up in the listing has
        # genuinely become a listing document, and should stop being flagged as
        # recovered from elsewhere.
        db.upsert_gazette(con, dict(r, source="ird-listing", source_detail=None))
    con.commit()
    return len(rows)


def _pages(path: str) -> int | None:
    out = subprocess.run(["pdfinfo", path], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return None


def process(con, row, force: bool = False, use_ocr: bool = True) -> dict:
    """Fetch, extract and parse one gazette. Idempotent."""
    no = row["no"]
    dest = fetch.pdf_path(PDF_DIR, no)
    warnings: list[str] = []

    downloaded = fetch.ensure(row["source_url"], dest, force=force)
    digest = fetch.sha256(dest)
    if row["pdf_sha256"] and row["pdf_sha256"] != digest:
        # Phase 0 left open whether the listing is strictly append-only. If a
        # published PDF changes under us, that is worth surfacing, not silently
        # overwriting.
        warnings.append(f"pdf changed upstream (was {row['pdf_sha256'][:12]})")

    raw = extract.to_text(dest)
    text = extract.clean(raw)
    pages_meta = extract.page_report(dest)

    # Splice in OCR for pages whose content is an image. Appended with markers
    # rather than merged into the body, so OCR-derived text stays identifiable.
    if use_ocr and any(p["needs_ocr"] for p in pages_meta):
        for p in pages_meta:
            if not p["needs_ocr"]:
                continue
            got = ocr.read_page(dest, digest, no, p["page"])
            p["ocr_chars"] = len(got)
            if got:
                text += (f"\n\n{ocr.BEGIN} (page {p['page']})\n{got}\n{ocr.END}\n")
    os.makedirs(TEXT_DIR, exist_ok=True)
    tpath = os.path.join(TEXT_DIR, os.path.basename(dest).replace(".pdf", ".txt"))
    with open(tpath, "w") as f:
        f.write(text)

    pages = pages_meta
    header_no, header_date = parse.header(text)
    act, act_no = parse.enabling_act(text)
    name, role = parse.authority(text)
    # These two compare the PDF against the listing. A gazette recovered from an
    # archive has no listing row to disagree with — its date is a placeholder
    # that the parsed header then corrects — so the comparison would only ever
    # report our own placeholder back at us.
    keys = row.keys() if hasattr(row, "keys") else row
    listed = ("source" not in keys) or row["source"] != "web-archive"
    if listed and header_no and header_no != no:
        warnings.append(f"pdf header says {header_no}, listing says {no}")
    if listed and header_date and header_date != row["published_date"]:
        warnings.append(f"pdf date {header_date} != listing {row['published_date']}")
    if not act:
        warnings.append("no enabling act found")

    db.upsert_gazette(con, dict(
        no=no, pdf_path=os.path.relpath(dest, ROOT), pdf_sha256=digest,
        pdf_bytes=os.path.getsize(dest), pages=_pages(dest),
        fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        header_no=header_no, header_date=header_date,
        enabling_act=act, enabling_act_no=act_no,
        authority=name, authority_role=role,
        subject=parse.subject(act, row["title"]),
        text_path=os.path.relpath(tpath, ROOT), text_chars=len(text),
        needs_ocr=int(any(p["needs_ocr"] for p in pages)),
        parse_warnings="\n".join(warnings) or None))

    db.replace_children(con, "gazette_date", no,
                        [dict(no=no, **d) for d in parse.dates(text)])
    db.replace_children(con, "gazette_reference", no,
                        [dict(src_no=no, **r) for r in parse.references(text, self_no=no)])
    db.replace_children(con, "gazette_page", no, [dict(no=no, **p) for p in pages])
    db.index_fts(con, no, row["title"], text)
    con.commit()
    return dict(no=no, downloaded=downloaded, warnings=warnings,
                needs_ocr=any(p["needs_ocr"] for p in pages))
