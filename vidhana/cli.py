"""Command line for the acquisition pipeline.

    python -m vidhana init                 create the database
    python -m vidhana sync                 refresh the listing (one request)
    python -m vidhana fetch [--limit N]    fetch + parse gazettes not yet processed
    python -m vidhana status               what is in the database
    python -m vidhana show 2481/22         one gazette, with its graph edges
    python -m vidhana search "tax invoice"   full-text search, with resolved state
    python -m vidhana search "tax invoice" --rules      one result per rule
    python -m vidhana search "lease" --audience notaries --in-force
    python -m vidhana search "transfer pricing" --as-of 2015-01-01
    python -m vidhana facets                 the facet lists worth filtering on
    python -m vidhana reindex                rebuild the index and facets
    python -m vidhana verify [--find]        what the corpus is missing
    python -m vidhana backfill               recover omitted gazettes from the archive
    python -m vidhana whatsnew --since 2025-01-01   what changed, and what it changed
    python -m vidhana feed                   write the Atom feeds under docs/feeds
    python -m vidhana summaries export       the LLM output, tracked in git
    python -m vidhana summaries import       restore it without paying again
    python -m vidhana chain 2500/106       walk the raw amendment edges
    python -m vidhana resolve              rebuild rule threads and in-force state
    python -m vidhana threads              list the rule threads
    python -m vidhana rule 2500/106        the rule this gazette belongs to, resolved
    python -m vidhana rule 2481/22 --as-of 2026-08-01
    python -m vidhana structure [--limit N]  LLM summaries + audience (costs money)
    python -m vidhana validate               grade the model against Phase 1 fields
    python -m vidhana batch submit           half price, async, parallel server-side
    python -m vidhana batch status [ID]
    python -m vidhana batch collect [ID]
"""
from __future__ import annotations

import argparse
import sys

from . import alerts, archive, db, listing, pipeline, resolve, search, structure


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


def cmd_resolve(a):
    con = db.connect(a.db)
    r = resolve.resolve(con)
    print(f"rule threads   : {r['threads']}")
    print(f"in a thread    : {r['threaded']}")
    print(f"standalone     : {r['standalone']}")
    print(f"rescinded      : {r['rescinded']}")


def cmd_threads(a):
    con = db.connect(a.db)
    rows = con.execute(
        "SELECT * FROM rule_thread ORDER BY size DESC, first_date").fetchall()
    if not rows:
        sys.exit("no threads — run `vidhana resolve` first")
    for t in rows:
        flag = f"  ({t['unresolved']} unresolved)" if t["unresolved"] else ""
        print(f"#{t['thread_id']:<3} {t['size']:>2} docs  {t['first_date'][:4]}-{t['last_date'][:4]}"
              f"  [{t['subject']}]  head={t['head_no']}{flag}")
        print(f"      {t['label'][:96]}")


def cmd_rule(a):
    """The resolved view: what defines this rule, what still stands, what is current."""
    con = db.connect(a.db)
    g = con.execute("SELECT * FROM gazette WHERE no=?", (a.no,)).fetchone()
    if not g:
        sys.exit(f"no such gazette: {a.no}")
    if g["status"] is None:
        sys.exit("state not resolved — run `vidhana resolve` first")
    if g["thread_id"] is None:
        print(f"{a.no} is standalone — it neither amends nor is amended by anything held.")
        print(f"  {g['published_date']}  effective {g['effective_from']}  [{g['subject']}]")
        print(f"  {g['title']}")
        return

    t = con.execute("SELECT * FROM rule_thread WHERE thread_id=?", (g["thread_id"],)).fetchone()
    print(f"rule thread #{t['thread_id']}  [{t['subject']}]  {t['first_date'][:4]}-{t['last_date'][:4]}"
          f"  {t['size']} documents")
    print(f"  {t['enabling_act'] or ''}")
    print()

    if a.as_of:
        rows = resolve.operative_on(con, t["thread_id"], a.as_of)
        print(f"operative on {a.as_of}:")
        for r in rows:
            mark = "*" if r["no"] == t["head_no"] else " "
            print(f"  {mark} {r['no']:>9}  effective {r['effective_from']}  {r['title'][:62]}")
        if not rows:
            print("  (nothing — the rule had not taken effect yet)")
        return

    for r in con.execute(
            "SELECT * FROM gazette WHERE thread_id=? ORDER BY published_date",
            (t["thread_id"],)):
        mark = "*" if r["no"] == t["head_no"] else " "
        note = ""
        if r["status"] == "rescinded":
            note = f"  rescinded by {r['rescinded_by']} from {r['rescinded_from']}"
        eff = r["effective_from"]
        eff_note = f"  effective {eff}" if eff != r["published_date"] else ""
        print(f"{mark} {r['published_date']}  {r['no']:>9}  {r['status']:<10}{eff_note}{note}")
        print(f"      {r['title'][:92]}")

    print(f"\ncurrent: {t['head_no']}")
    if t["unresolved"]:
        print(f"warning: {t['unresolved']} reference(s) point at gazettes the IRD listing "
              f"does not carry, so this history may be incomplete")


