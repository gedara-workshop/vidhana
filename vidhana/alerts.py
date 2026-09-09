"""Phase 4: what changed, and the feed that says so.

Events are derived from the corpus, never accumulated as it changes. Every kind
here is a fact about the data that is true whenever it is asked, which makes
derivation idempotent: a missed run loses nothing, a rebuilt database produces
the same events, and running the pipeline twice does not double-notify anyone.

What counts as news is the interesting question. A new gazette appearing is the
obvious event and the least useful one on its own — the reader cares that
something they already follow has changed under them. So a gazette that amends
or rescinds another raises an event against *both*, and the entry says what the
rule's current document is now.
"""
from __future__ import annotations

import datetime as dt

# `cites` is excluded deliberately: it is a reference to an unrelated instrument
# — a depreciation-rates gazette, say — and does not change the standing of
# anything. Alerting on it would bury the events that matter.
RELATIONS = ("amends", "rescinds")

KIND_LABEL = {
    "published": "new gazette",
    "amends": "amended",
    "rescinds": "rescinded",
    "effective_change": "effective date changed",
}


def derive(con) -> list[dict]:
    """Every event the corpus currently implies, newest first.

    Pure: reads, never writes. `record` is what persists first-seen times.
    """
    out: list[dict] = []

    for r in con.execute(
            "SELECT no, published_date, subject, title FROM gazette "
            "ORDER BY published_date DESC"):
        out.append(dict(event_id=f"published:{r['no']}:", kind="published",
                        no=r["no"], target_no=None, event_date=r["published_date"]))

    # Only edges whose target we actually hold. A dangling edge points at a
    # gazette the IRD listing does not carry (13 of them), so we cannot say what
    # it changed or what the rule now is — and an alert that cannot say either is
    # noise.
    for r in con.execute(
            "SELECT r.src_no, r.dst_no, r.relation, g.published_date "
            "FROM gazette_reference r "
            "JOIN gazette g ON g.no = r.src_no "
            "JOIN gazette t ON t.no = r.dst_no "
            f"WHERE r.relation IN ({','.join('?' * len(RELATIONS))}) "
            "ORDER BY g.published_date DESC", RELATIONS):
        out.append(dict(event_id=f"{r['relation']}:{r['src_no']}:{r['dst_no']}",
                        kind=r["relation"], no=r["src_no"], target_no=r["dst_no"],
                        event_date=r["published_date"]))

    # A gazette that moves another's effective date without otherwise amending
    # it. Rare — one in the corpus — and the single highest-value alert in it:
    # 2500/106 moved the tax invoice format from July to October 2026, and a
    # reader who acted on 2481/22 alone would have been three months early.
    for r in con.execute(
            "SELECT d.no, d.kind, g.published_date FROM gazette_date d "
            "JOIN gazette g ON g.no = d.no "
            "WHERE d.kind IN ('sets_effective_date', 'replaces_effective_date')"):
        for tgt in con.execute(
                "SELECT dst_no FROM gazette_reference WHERE src_no=? "
                "AND relation IN ('amends', 'rescinds')", (r["no"],)):
            out.append(dict(event_id=f"effective_change:{r['no']}:{tgt['dst_no']}",
                            kind="effective_change", no=r["no"],
                            target_no=tgt["dst_no"], event_date=r["published_date"]))

    seen, uniq = set(), []
    for e in out:
        if e["event_id"] not in seen:
            seen.add(e["event_id"])
            uniq.append(e)
    uniq.sort(key=lambda e: (e["event_date"], e["no"]), reverse=True)
    return uniq


