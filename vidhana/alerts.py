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


def _entry_title(e: dict) -> str:
    """A grouped entry says what the gazette *does*, so a reader can decide from
    the title alone whether to open it.

    Built as clauses rather than a list of labels: "rescinded and new gazette
    2463/05" reads as though 2463/05 were the new one, which is the opposite of
    what happened.
    """
    subject = f"[{e['subject']}] " if e["subject"] else ""
    acts = {}
    for kind, target, _ in e.get("acts_on", ()):
        acts.setdefault(kind, []).append(target)
    if not acts:
        return f"{e['no']} {subject}new: {e['title']}".strip()

    clauses = []
    for kind in ("rescinds", "amends"):
        if kind in acts:
            clauses.append(f"{kind} {', '.join(sorted(set(acts[kind])))}")
    if "effective_change" in acts:
        moved = sorted(set(acts["effective_change"]))
        # "amends 2481/22 and changes when it takes effect" — naming the same
        # gazette twice in one title is noise, so the pronoun is used when the
        # effective-date change lands on a gazette already named.
        named = {t for ts in (acts.get("rescinds", []), acts.get("amends", [])) for t in ts}
        subj = "it" if clauses and set(moved) <= named else ", ".join(moved)
        clauses.append(f"changes when {subj} takes effect")
    return f"{e['no']} {subject}{' and '.join(clauses)}".strip()


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


# ---------------------------------------------------------------------------
# Atom 1.0. Written by hand rather than with a library: the feed is four
# elements deep, the project has no dependencies, and xml.etree gives correct
# escaping without adding one.
# ---------------------------------------------------------------------------

FEED_TITLE = "Vidhana — Sri Lankan IRD tax and VAT gazettes"
FEED_HOME = "https://github.com/gedara-workshop/vidhana"
LISTING_URL = ("https://www.ird.gov.lk/en/publications/sitepages/"
               "gazette.aspx?menuid=1602")


# Most significant first. A gazette that moves another's effective date is the
# thing to say about it; that it also exists is not.
KIND_RANK = ("effective_change", "rescinds", "amends", "published")


def group(events: list[dict]) -> list[dict]:
    """One feed entry per gazette, not one per event.

    2500/106 raises three events — it is new, it amends 2481/22, and it moves
    that gazette's effective date. They are three facts about one document, and
    a feed reader would show them as three notifications with near-identical
    text. So the feed groups them and the entry says everything the gazette
    does; `whatsnew` keeps them separate, because there the granularity is the
    point.
    """
    by_no: dict[str, dict] = {}
    for e in events:
        g = by_no.get(e["no"])
        if g is None:
            g = by_no[e["no"]] = dict(e, kinds=[], acts_on=[])
        g["kinds"].append(e["kind"])
        if e["target_no"]:
            g["acts_on"].append((e["kind"], e["target_no"], e["target_title"]))
    out = []
    for g in by_no.values():
        g["kinds"] = sorted(set(g["kinds"]), key=KIND_RANK.index)
        g["kind"] = g["kinds"][0]
        g["headline"] = _headline(g)
        out.append(g)
    out.sort(key=lambda g: (g["event_date"], g["no"]), reverse=True)
    return out


def _entry_body(e: dict) -> str:
    """The entry text. Plain prose, because a feed reader shows it as-is and a
    reader who gets an alert should not have to open a PDF to learn whether it
    concerns them."""
    lines = []
    if e["summary"]:
        lines.append(e["summary"])
    for kind, target, target_title in dict.fromkeys(e.get("acts_on", ())):
        if kind == "effective_change":
            lines.append(f"This changes when {target} takes effect. "
                         f"Check the date before acting on {target} itself.")
        else:
            verb = "Amends" if kind == "amends" else "Rescinds"
            tgt = f"{verb} {target}"
            if target_title:
                tgt += f" — {target_title}"
            lines.append(tgt + ".")
    if e["head_no"] and e["head_no"] != e["no"]:
        lines.append(f"The current document in this rule is now {e['head_no']} "
                     f"({e['head_date']}).")
    if e["effective_from"]:
        lines.append(f"Effective from {e['effective_from']}.")
    if e["audience"]:
        lines.append("Affects: " + "; ".join(e["audience"]) + ".")
    if e["confidence"] and e["confidence"] != "high":
        # Say so in the feed, not just in the database. A summary the model was
        # unsure of should not reach a reader looking as certain as one it was.
        lines.append(f"(Summary confidence: {e['confidence']}. "
                     f"The gazette itself is the source of truth.)")
    lines.append(f"Source: {e['url']}")
    return "\n\n".join(lines)