def cmd_structure(a):
    con = db.connect(a.db)
    if a.only:
        todo = [{"no": n} for n in a.only]
    else:
        todo = con.execute(
            "SELECT no FROM gazette WHERE (? OR no NOT IN (SELECT no FROM gazette_summary)) "
            "ORDER BY published_date DESC", (1 if a.force else 0,)).fetchall()
    if a.subject:
        todo = [r for r in todo if con.execute(
            "SELECT subject FROM gazette WHERE no=?", (r["no"],)).fetchone()["subject"] in a.subject]
    if a.limit:
        todo = todo[:a.limit]
    if not todo:
        print("nothing to do"); return

    print(f"{len(todo)} gazettes -> {a.model}\n")
    tin = tout = done = failed = 0
    for r in todo:
        try:
            row = structure.summarise(con, r["no"], model=a.model)
        except Exception as e:
            failed += 1
            print(f"  FAIL {r['no']}: {type(e).__name__}: {e}")
            continue
        done += 1
        tin += row["input_tokens"] or 0
        tout += row["output_tokens"] or 0
        print(f"  ok {r['no']:>9}  [{row['confidence']}]  {row['summary'][:74]}")
    # gpt-5.6-luna list price; keeps the running total honest and visible
    cost = tin / 1e6 * 0.20 + tout / 1e6 * 1.20
    print(f"\nsummarised {done}, failed {failed}")
    print(f"tokens {tin:,} in / {tout:,} out   approx ${cost:.4f} at gpt-5.6-luna list price")


def cmd_batch(a):
    con = db.connect(a.db)
    if a.action == "submit":
        nos = [r["no"] for r in con.execute(
            "SELECT no FROM gazette WHERE (? OR no NOT IN (SELECT no FROM gazette_summary)) "
            "ORDER BY published_date DESC", (1 if a.force else 0,))]
        if a.limit:
            nos = nos[:a.limit]
        if not nos:
            print("nothing pending"); return
        if a.dry_run:
            body = structure._request_body(con, nos[0], a.model)
            print(f"would submit {len(nos)} requests to /v1/responses as {a.model}")
            print(f"first custom_id : {nos[0].replace('/', '-')}")
            print(f"prompt chars    : {len(body['input'][0]['content']):,}")
            print(f"schema fields   : {list(body['text']['format']['schema']['properties'])}")
            print("\n(dry run — nothing submitted, nothing spent)")
            return
        bid = structure.submit_batch(con, nos, model=a.model)
        print(f"submitted {len(nos)} requests as batch {bid}")
        print(f"poll with: python3 -m vidhana batch status {bid}")
        return

    bid = a.id or (con.execute(
        "SELECT id FROM batch_job ORDER BY submitted_at DESC LIMIT 1").fetchone() or {})
    bid = bid if isinstance(bid, str) else (bid["id"] if bid else None)
    if not bid:
        sys.exit("no batch job recorded — submit one first")

    if a.action == "status":
        st = structure.poll_batch(con, bid)
        print(f"{st['id']}  {st['status']}")
        if st["total"]:
            print(f"  {st['completed']}/{st['total']} completed, {st['failed']} failed")
    else:
        r = structure.collect_batch(con, bid)
        if r["status"] != "completed":
            print(f"batch is {r['status']} — nothing to collect yet"); return
        print(f"collected {r['collected']}, failed {r['failed']}")


