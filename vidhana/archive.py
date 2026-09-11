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
import os
import re
import urllib.parse
import urllib.request

from .fetch import UA
from .util import normalise_no

CDX = "http://web.archive.org/cdx/search/cdx"
RECOVERED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "recovered.json")
WAYBACK = "https://web.archive.org/web/{ts}if_/{url}"

# The two filename layouts documents.gov.lk used. Both put the gazette number in
# the path, which is the only reason lookup by number is possible at all.
#   /files/egz/2012/12/1791-08_E.pdf
#   /Extgzt/2006/Pdf/Jun/1447-42/1447-42E.pdf
_NUM = r"(\d{3,4})[-_](\d{1,3})"
LAYOUTS = (
    re.compile(rf"/files/egz/\d{{4}}/\d{{1,2}}/{_NUM}_E\.pdf$", re.I),
    re.compile(rf"/Extgzt/\d{{4}}/PDF/\w+/{_NUM}[/_]{_NUM}\s*\(?E\)?\.pdf$", re.I),
)


def _numbers(url: str) -> list[tuple[int, int]]:
    """Every gazette number a URL claims, normalised.

    A URL can claim two — the archive stores
    `/Extgzt/2006/Pdf/Mar/1439-19/1436-19e.pdf`, where the directory and the
    filename disagree — so both are returned and a caller that cares must
    require all of them to match.
    """
    for pat in LAYOUTS:
        m = pat.search(url)
        if m:
            g = m.groups()
            return [(int(g[i]), int(g[i + 1])) for i in range(0, len(g), 2)]
    return []


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
    want = (int(n), int(s)) if s.isdigit() else None
    if want is None:
        return []
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
            if status != "200" or orig in seen:
                continue
            # Exact number match, never substring. The CDX filter is only a
            # prefilter and it is a regex over the whole URL: asking for 1439/1
            # matches `1439-19` and `1439-10` just as happily as `1439-01`.
            # That is not a theoretical risk — it silently ingested a
            # Provincial Councils Elections gazette as an IRD one.
            claims = _numbers(orig)
            if not claims or any(c != want for c in claims):
                continue
            seen.add(orig)
            out.append(dict(no=no, url=orig, timestamp=ts,
                            snapshot=WAYBACK.format(ts=ts, url=orig)))
    out.sort(key=lambda r: r["timestamp"], reverse=True)
    return out


def missing(con) -> list[dict]:
    """Gazettes our documents reference but the corpus does not hold.

    Split by whether they fall inside the listing's own covered range, because
    the two mean different things. Outside it is expected — the listing starts
    in 2006 and a 1982 order it rescinds was never going to be there. Inside it
    is a defect in the source, and the reason `search` cannot simply assert
    "in force".
    """
    span = con.execute(
        "SELECT MIN(CAST(substr(no,1,instr(no,'/')-1) AS INT)) lo, "
        "       MAX(CAST(substr(no,1,instr(no,'/')-1) AS INT)) hi FROM gazette").fetchone()
    rows = con.execute(
        "SELECT DISTINCT r.dst_no, r.relation, r.src_no, g.published_date "
        "FROM gazette_reference r JOIN gazette g ON g.no = r.src_no "
        "WHERE NOT EXISTS (SELECT 1 FROM gazette h WHERE h.no = r.dst_no) "
        "ORDER BY r.dst_no").fetchall()
    out = []
    for r in rows:
        n = int(r["dst_no"].split("/")[0])
        out.append(dict(no=r["dst_no"], relation=r["relation"], referenced_by=r["src_no"],
                        in_range=bool(span["lo"] <= n <= span["hi"])))
    return out


