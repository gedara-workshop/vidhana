"""Command line for the acquisition pipeline.

    python -m vidhana init                 create the database
    python -m vidhana sync                 refresh the listing (one request)
    python -m vidhana fetch [--limit N]    fetch + parse gazettes not yet processed
    python -m vidhana status               what is in the database
    python -m vidhana show 2481/22         one gazette, with its graph edges
    python -m vidhana search "tax invoice" full-text search
    python -m vidhana chain 2500/106       walk the amendment chain
"""
from __future__ import annotations

import argparse
import sys

from . import db, listing, pipeline


def cmd_init(a):
    con = db.connect(a.db)
    db.init(con)
    print(f"database ready: {a.db}")


def cmd_sync(a):
    con = db.connect(a.db)
    db.init(con)
    n = pipeline.sync_listing(con)
    print(f"listing: {n} gazettes")


def cmd_fetch(a):
    con = db.connect(a.db)
    all_rows = a.force or a.reparse
    rows = con.execute(
        "SELECT * FROM gazette WHERE (pdf_sha256 IS NULL OR ?) ORDER BY published_date DESC",
        (1 if all_rows else 0,)).fetchall()
    if a.subject:
        rows = [r for r in rows if (r["subject"] or "") in a.subject]
    if a.limit:
        rows = rows[:a.limit]
    print(f"{len(rows)} to process")
    done = failed = 0
    for r in rows:
        try:
            res = pipeline.process(con, r, force=a.force)  # reparse reuses the PDF
        except Exception as e:                       # keep going; one bad PDF is not fatal
            failed += 1
            print(f"  FAIL {r['no']}: {type(e).__name__}: {e}")
            continue
        done += 1
        flags = []
        if res["needs_ocr"]:
            flags.append("needs-ocr")
        flags += res["warnings"]
        print(f"  ok {r['no']:>9}  {'; '.join(flags) if flags else ''}")
    print(f"\nprocessed {done}, failed {failed}")


def cmd_status(a):
    con = db.connect(a.db)
    q = lambda s, *p: con.execute(s, p).fetchall()
    total = q("SELECT COUNT(*) c FROM gazette")[0]["c"]
    fetched = q("SELECT COUNT(*) c FROM gazette WHERE pdf_sha256 IS NOT NULL")[0]["c"]
    print(f"gazettes in listing : {total}")
    print(f"fetched + parsed    : {fetched}")
    print(f"needing OCR         : {q('SELECT COUNT(*) c FROM gazette WHERE needs_ocr=1')[0]['c']}")
    edges = q("SELECT COUNT(*) c FROM gazette_reference")[0]["c"]
    dang = q("SELECT COUNT(*) c FROM gazette_reference r "
             "LEFT JOIN gazette g ON g.no=r.dst_no WHERE g.no IS NULL")[0]["c"]
    print(f"amendment edges     : {edges}  ({dang} pointing outside the listing)")
    print(f"typed dates         : {q('SELECT COUNT(*) c FROM gazette_date')[0]['c']}")
    print("\nby subject:")
    for r in q("SELECT COALESCE(subject,'(unparsed)') s, COUNT(*) c FROM gazette "
               "GROUP BY s ORDER BY c DESC"):
        print(f"  {r['c']:>4}  {r['s']}")
    if dang:
        print("\nreferenced but absent from the IRD listing "
              "(mostly pre-2006, which the listing does not cover):")
        for r in q("SELECT DISTINCT dst_no FROM gazette_reference r "
                   "LEFT JOIN gazette g ON g.no=r.dst_no WHERE g.no IS NULL "
                   "ORDER BY CAST(dst_no AS INTEGER)"):
            print(f"  {r['dst_no']}")

    warn = q("SELECT no, parse_warnings FROM gazette WHERE parse_warnings IS NOT NULL")
    if warn:
        print(f"\nwarnings ({len(warn)}):")
        for r in warn:
            for line in r["parse_warnings"].splitlines():
                print(f"  {r['no']:>9}  {line}")