def cmd_validate(a):
    con = db.connect(a.db)
    res = structure.check(con)
    n = con.execute("SELECT COUNT(*) c FROM gazette_summary").fetchone()["c"]
    if not n:
        sys.exit("no summaries yet — run `vidhana structure` first")
    print(f"grading {n} summaries\n")
    print("  three fields Phase 1 also derives by rule, plus whether the model stayed")
    print("  inside the audience candidates its Act allows\n")
    for field, (ok, tot) in res.items():
        pct = f"{100*ok//tot}%" if tot else "n/a"
        print(f"  {field:<18} {ok:>3}/{tot:<3} agree  ({pct})")
    dis = con.execute(
        "SELECT no, field, deterministic, model_value FROM summary_check "
        "WHERE agrees=0 ORDER BY field, no").fetchall()
    if dis:
        print(f"\ndisagreements ({len(dis)}) — the model is not necessarily the wrong one:")
        for d in dis:
            print(f"  {d['no']:>9}  {d['field']:<15} phase1={str(d['deterministic'])[:34]!r}  "
                  f"model={str(d['model_value'])[:34]!r}")


def _search_filters(a):
    return dict(subject=a.subject, tag=a.tag, audience=a.audience, act=a.act,
                since=a.since, until=a.until, in_force=a.in_force, as_of=a.as_of)


def cmd_search(a):
    con = db.connect(a.db)
    if a.rules:
        return _print_rules(con, a)
    rows = search.search(con, a.query, a.limit, **_search_filters(a))
    if not rows:
        print("no matches"); return
    for r in rows:
        print(f"\n{r['no']:>9}  {r['published_date']}  [{r['subject']}]  {r['standing']}")
        print(f"  {r['title'][:96]}")
        if r["summary"]:
            print(f"  {r['summary'][:150]}")
        if r["snip"]:
            print(f"  {r['snip']}")


def _print_rules(con, a):
    """One result per rule: the current document as the answer, the documents
    that produced it as the history."""
    out = search.rules(con, a.query, a.limit, **_search_filters(a))
    if not out:
        print("no matches"); return
    for t in out:
        c = t["current"]
        print(f"\n[{t['subject']}]  {t['size']} document(s) in this rule")
        print(f"  current: {c['no']}  {c['published_date']}"
              f"  effective {c['effective_from']}")
        print(f"  {(c['summary'] or c['title'])[:150]}")
        others = [m for m in t["matches"] if m["no"] != c["no"]]
        if others:
            print("  matched earlier in this rule: "
                  + ", ".join(f"{m['no']} ({m['published_date'][:4]})" for m in others))


def cmd_reindex(a):
    con = db.connect(a.db)
    db.init(con)
    r = search.reindex(con)
    if r["rebuilt"]:
        print("full-text index columns changed — index was rebuilt from scratch")
    print(f"indexed {r['indexed']} documents, {r['tags']} tags, {r['audiences']} audiences")
    if r["ungrounded"] or r["no_map"]:
        print(f"  {r['ungrounded']} audience string(s) did not ground on their Act's map"
              f"{f', {r["no_map"]} had no map' if r['no_map'] else ''}")


def cmd_facets(a):
    con = db.connect(a.db)
    f = search.facets(con, a.min_uses)
    for name in ("subject", "audience", "status", "tag"):
        rows = f[name]
        extra = (f" (used {a.min_uses}+ times; rarer tags still filter and search)"
                 if name == "tag" else "")
        print(f"\n{name}{extra}")
        for r in rows:
            print(f"  {r['n']:>4}  {r['name']}")