def backfill(con, no: str, snapshot: dict | None = None, use_ocr: bool = True) -> dict:
    """Recover one gazette from the archive and run it through the pipeline.

    The document is inserted with `source='web-archive'` and the snapshot URL in
    `source_detail`, so nothing downstream can mistake it for something the IRD
    published. Everything else — extraction, parsing, the reference graph — is
    the ordinary Phase 1 path, because a recovered gazette is only useful if it
    is treated exactly as rigorously as a listed one.
    """
    from . import db, pipeline

    if con.execute("SELECT 1 FROM gazette WHERE no=?", (no,)).fetchone():
        return dict(no=no, status="already held")
    hits = snapshot and [snapshot] or find(no)
    if not hits:
        return dict(no=no, status="no snapshot")
    hit = hits[0]

    # The archive's own timestamp is when it crawled, not when the gazette was
    # published. The real date is in the document, and `process` parses it into
    # header_date — so this is a placeholder that gets corrected below, never a
    # claim.
    year = int(re.search(r"/(\d{4})/", hit["url"]).group(1)) if re.search(r"/(\d{4})/", hit["url"]) else int(hit["timestamp"][:4])
    db.upsert_gazette(con, dict(
        no=no, year=year, published_date=f"{year}-01-01",
        title=f"(recovered from the Internet Archive; not in the IRD listing)",
        source_url=hit["snapshot"], source="web-archive",
        source_detail=f"{hit['url']} @ {hit['timestamp']}"))
    con.commit()

    row = con.execute("SELECT * FROM gazette WHERE no=?", (no,)).fetchone()
    res = pipeline.process(con, row, use_ocr=use_ocr)

    # Defence in depth: the URL claimed a number, and now the document itself
    # says one. If they disagree, the document wins and the backfill is undone.
    # A URL is a filing convention maintained by hand across two decades; the
    # printed header is the gazette. Trusting the path alone put a Provincial
    # Councils Elections gazette into the corpus as an IRD one.
    got = con.execute("SELECT header_no FROM gazette WHERE no=?", (no,)).fetchone()["header_no"]
    if got and normalise_no(got) != normalise_no(no):
        _discard(con, no)
        return dict(no=no, status="wrong document",
                    detail=f"snapshot {hit['url']} contains gazette {got}")

    # Correct the placeholder from what the document itself says. The PDF header
    # is authoritative for a document the listing never carried — there is no
    # listing row to disagree with.
    g = con.execute("SELECT header_date, enabling_act FROM gazette WHERE no=?", (no,)).fetchone()
    if g["header_date"]:
        db.upsert_gazette(con, dict(no=no, published_date=g["header_date"],
                                    year=int(g["header_date"][:4])))
        con.commit()
    return dict(no=no, status="recovered", snapshot=hit["snapshot"],
                published=g["header_date"], act=g["enabling_act"],
                warnings=res["warnings"])


def _discard(con, no: str) -> None:
    """Remove a backfilled gazette and everything derived from it.

    Used when a recovered document turns out not to be the one asked for. The
    PDF goes too: `fetch.ensure` skips a download when the file is already
    there, so leaving it would make the next attempt silently reuse the wrong
    document and look like it succeeded.
    """
    import os

    from . import pipeline
    from .fetch import pdf_path

    for t in ("gazette_date", "gazette_page", "gazette_summary",
              "gazette_tag", "gazette_audience"):
        con.execute(f"DELETE FROM {t} WHERE no=?", (no,))
    con.execute("DELETE FROM gazette_reference WHERE src_no=?", (no,))
    con.execute("DELETE FROM gazette_fts WHERE no=?", (no,))
    con.execute("DELETE FROM gazette WHERE no=?", (no,))
    con.commit()
    path = pdf_path(pipeline.PDF_DIR, no)
    for p in (path, os.path.join(pipeline.TEXT_DIR,
                                 os.path.basename(path).replace(".pdf", ".txt"))):
        if os.path.exists(p):
            os.remove(p)


# --- the tracked record ------------------------------------------------------
#
# The database is gitignored and rebuilt from scratch on every nightly run, and
# the IRD listing is the only enumeration a rebuild starts from. A gazette the
# listing omits therefore exists nowhere a cold runner can see unless it is
# written down. It was not, and the first unattended run dropped all seven,
# deleted their summaries, and reported "0 new".
#
# So each recovery is recorded here: the exact archived URL and crawl timestamp
# (a Wayback `if_` capture at a fixed timestamp is immutable, so it can be
# fetched again without searching the archive) and the sha256 of what was
# verified, so a re-fetch that returns something else is caught.