def cmd_show(a):
    con = db.connect(a.db)
    g = con.execute("SELECT * FROM gazette WHERE no=?", (a.no,)).fetchone()
    if not g:
        sys.exit(f"no such gazette: {a.no}")
    print(f"{g['no']}  {g['published_date']}  [{g['subject']}]")
    print(f"  {g['title']}")
    print(f"  act       : {g['enabling_act']}, No. {g['enabling_act_no']}")
    print(f"  authority : {g['authority']} ({g['authority_role']})")
    print(f"  pdf       : {g['pdf_path']}  {g['pages']}p"
          f"{'  NEEDS OCR' if g['needs_ocr'] else ''}")
    print(f"  source    : {g['source_url']}")
    dates = con.execute("SELECT * FROM gazette_date WHERE no=? ORDER BY kind, date",
                        (a.no,)).fetchall()
    if dates:
        print("  dates:")
        for d in dates:
            print(f"    {d['kind']:<18} {d['date']}")
    out = con.execute("SELECT * FROM gazette_reference WHERE src_no=?", (a.no,)).fetchall()
    inc = con.execute("SELECT * FROM gazette_reference WHERE dst_no=?", (a.no,)).fetchall()
    for label, rows, key in (("references", out, "dst_no"), ("referenced by", inc, "src_no")):
        if rows:
            print(f"  {label}:")
            for r in rows:
                print(f"    {r['relation']:<18} {r[key]}")


def cmd_chain(a):
    """Walk supersession both ways. The current state of a rule usually exists in
    no single gazette, so this is the view that matters."""
    con = db.connect(a.db)
    seen, order = set(), []

    def walk(no, depth=0, via=""):
        if no in seen or depth > 12:
            return
        seen.add(no)
        g = con.execute("SELECT published_date, title FROM gazette WHERE no=?", (no,)).fetchone()
        order.append((depth, no, g["published_date"] if g else "?",
                      (g["title"][:64] if g else "(not in listing)"), via))
        for r in con.execute(
                "SELECT src_no, relation FROM gazette_reference WHERE dst_no=? "
                "AND relation IN ('amends','rescinds','last_amended_by')", (no,)):
            walk(r["src_no"], depth + 1, f"<- {r['relation']}")
        for r in con.execute(
                "SELECT dst_no, relation FROM gazette_reference WHERE src_no=? "
                "AND relation IN ('amends','rescinds','last_amended_by')", (no,)):
            walk(r["dst_no"], depth + 1, f"-> {r['relation']}")

    walk(a.no)
    for depth, no, date, title, via in sorted(order, key=lambda x: x[2]):
        print(f"  {date}  {no:>9}  {via:<22} {title}")


def cmd_search(a):
    con = db.connect(a.db)
    rows = con.execute(
        "SELECT f.no, g.published_date, g.subject, g.title, "
        "snippet(gazette_fts, 2, '[', ']', '...', 12) s "
        "FROM gazette_fts f JOIN gazette g ON g.no=f.no "
        "WHERE gazette_fts MATCH ? ORDER BY rank LIMIT ?", (a.query, a.limit)).fetchall()
    if not rows:
        print("no matches")
    for r in rows:
        print(f"\n{r['no']:>9}  {r['published_date']}  [{r['subject']}]\n"
              f"  {r['title'][:96]}\n  …{r['s']}…")


def main(argv=None):
    p = argparse.ArgumentParser(prog="vidhana", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=db.DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)

    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int)
    f.add_argument("--force", action="store_true", help="re-download and re-parse")
    f.add_argument("--reparse", action="store_true",
                   help="re-extract and re-parse from PDFs already on disk, no downloads")
    f.add_argument("--subject", nargs="*", help="only these subjects, e.g. vat income-tax")
    f.set_defaults(fn=cmd_fetch)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    s = sub.add_parser("show"); s.add_argument("no"); s.set_defaults(fn=cmd_show)
    c = sub.add_parser("chain"); c.add_argument("no"); c.set_defaults(fn=cmd_chain)

    q = sub.add_parser("search"); q.add_argument("query")
    q.add_argument("--limit", type=int, default=10); q.set_defaults(fn=cmd_search)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
