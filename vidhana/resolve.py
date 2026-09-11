"""Resolve the amendment graph into rule threads and in-force state.

Phase 0 found that roughly half the corpus amends or rescinds another gazette,
and that the current state of a rule frequently exists in no single document.
This module turns the edge list into the thing a reader actually wants: for a
given rule, which documents define it, which are still standing, and which one
is current.

What it does NOT do, and cannot do deterministically: produce the merged text of
an amended rule. "Substitute paragraph (i) of item (2) of the Schedule" is a
textual operation on a document we only have as a PDF. This module reports which
documents are operative and how they relate; reconstructing the consolidated text
is a separate problem and probably an LLM one.

"In force" here means "not rescinded by another document in our data". That is
weaker than a legal determination — the corpus has 13 edges pointing at gazettes
the IRD listing does not carry, so a rescission we cannot see would not show up.
Threads carrying such edges are marked `unresolved`.
"""
from __future__ import annotations

import collections

# Only these relations bind documents into one rule. A plain `cites` is a
# reference to an unrelated instrument (a depreciation-rates gazette, say) and
# must not merge two threads that have nothing to do with each other.
THREAD_RELATIONS = ("amends", "rescinds", "last_amended_by")


def _issue_order(no: str) -> tuple[int, ...]:
    """A gazette number as a sortable tuple: `1441/17` -> (1441, 17).

    The tie-break for documents published on the same day. The IRD issues in
    batches (1439/01 and 1439/02, 1441/17 and 1441/18), and on one day the
    number is the order of issue. Without it, ordering falls back to iterating
    a set of strings, which Python randomises per process: the same corpus
    gave three different roots and two different current documents across
    eight hash seeds. Numeric, so that `1441/9` sorts before `1441/10`.
    """
    return tuple(int(p) if p.isdigit() else 0 for p in no.split("/"))


def _components(edges: list[tuple[str, str]], known: set[str]) -> list[set[str]]:
    """Connected components over the threading relations, restricted to gazettes
    we actually hold. Dangling targets are counted separately, not merged in."""
    adj: dict[str, set[str]] = collections.defaultdict(set)
    for a, b in edges:
        if a in known and b in known:
            adj[a].add(b)
            adj[b].add(a)
    seen: set[str] = set()
    out: list[set[str]] = []
    for node in adj:
        if node in seen:
            continue
        stack, comp = [node], set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            seen.add(cur)
            stack.extend(adj[cur] - comp)
        out.append(comp)
    return out


def stated_effective(con, no: str) -> str | None:
    """The effective date the document itself states, or None.

    A date in the operative clause — "I, <name>, do by this Order ... with
    effect from" — wins, because that clause is the document's own act. Only
    without one does the earliest `effective` date stand in: effective dates
    are frequently retroactive (2316/13 published Jan 2023, effective Oct
    2022), but "earliest" alone also picked up dates belonging to schedules,
    transitional provisions and other instruments reproduced in full, and
    reported a December 2012 gazette as effective from 2003.
    """
    by = {r["kind"]: r["d"] for r in con.execute(
        "SELECT kind, MIN(date) d FROM gazette_date "
        "WHERE no=? AND kind IN ('operative', 'effective') GROUP BY kind", (no,))}
    return by.get("operative") or by.get("effective")


def effective_from(con, no: str, published: str) -> str:
    """Best single effective date for a document.

    What the document states if anything (`stated_effective`), else the
    publication date. Deliberately visible: the fallback to publication is a
    floor, not a truth, and `gazette_date` keeps every candidate with the clause
    it came from.
    """
    return stated_effective(con, no) or published


def _rescission_date(con, src: str, published: str) -> str:
    """When a rescission bites. 2481/22 rescinds 2463/05 only from 01 Jul 2026,
    months after publication, so there is a window where both stand."""
    row = con.execute(
        "SELECT MIN(date) d FROM gazette_date WHERE no=? AND kind='rescind_effective'",
        (src,)).fetchone()
    return row["d"] or effective_from(con, src, published)