_RECORD_KEYS = ("no", "original", "timestamp", "sha256")


def snapshot_of(rec: dict) -> dict:
    """The `backfill` snapshot argument for a recorded recovery."""
    return dict(no=rec["no"], url=rec["original"], timestamp=rec["timestamp"],
                snapshot=WAYBACK.format(ts=rec["timestamp"], url=rec["original"]))


def load_recovered(path: str = RECOVERED) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def export_recovered(con, path: str = RECOVERED) -> dict:
    """Write every web-archive gazette the database holds into the record.

    Merges, never prunes. An entry whose gazette the database does not hold is
    kept, because "not in this database" is exactly the state a cold rebuild is
    in before it reads this file — pruning on that basis is the bug this record
    exists to fix. Removing a recovery is a deliberate edit to the file.

    Sorted, stable key order and one entry per line of diff, like
    `data/summaries.json`, so a new recovery reads as a one-record change.
    """
    have = {r["no"]: r for r in load_recovered(path)}
    added = 0
    for g in con.execute(
            "SELECT no, source_detail, pdf_sha256 FROM gazette "
            "WHERE source='web-archive' AND pdf_sha256 IS NOT NULL"):
        original, _, ts = (g["source_detail"] or "").rpartition(" @ ")
        if not original or not ts:
            raise ValueError(f"{g['no']}: source_detail is not 'url @ timestamp'")
        rec = dict(no=g["no"], original=original, timestamp=ts, sha256=g["pdf_sha256"])
        if have.get(g["no"]) != rec:
            added += g["no"] not in have
            have[g["no"]] = rec
    rows = [{k: r[k] for k in _RECORD_KEYS} for _, r in sorted(have.items())]
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)
        f.write("\n")
    return dict(total=len(rows), added=added)



def restore(con, path: str = RECOVERED, use_ocr: bool = True) -> list[dict]:
    """Re-acquire every recorded recovery the database does not hold.

    This is what a cold rebuild runs after `sync`. Each document is fetched by
    its exact snapshot URL — no archive search, so nothing here depends on the
    CDX API being up — and its sha256 is checked *before* it is ingested, so a
    document that is not the one we verified never reaches the database. After
    that it goes through `backfill`, which re-verifies the printed header.

    A gazette that has since appeared in the IRD listing is already held once
    `sync` has run, and is left alone: the listing is the better source.

    Returns one result per record. The caller decides what a failure means; the
    CLI treats any as fatal, because a corpus quietly missing a document is the
    exact outcome this function exists to prevent.
    """
    import hashlib

    from . import pipeline
    from .fetch import pdf_path

    out = []
    for rec in load_recovered(path):
        no = rec["no"]
        if con.execute("SELECT 1 FROM gazette WHERE no=?", (no,)).fetchone():
            out.append(dict(no=no, status="already held"))
            continue
        snap = snapshot_of(rec)
        dest = pdf_path(pipeline.PDF_DIR, no)

        # A cached PDF is reused only if it is the document we verified. A stale
        # or foreign file left in the cache would otherwise be skipped over by
        # `fetch.ensure` and ingested as if it were right.
        if os.path.exists(dest):
            with open(dest, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() != rec["sha256"]:
                    os.remove(dest)
        if not os.path.exists(dest):
            try:
                body = _get(snap["snapshot"], timeout=120)
            except ArchiveUnavailable as e:
                out.append(dict(no=no, status="unavailable", detail=str(e)[:120]))
                continue
            got = hashlib.sha256(body).hexdigest()
            if got != rec["sha256"]:
                out.append(dict(no=no, status="hash mismatch",
                                detail=f"expected {rec['sha256'][:12]}, archive served {got[:12]}"))
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest + ".part", "wb") as f:
                f.write(body)
            os.replace(dest + ".part", dest)

        try:
            r = backfill(con, no, snapshot=snap, use_ocr=use_ocr)
        except Exception as e:                # extraction, parsing — leave no half-row
            _discard(con, no)
            out.append(dict(no=no, status="failed", detail=f"{type(e).__name__}: {e}"[:120]))
            continue
        out.append(r)
    return out