def record(con, now: str | None = None) -> dict:
    """Persist first-seen times for derived events. Returns counts, and the
    events that were new on this run — which is exactly what a cron job needs to
    decide whether it has anything to say."""
    now = now or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    known = {r["event_id"] for r in con.execute("SELECT event_id FROM gazette_event")}
    events = derive(con)
    fresh = [e for e in events if e["event_id"] not in known]
    con.executemany(
        "INSERT OR IGNORE INTO gazette_event "
        "(event_id, kind, no, target_no, event_date, detected_at) VALUES (?,?,?,?,?,?)",
        [(e["event_id"], e["kind"], e["no"], e["target_no"], e["event_date"], now)
         for e in events])
    # An event can stop being derivable — a reference re-parsed away by a fix to
    # parse.py. Dropping it keeps the feed honest about what the corpus says now,
    # rather than leaving an entry no evidence supports.
    live = {e["event_id"] for e in events}
    stale = [k for k in known if k not in live]
    if stale:
        con.executemany("DELETE FROM gazette_event WHERE event_id=?",
                        [(k,) for k in stale])
    con.commit()
    return dict(total=len(events), new=len(fresh), dropped=len(stale), events=fresh)


def describe(con, event: dict) -> dict:
    """Turn an event into the thing a reader needs, in one place.

    Both `whatsnew` and the Atom feed render from this, so the terminal and the
    feed can never drift into saying different things about the same change.
    """
    g = con.execute(
        "SELECT g.no, g.published_date, g.title, g.subject, g.source_url, "
        "       g.effective_from, g.status, g.thread_id, "
        "       s.summary, s.obligation, s.confidence "
        "FROM gazette g LEFT JOIN gazette_summary s ON s.no = g.no "
        "WHERE g.no = ?", (event["no"],)).fetchone()
    d = dict(event, title=g["title"], subject=g["subject"], url=g["source_url"],
             summary=g["summary"], effective_from=g["effective_from"],
             obligation=g["obligation"], confidence=g["confidence"],
             # Distinct: several model strings routinely ground to one
             # candidate, and "VAT-registered businesses, VAT-registered
             # businesses" is not a more precise answer than one of them.
             audience=list(dict.fromkeys(
                 r["coarse"] or r["audience"] for r in con.execute(
                     "SELECT audience, coarse FROM gazette_audience WHERE no=?",
                     (event["no"],)))),
             target_title=None, head_no=None, head_date=None)

    if event["target_no"]:
        t = con.execute("SELECT title, published_date FROM gazette WHERE no=?",
                        (event["target_no"],)).fetchone()
        d["target_title"] = t["title"] if t else None

    # The current document of the affected rule. This is the line that makes an
    # alert actionable rather than merely informative: not "2481/22 changed" but
    # "the rule you follow is now 2500/106".
    if g["thread_id"]:
        h = con.execute(
            "SELECT t.head_no, g.published_date FROM rule_thread t "
            "JOIN gazette g ON g.no = t.head_no WHERE t.thread_id = ?",
            (g["thread_id"],)).fetchone()
        if h:
            d["head_no"], d["head_date"] = h["head_no"], h["published_date"]

    d["headline"] = _headline(d)
    return d


def _headline(d: dict) -> str:
    subject = f"[{d['subject']}]" if d["subject"] else ""
    if d["kind"] == "published":
        return f"{d['no']} {subject} {d['title']}".strip()
    if d["kind"] == "effective_change":
        return (f"{d['no']} {subject} changes when {d['target_no']} takes effect").strip()
    verb = "amends" if d["kind"] == "amends" else "rescinds"
    return f"{d['no']} {subject} {verb} {d['target_no']}".strip()


def whatsnew(con, since: str | None = None, subject=None, kind=None,
             limit: int = 50) -> list[dict]:
    """Events, newest first, described. `since` filters on the gazette's
    publication date rather than on when we detected it — a reader asking what
    changed since January means changes to the law, not changes to our database.
    """
    sql = ("SELECT e.* FROM gazette_event e JOIN gazette g ON g.no = e.no WHERE 1=1")
    params: list = []
    if since:
        sql += " AND e.event_date >= ?"; params.append(since)
    if subject:
        sql += f" AND g.subject IN ({','.join('?' * len(subject))})"; params += list(subject)
    if kind:
        sql += f" AND e.kind IN ({','.join('?' * len(kind))})"; params += list(kind)
    sql += " ORDER BY e.event_date DESC, e.no DESC, e.kind LIMIT ?"
    params.append(limit)
    return [describe(con, dict(r)) for r in con.execute(sql, params)]