def resolve(con) -> dict:
    """Recompute threads and status for the whole corpus. Idempotent."""
    con.execute("UPDATE gazette SET thread_id=NULL, status=NULL, rescinded_by=NULL, "
                "rescinded_from=NULL, effective_from=NULL")
    con.execute("DELETE FROM rule_thread")

    gazettes = {r["no"]: r for r in con.execute(
        "SELECT no, published_date, subject, enabling_act, title FROM gazette")}
    known = set(gazettes)

    for no, g in gazettes.items():
        con.execute("UPDATE gazette SET effective_from=? WHERE no=?",
                    (effective_from(con, no, g["published_date"]), no))

    # Propagate a metadata-only amendment onto its target. 2500/106 does nothing
    # but move 2481/22's effective date from July to October; after this, asking
    # 2481/22 when it bites gives October, which is the answer a reader needs and
    # which appears in neither document on its own.
    for r in con.execute(
            "SELECT ref.src_no, ref.dst_no, d.date FROM gazette_reference ref "
            "JOIN gazette_date d ON d.no = ref.src_no AND d.kind = 'sets_effective_date' "
            "WHERE ref.relation = 'amends'"):
        if r["dst_no"] in known:
            con.execute("UPDATE gazette SET effective_from=? WHERE no=?",
                        (r["date"], r["dst_no"]))

    # Rescissions. A document is rescinded if anything we hold rescinds it.
    for r in con.execute(
            "SELECT src_no, dst_no FROM gazette_reference WHERE relation='rescinds'"):
        if r["dst_no"] not in known or r["src_no"] not in known:
            continue
        when = _rescission_date(con, r["src_no"], gazettes[r["src_no"]]["published_date"])
        con.execute(
            "UPDATE gazette SET status='rescinded', rescinded_by=?, rescinded_from=? "
            "WHERE no=?", (r["src_no"], when, r["dst_no"]))

    # A date-moving amendment moves the date everywhere the target uses it.
    # 2500/106: 'The effective date of "July 01, 2026", is hereby amended as
    # "October 01, 2026"'. 2481/22 uses that date twice — for its own start
    # and for rescinding the 2025 format ("rescinded with effect from July 01,
    # 2026"). Moving only the first left a quarter in which no invoice format
    # was in force at all: asked what applied on 1 August 2026, search
    # answered nothing. The substitution is literal — only a rescission dated
    # exactly the replaced date moves — so nothing is interpreted.
    for r in con.execute(
            "SELECT ref.dst_no, s.date AS moved_to, x.date AS moved_from "
            "FROM gazette_reference ref "
            "JOIN gazette_date s ON s.no = ref.src_no AND s.kind = 'sets_effective_date' "
            "JOIN gazette_date x ON x.no = ref.src_no AND x.kind = 'replaces_effective_date' "
            "WHERE ref.relation = 'amends'"):
        con.execute("UPDATE gazette SET rescinded_from=? WHERE rescinded_by=? AND rescinded_from=?",
                    (r["moved_to"], r["dst_no"], r["moved_from"]))

    edges = [(r["src_no"], r["dst_no"]) for r in con.execute(
        f"SELECT src_no, dst_no FROM gazette_reference "
        f"WHERE relation IN ({','.join('?' * len(THREAD_RELATIONS))})", THREAD_RELATIONS)]
    dangling = collections.Counter(
        b for a, b in edges if a in known and b not in known)

    threads = 0
    for comp in sorted(_components(edges, known), key=lambda c: min(c)):
        rows = sorted(comp, key=lambda n: (gazettes[n]["published_date"], _issue_order(n)))
        threads += 1
        tid = threads
        standing = [n for n in rows if con.execute(
            "SELECT status FROM gazette WHERE no=?", (n,)).fetchone()["status"] != "rescinded"]
        head = standing[-1] if standing else rows[-1]
        subj = collections.Counter(gazettes[n]["subject"] for n in rows).most_common(1)[0][0]
        act = next((gazettes[n]["enabling_act"] for n in reversed(rows)
                    if gazettes[n]["enabling_act"]), None)
        label = f"{act or subj} — {gazettes[rows[0]]['title'][:70]}"
        unresolved = sum(dangling[b] for a, b in edges if a in comp for b in [b]
                         if b not in known)
        con.execute(
            "INSERT INTO rule_thread (thread_id, label, subject, enabling_act, root_no, "
            "head_no, first_date, last_date, size, unresolved) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tid, label, subj, act, rows[0], head,
             gazettes[rows[0]]["published_date"], gazettes[rows[-1]]["published_date"],
             len(rows), unresolved))
        for n in rows:
            con.execute("UPDATE gazette SET thread_id=? WHERE no=?", (tid, n))

    con.execute("UPDATE gazette SET status='in_force' "
                "WHERE status IS NULL AND thread_id IS NOT NULL")
    con.execute("UPDATE gazette SET status='standalone' WHERE status IS NULL")
    con.commit()

    q = lambda s: con.execute(s).fetchone()[0]
    return dict(threads=threads,
                threaded=q("SELECT COUNT(*) FROM gazette WHERE thread_id IS NOT NULL"),
                standalone=q("SELECT COUNT(*) FROM gazette WHERE status='standalone'"),
                rescinded=q("SELECT COUNT(*) FROM gazette WHERE status='rescinded'"))


def operative_on(con, thread_id: int, when: str) -> list[dict]:
    """Which documents in a thread are operative on a given date.

    A document counts if it had taken effect by `when` and had not been rescinded
    by then. Both halves matter: 2481/22 was published in March 2026 but takes
    effect in October, and 2463/05 stayed standing until July.
    """
    rows = con.execute(
        "SELECT no, published_date, effective_from, status, rescinded_by, rescinded_from, "
        "title FROM gazette WHERE thread_id=? ORDER BY effective_from", (thread_id,)).fetchall()
    out = []
    for r in rows:
        if (r["effective_from"] or r["published_date"]) > when:
            continue
        if r["rescinded_from"] and r["rescinded_from"] <= when:
            continue
        out.append(dict(r))
    return out