def cmd_whatsnew(a):
    con = db.connect(a.db)
    n = alerts.record(con)
    rows = alerts.whatsnew(con, since=a.since, subject=a.subject, kind=a.kind,
                           limit=a.limit)
    if not rows:
        print("nothing" + (f" since {a.since}" if a.since else "")); return
    if n["new"]:
        print(f"{n['new']} event(s) seen for the first time on this run\n")
    for e in rows:
        print(f"{e['event_date']}  {alerts.KIND_LABEL[e['kind']]:<22} {e['headline'][:76]}")
        if e["head_no"] and e["head_no"] != e["no"]:
            print(f"{'':>12}  the rule is now {e['head_no']} ({e['head_date']})")
        if e["audience"]:
            print(f"{'':>12}  affects: {'; '.join(e['audience'][:3])}")
    print(f"\n{len(rows)} event(s); {n['total']} in the corpus")


def cmd_feed(a):
    con = db.connect(a.db)
    alerts.record(con)
    for w in alerts.write_feeds(con, out_dir=a.out, base_url=a.base_url, limit=a.limit):
        state = "written" if w["changed"] else "unchanged"
        print(f"  {w['name']:<15} {w['entries']:>3} entries  {state:<9} {w['path']}")


def cmd_summaries(a):
    con = db.connect(a.db)
    db.init(con)
    if a.action == "export":
        n = structure.export_summaries(con, a.path)
        print(f"exported {n} summaries to {a.path}")
    else:
        r = structure.import_summaries(con, a.path, overwrite=a.overwrite)
        print(f"loaded {r['loaded']}, already present {r['skipped']}, "
              f"not in this corpus {r['unknown']}")


def cmd_verify(a):
    """Report what the corpus is missing, and how much of the graph it weakens."""
    con = db.connect(a.db)
    miss = archive.missing(con)
    inr = [m for m in miss if m["in_range"]]
    held = con.execute("SELECT source, COUNT(*) c FROM gazette GROUP BY source").fetchall()
    print("corpus")
    for r in held:
        print(f"  {r['c']:>4}  {r['source']}")
    print(f"\nreferenced but not held: {len(miss)} "
          f"({len(inr)} inside the listing's own range)")
    for m in sorted(miss, key=lambda r: (not r["in_range"], r["no"])):
        tag = "IN RANGE" if m["in_range"] else "pre-listing"
        print(f"  {m['no']:<9} {tag:<12} {m['relation']:<16} referenced by {m['referenced_by']}")

    rows = con.execute(
        "SELECT COUNT(*) c FROM gazette WHERE status='in_force' AND thread_id IN "
        "(SELECT thread_id FROM rule_thread WHERE unresolved>0)").fetchone()["c"]
    print(f"\n{rows} gazette(s) are reported in force inside a rule whose history "
          f"has a hole.\nSearch and the feed disclose this; it is not silently ignored.")
    if a.find:
        print("\nlooking for the in-range gaps in the Internet Archive:")
        for m in inr:
            try:
                hits = archive.find(m["no"])
            except archive.ArchiveUnavailable as e:
                print(f"  {m['no']:<9} lookup failed — {str(e)[:60]}")
                continue
            print(f"  {m['no']:<9} {len(hits)} snapshot(s)"
                  + (f"  {hits[0]['snapshot']}" if hits else ""))


