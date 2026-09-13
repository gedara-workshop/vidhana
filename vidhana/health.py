"""What the corpus knows about its own condition.

The third of the three pieces that stand in for an admin UI, and the one that
faces outward. Validation scores, parse warnings, documents that needed OCR,
gazettes referenced but not held, and when the corpus was last rebuilt — as a
page anyone can read, not a dashboard behind a login.

Publishing this is the point rather than a side effect. The site asks people to
act on what it says about the law; the least it can do is show its own error
rate, name the document it knows is missing, and say when it last checked. A
number that only its author sees is a number nobody audits.

Read-only: `structure.grade` is used instead of `structure.check`, so building
the page never writes to the database.

**No timestamp in here.** The report is committed with the rest of docs/data,
and a "generated at" field would differ on every run, so the nightly job would
commit every night — which is precisely what it must not do, since the history
is a record of the law changing and not of the workflow running. When the page
was built is stamped into the page at build time instead, where it costs no
commit.
"""
from __future__ import annotations

from . import answers, corrections, structure


def report(con) -> dict:
    """Everything the health page shows. Pure: reads, writes nothing."""
    g = con.execute(
        "SELECT COUNT(*) n, "
        "       SUM(source = 'ird-listing') listed, "
        "       SUM(source != 'ird-listing') recovered, "
        "       SUM(status = 'rescinded') rescinded, "
        "       MIN(published_date) first, MAX(published_date) last FROM gazette").fetchone()
    threads = con.execute(
        "SELECT COUNT(*) n, SUM(unresolved > 0) holed FROM rule_thread").fetchone()

    rows = structure.grade(con)
    scored = structure.scores(rows)

    # Referenced but not held, split the way COMPLETENESS.md splits them: inside
    # the listing's range is a defect in the source, before it is expected.
    span = con.execute(
        "SELECT MIN(CAST(substr(no,1,instr(no,'/')-1) AS INT)) lo, "
        "       MAX(CAST(substr(no,1,instr(no,'/')-1) AS INT)) hi FROM gazette").fetchone()
    missing_in, missing_before = [], []
    for r in con.execute(
            "SELECT DISTINCT dst_no FROM gazette_reference WHERE dst_no NOT IN "
            "(SELECT no FROM gazette) ORDER BY dst_no"):
        n = int(r["dst_no"].split("/")[0])
        (missing_in if span["lo"] <= n <= span["hi"] else missing_before).append(r["dst_no"])

    return dict(
        corpus=dict(gazettes=g["n"], listed=g["listed"] or 0, recovered=g["recovered"] or 0,
                    rescinded=g["rescinded"] or 0, rules=threads["n"],
                    rules_with_holes=threads["holed"] or 0,
                    first=g["first"], last=g["last"]),
        validation=dict(
            fields=[dict(field=f, agreed=a, compared=c) for f, (a, c) in scored.items()],
            disagreements=[dict(no=r["no"], field=r["field"],
                                derived=str(r["deterministic"] or "")[:120],
                                model=str(r["model_value"] or "")[:120])
                           for r in rows if not r["agrees"]],
            reviewed=len(corrections.load()),
        ),
        confidence={r["confidence"] or "unrated": r["n"] for r in con.execute(
            "SELECT confidence, COUNT(*) n FROM gazette_summary GROUP BY confidence")},
        parse_warnings=[dict(no=r["no"], warnings=r["parse_warnings"].strip().splitlines())
                        for r in con.execute(
                            "SELECT no, parse_warnings FROM gazette "
                            "WHERE parse_warnings IS NOT NULL AND parse_warnings != '' "
                            "ORDER BY no")],
        needs_ocr=[dict(no=r["no"], pages=r["pages"]) for r in con.execute(
            "SELECT g.no, COUNT(p.page) pages FROM gazette g "
            "JOIN gazette_page p ON p.no = g.no AND p.needs_ocr = 1 "
            "GROUP BY g.no ORDER BY g.no")],
        missing=dict(in_range=missing_in, before_listing=len(missing_before)),
        answers={k: sum(1 for r in answers.status(con) if r["state"] == k)
                 for k in ("current", "stale", "failing", "missing")},
    )