def atom(con, events: list[dict], *, feed_id: str, title: str,
         self_url: str | None = None, updated: str | None = None) -> str:
    from xml.etree import ElementTree as ET

    ns = "http://www.w3.org/2005/Atom"
    ET.register_namespace("", ns)
    feed = ET.Element(f"{{{ns}}}feed")

    def sub(parent, tag, text=None, **attrib):
        el = ET.SubElement(parent, f"{{{ns}}}{tag}", attrib)
        if text is not None:
            el.text = text
        return el

    sub(feed, "title", title)
    sub(feed, "id", feed_id)
    sub(feed, "link", href=FEED_HOME)
    if self_url:
        sub(feed, "link", href=self_url, rel="self")
    sub(feed, "subtitle",
        "What changed in the Sri Lankan Inland Revenue gazettes, and what the "
        "rule is now. Derived from " + LISTING_URL)
    # The feed's updated time is the newest event's, not now(). A nightly run
    # that finds nothing must not restamp the feed — clients treat that as
    # activity, and a quiet corpus should look quiet.
    sub(feed, "updated", updated or (
        _atom_time(events[0]["event_date"]) if events
        else _atom_time(dt.date.today().isoformat())))
    author = sub(feed, "author")
    sub(author, "name", "Vidhana")

    for e in events:
        entry = sub(feed, "entry")
        sub(entry, "title", _entry_title(e))
        sub(entry, "id", f"tag:vidhana,2026:gazette:{e['no']}")
        sub(entry, "link", href=e["url"])
        sub(entry, "updated", _atom_time(e["event_date"]))
        sub(entry, "published", _atom_time(e["event_date"]))
        if e["subject"]:
            sub(entry, "category", term=e["subject"])
        sub(entry, "content", _entry_body(e), type="text")

    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            + ET.tostring(feed, encoding="unicode") + "\n")


def _atom_time(date: str) -> str:
    """Atom wants an RFC 3339 timestamp; gazettes carry a date. Midnight UTC is
    the honest reading — a gazette is published on a day, not at an instant."""
    return f"{date}T00:00:00Z"


# Published feeds live under docs/ so GitHub Pages can serve them straight from
# the repo with no hosting decision attached. They are tracked in git, unlike the
# database — a feed's whole job is to be a stable URL with stable entry ids, and
# a derived artefact that must not change spuriously is exactly the kind that
# belongs in version control.
FEED_DIR = "docs/feeds"
FEED_LIMIT = 60


def write_feeds(con, out_dir: str = FEED_DIR, base_url: str | None = None,
                limit: int = FEED_LIMIT) -> list[dict]:
    """Write the main feed and one per subject.

    Per-subject feeds exist because the corpus is not one audience. Someone who
    cares about VAT should not be notified about 63 income-tax gazettes to catch
    32 VAT ones, and the subject is already classified deterministically, so the
    split costs a query rather than a judgement.
    """
    import os

    os.makedirs(out_dir, exist_ok=True)
    events = whatsnew(con, limit=limit * 4)
    subjects = sorted({e["subject"] for e in events if e["subject"]})

    written = []
    for name, subject in [("all", None)] + [(s, s) for s in subjects]:
        chosen = [e for e in events if subject is None or e["subject"] == subject]
        entries = group(chosen)[:limit]
        title = FEED_TITLE if subject is None else f"{FEED_TITLE} — {subject}"
        self_url = f"{base_url.rstrip('/')}/{name}.xml" if base_url else None
        path = os.path.join(out_dir, f"{name}.xml")
        xml = atom(con, entries, feed_id=f"tag:vidhana,2026:feed:{name}",
                   title=title, self_url=self_url)
        old = None
        if os.path.exists(path):
            with open(path) as f:
                old = f.read()
        if old != xml:
            with open(path, "w") as f:
                f.write(xml)
        written.append(dict(name=name, path=path, entries=len(entries),
                            changed=old != xml))
    return written