def cmd_backfill(a):
    con = db.connect(a.db)
    todo = a.only or [m["no"] for m in archive.missing(con) if m["in_range"]]
    if not todo:
        print("nothing to backfill"); return
    for no in todo:
        try:
            r = archive.backfill(con, no, use_ocr=not a.no_ocr)
        except archive.ArchiveUnavailable as e:
            print(f"  {no:<9} lookup failed — {str(e)[:70]}")
            continue
        detail = r.get("detail") or r.get("act") or ""
        print(f"  {no:<9} {r['status']:<15} {detail}")
    print("\nrun `vidhana resolve && vidhana structure && vidhana reindex` to finish")


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
    sub.add_parser("resolve").set_defaults(fn=cmd_resolve)
    sub.add_parser("threads").set_defaults(fn=cmd_threads)

    r = sub.add_parser("rule")
    r.add_argument("no")
    r.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD",
                   help="what was operative on this date")
    r.set_defaults(fn=cmd_rule)

    s = sub.add_parser("show"); s.add_argument("no"); s.set_defaults(fn=cmd_show)
    c = sub.add_parser("chain"); c.add_argument("no"); c.set_defaults(fn=cmd_chain)

    st = sub.add_parser("structure")
    st.add_argument("--limit", type=int)
    st.add_argument("--force", action="store_true", help="re-summarise even if already done")
    st.add_argument("--subject", nargs="*")
    st.add_argument("--model", default=structure.DEFAULT_MODEL)
    st.add_argument("--only", nargs="*", metavar="NO",
                    help="summarise just these gazette numbers, e.g. 2481/22")
    st.set_defaults(fn=cmd_structure)

    sub.add_parser("validate").set_defaults(fn=cmd_validate)

    b = sub.add_parser("batch")
    b.add_argument("action", choices=["submit", "status", "collect"])
    b.add_argument("id", nargs="?", help="batch id; defaults to the most recent")
    b.add_argument("--limit", type=int)
    b.add_argument("--force", action="store_true")
    b.add_argument("--dry-run", action="store_true", help="build and inspect, submit nothing")
    b.add_argument("--model", default=structure.DEFAULT_MODEL)
    b.set_defaults(fn=cmd_batch)

    q = sub.add_parser("search")
    q.add_argument("query")
    q.add_argument("--limit", type=int, default=10)
    q.add_argument("--rules", action="store_true",
                   help="one result per rule, answered by its current document")
    q.add_argument("--subject", nargs="*", help="vat income-tax stamp-duty esc ...")
    q.add_argument("--tag", nargs="*", help="see `vidhana facets`")
    q.add_argument("--audience", nargs="*", help="see `vidhana facets`")
    q.add_argument("--act", help="substring of the enabling Act")
    q.add_argument("--since", metavar="YYYY-MM-DD")
    q.add_argument("--until", metavar="YYYY-MM-DD")
    q.add_argument("--in-force", dest="in_force", action="store_true",
                   help="drop what another gazette has rescinded")
    q.add_argument("--as-of", dest="as_of", metavar="YYYY-MM-DD",
                   help="what stood on this date, by effective date not publication")
    q.set_defaults(fn=cmd_search)

    sub.add_parser("reindex").set_defaults(fn=cmd_reindex)

    v = sub.add_parser("verify")
    v.add_argument("--find", action="store_true",
                   help="also ask the Internet Archive about the in-range gaps")
    v.set_defaults(fn=cmd_verify)

    bf = sub.add_parser("backfill")
    bf.add_argument("--only", nargs="*", metavar="NO")
    bf.add_argument("--no-ocr", dest="no_ocr", action="store_true")
    bf.set_defaults(fn=cmd_backfill)

    w = sub.add_parser("whatsnew")
    w.add_argument("--since", metavar="YYYY-MM-DD",
                   help="by gazette publication date, not when we detected it")
    w.add_argument("--subject", nargs="*")
    w.add_argument("--kind", nargs="*",
                   choices=["published", "amends", "rescinds", "effective_change"])
    w.add_argument("--limit", type=int, default=50)
    w.set_defaults(fn=cmd_whatsnew)

    sm = sub.add_parser("summaries")
    sm.add_argument("action", choices=["export", "import"])
    sm.add_argument("--path", default=structure.SUMMARY_EXPORT)
    sm.add_argument("--overwrite", action="store_true",
                    help="replace summaries already in the database")
    sm.set_defaults(fn=cmd_summaries)

    fd = sub.add_parser("feed")
    fd.add_argument("--out", default=alerts.FEED_DIR)
    fd.add_argument("--base-url", dest="base_url",
                    default="https://gedara-workshop.github.io/vidhana/feeds")
    fd.add_argument("--limit", type=int, default=alerts.FEED_LIMIT)
    fd.set_defaults(fn=cmd_feed)

    fc = sub.add_parser("facets")
    fc.add_argument("--min-uses", dest="min_uses", type=int, default=3)
    fc.set_defaults(fn=cmd_facets)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
