"""Phase 3: search across the corpus, answering with resolved state.

The point of this module is the difference between two questions:

    "which documents mention the tax invoice format?"      — plain full-text
    "what is the rule on tax invoice formats right now?"   — what a reader wants

Everything here is deterministic. The resolver (`resolve.py`) already knows
which documents are in force; search's job is to carry that state into the
result rather than returning a list of PDFs and leaving the reader to work out
which of them still stands. No LLM runs at query time.

Facets are derived, not stored as the model wrote them. Measured over the
corpus: 225 of 319 distinct tags are used exactly once and 95 of 105 audience
strings are unique, so the model's own strings describe a document well and
navigate it badly. Tags are folded to a key and given a display form; audience
is grounded back to the enabling Act's candidate list.
"""
from __future__ import annotations

import collections
import json

from .structure import audience_candidates

# True synonyms only. Mechanical plural folding (below) already merges
# tax-rate/tax-rates and tax-exemption/tax-exemptions, so this map is for pairs
# no rule can catch: an abbreviation, a differently-inflected stem, two names
# for one thing. Kept deliberately short — over-merging tags destroys the
# distinctions the model got right.
TAG_ALIAS = {
    "vat": "value-added-tax",
    "debit-tax": "debits-tax",
    "excise": "excise-tax",
    "withholding": "withholding-tax",
    "tax-invoicing": "tax-invoices",
    "importation": "imports",
    "casino-regulation": "casino-licensing",
    "port-city": "colombo-port-city",
    "svat-transition": "svat",
    "amendment": "gazette-amendment",
    "gazette-correction": "gazette-amendment",
    "freight-forwarding": "freight-forwarders",
}


def _depluralise(word: str) -> str:
    """Fold an English plural to its stem. Only ever applied to the final token
    of a tag, where the head noun sits: `tax-rates` -> `tax-rate`, but
    `debits-tax` is left alone because its plural is not at the end."""
    if len(word) < 4 or word.endswith("ss"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def tag_key(raw: str) -> str:
    """Fold a model-written tag to a canonical key.

    The key is for grouping, not display — `notaries` and `notary` both key to
    `notary`, which reads oddly in a facet list. `canonical_tags` picks the form
    a human sees.
    """
    t = "-".join(raw.strip().lower().split())
    t = t.strip("-")
    t = TAG_ALIAS.get(t, t)
    if not t:
        return ""
    parts = t.split("-")
    parts[-1] = _depluralise(parts[-1])
    key = "-".join(parts)
    return TAG_ALIAS.get(key, key)


def canonical_tags(raws: list[str]) -> dict[str, str]:
    """key -> the display form for that key, over a whole corpus of raw tags.

    The winner is the most-used raw variant, ties broken alphabetically so the
    result does not depend on row order. This is why facets are rebuilt
    wholesale rather than per document: the display form is a corpus-level fact.
    """
    groups: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for raw in raws:
        key = tag_key(raw)
        if key:
            groups[key]["-".join(raw.strip().lower().split())] += 1
    return {key: min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0] for key, c in groups.items()}


def _words(s: str) -> list[str]:
    return [w for w in "".join(c if c.isalnum() else " " for c in s.lower()).split()]


def ground_audience(act: str | None, audience: str, subject: str | None = None):
    """Match one model-written audience string back to its Act's candidate list.

    CLAUDE.md: the audience is not in the documents. It is inferred from the
    enabling Act, and the model may only narrow within the Act's candidates,
    never invent one. This is where that rule is checked rather than merely
    asked for.

    Returns `(coarse, reason)`. Three outcomes, and they mean different things:

        ("VAT-registered businesses", "grounded")  narrowed within the map
        (None, "no-map")                           the Act has no map to obey
        (None, "ungrounded")                       it had a map and left it

    Only the third is a finding about the model. Collapsing the first two into
    "not grounded" would report a gap in our curation as a model failure.
    """
    candidates = audience_candidates((act or "").replace("The ", ""), subject)
    if not candidates:
        return None, "no-map"
    if not audience:
        return None, "ungrounded"
    got = {_depluralise(w) for w in _words(audience)}
    best, best_hit, best_score = None, 0, 0.0
    for cand in candidates:
        want = [_depluralise(w) for w in _words(cand) if len(w) > 3]
        if not want:
            continue
        hit = sum(w in got for w in want)
        score = hit / len(want)
        if (hit, score) > (best_hit, best_score):
            best, best_hit, best_score = cand, hit, score
    # Two ways to ground, because the candidates are not the same shape. Short
    # ones are noun phrases and want a ratio: "VAT-registered wholesalers and
    # retailers" keeps one word of two from "VAT-registered businesses" and is
    # plainly a narrowing. Long ones enumerate — "parties to leases, transfers
    # and other stampable instruments" — and a narrowing keeps one branch of the
    # list and drops the rest, so demanding half the words would reject exactly
    # the documents that obeyed the instruction. Two distinctive words is the
    # floor for those.
    if best_score >= 0.5 or best_hit >= 2:
        return best, "grounded"
    return None, "ungrounded"


def reindex(con) -> dict:
    """Rebuild the search index and both facet tables from what is already stored.

    Reads the text from disk and the summaries from gazette_summary — no network
    call, no model call, nothing to pay for. Wholesale rather than incremental
    because the canonical tag display form is a corpus-level fact: adding one
    document can change how an existing tag is spelled in the facet list.
    """
    from . import db

    rebuilt = db.migrate_fts(con)
    rows = con.execute(
        "SELECT g.no, g.title, g.text_path, g.enabling_act, g.subject, "
        "       s.summary, s.tags, s.audience "
        "FROM gazette g LEFT JOIN gazette_summary s ON s.no = g.no").fetchall()

    raws = [t for r in rows for t in json.loads(r["tags"] or "[]")]
    canon = canonical_tags(raws)

    out = dict(rebuilt=rebuilt, indexed=0, tags=0, audiences=0, ungrounded=0, no_map=0)
    for r in rows:
        body = ""
        if r["text_path"]:
            try:
                body = open(r["text_path"]).read()
            except OSError:
                body = ""            # PDFs are gitignored; a fresh clone has no text yet
        db.index_fts(con, r["no"], r["title"], body, r["summary"])
        out["indexed"] += 1

        con.execute("DELETE FROM gazette_tag WHERE no=?", (r["no"],))
        seen = set()
        for raw in json.loads(r["tags"] or "[]"):
            key = tag_key(raw)
            if not key or key in seen:
                continue
            seen.add(key)
            con.execute("INSERT INTO gazette_tag (no, tag, raw) VALUES (?,?,?)",
                        (r["no"], canon.get(key, key), raw))
            out["tags"] += 1

        con.execute("DELETE FROM gazette_audience WHERE no=?", (r["no"],))
        for aud in json.loads(r["audience"] or "[]"):
            coarse, why = ground_audience(r["enabling_act"], aud, r["subject"])
            con.execute(
                "INSERT OR IGNORE INTO gazette_audience (no, audience, coarse) VALUES (?,?,?)",
                (r["no"], aud, coarse))
            out["audiences"] += 1
            if why != "grounded":
                out["ungrounded" if why == "ungrounded" else "no_map"] += 1
    con.commit()
    return out


# bm25 weights, one per fts5 column including the UNINDEXED key. The title is
# the listing description, which is short and often the most direct statement of
# what a gazette does — but 34 of 137 are too terse to classify from, so it
# cannot dominate. The summary is plain English written to be read. The body is
# statutory prose where a hit is as likely to be boilerplate as substance, so it
# is weighted lowest while still being the reason full-text search exists.
WEIGHTS = (0.0, 6.0, 4.0, 1.0)

_SELECT = """
SELECT g.no, g.published_date, g.title, g.subject, g.enabling_act,
       g.status, g.rescinded_by, g.rescinded_from, g.effective_from,
       g.thread_id, s.summary, s.confidence,
       t.head_no, t.size AS thread_size,
       bm25(gazette_fts, {w}) AS score,
       snippet(gazette_fts, 3, '[', ']', ' … ', 14) AS snip
FROM gazette_fts f
JOIN gazette g       ON g.no = f.no
LEFT JOIN gazette_summary s ON s.no = g.no
LEFT JOIN rule_thread t     ON t.thread_id = g.thread_id
WHERE gazette_fts MATCH ?
"""


def _filters(subject=None, tag=None, audience=None, act=None,
             since=None, until=None, in_force=False, as_of=None):
    """Build the WHERE fragments and their parameters, in order.

    Subject, tag and audience narrow by facet; since/until bound the
    publication date. The two state filters are different in kind and are worth
    keeping apart:

        in_force   drop what another document in the corpus has rescinded
        as_of      what stood on a given day — the thing a reader needs when
                   asking about a return they filed two years ago

    `as_of` is not just `published <= date`. A gazette published in January
    2023 can take effect in October 2022 (2316/13 does exactly that), so the
    test is on effective_from, and a rescission that had not yet bitten on that
    date must not remove the document.
    """
    where, params = [], []
    if subject:
        where.append(f"g.subject IN ({','.join('?' * len(subject))})")
        params += list(subject)
    if act:
        where.append("LOWER(g.enabling_act) LIKE ?")
        params.append(f"%{act.lower()}%")
    for col, table, vals in (("tag", "gazette_tag", tag),
                             ("coarse", "gazette_audience", audience)):
        if vals:
            where.append(f"g.no IN (SELECT no FROM {table} WHERE {col} IN "
                         f"({','.join('?' * len(vals))}))")
            params += list(vals)
    if since:
        where.append("g.published_date >= ?"); params.append(since)
    if until:
        where.append("g.published_date <= ?"); params.append(until)
    if in_force:
        where.append("(g.status IS NULL OR g.status != 'rescinded')")
    if as_of:
        where.append("g.effective_from IS NOT NULL AND g.effective_from <= ?")
        params.append(as_of)
        where.append("(g.rescinded_from IS NULL OR g.rescinded_from > ?)")
        params.append(as_of)
    return where, params


def search(con, query: str, limit: int = 10, **filters) -> list[dict]:
    """Full-text search, ranked, with each hit's resolved state attached.

    The state is the point. A plain FTS hit list cannot tell the reader that
    2481/22 says the invoice format starts in July while 2500/106 moved it to
    October — both documents match "tax invoice", and only one of them is still
    what the rule says. Every row therefore carries its status, what rescinded
    it if anything did, and the current head of its rule thread.
    """
    where, params = _filters(**filters)
    sql = _SELECT.format(w=", ".join(str(w) for w in WEIGHTS))
    if where:
        sql += " AND " + " AND ".join(where)
    rows = con.execute(sql + " ORDER BY score LIMIT ?", [query, *params, limit]).fetchall()
    return [_annotate(dict(r)) for r in rows]


def facets(con, min_uses: int = 3) -> dict:
    """The facet lists worth showing a reader.

    Tags are cut at `min_uses` because the long tail is real and enormous — 206
    of 301 keys are used once — and a facet list longer than the corpus is not a
    navigation aid. The cut is on display only: filtering on a rare tag still
    works, and every tag remains searchable as text.
    """
    q = lambda sql, *a: [dict(r) for r in con.execute(sql, a)]
    return dict(
        subject=q("SELECT subject AS name, COUNT(*) n FROM gazette "
                  "GROUP BY subject ORDER BY n DESC"),
        audience=q("SELECT coarse AS name, COUNT(*) n FROM gazette_audience "
                   "WHERE coarse IS NOT NULL GROUP BY coarse ORDER BY n DESC"),
        tag=q("SELECT tag AS name, COUNT(*) n FROM gazette_tag GROUP BY tag "
              "HAVING n >= ? ORDER BY n DESC, name", min_uses),
        status=q("SELECT status AS name, COUNT(*) n FROM gazette "
                 "WHERE status IS NOT NULL GROUP BY status ORDER BY n DESC"),
    )


def _annotate(r: dict) -> dict:
    """Attach the one-line reading of a hit's standing, so callers do not each
    re-derive it from four columns."""
    # Extraction runs `pdftotext -layout`, which preserves the column spacing
    # that keeps clause numbers attached to their clauses. In a one-line snippet
    # that spacing is just a run of blanks wide enough to push the match off the
    # screen, so it is collapsed here rather than at extraction time, where it
    # is load-bearing.
    if r.get("snip"):
        r["snip"] = " ".join(r["snip"].split())
    if r.get("status") == "rescinded":
        r["standing"] = (f"rescinded by {r['rescinded_by']} from {r['rescinded_from']}"
                         if r.get("rescinded_by") else "rescinded")
    elif r.get("thread_id") and r.get("head_no") and r["head_no"] != r["no"]:
        r["standing"] = f"in force, but {r['head_no']} is the current document in this rule"
    elif r.get("thread_id"):
        r["standing"] = f"current document in a {r['thread_size']}-document rule"
    else:
        r["standing"] = "standalone"
    return r


def rules(con, query: str, limit: int = 10, **filters) -> list[dict]:
    """Search, rolled up to one result per rule instead of one per document.

    This is the answer to the question the README promises: not "which
    documents mention this" but "what is the rule". Searching "tax invoice"
    returns three documents that are three drafts of one rule; a reader wants
    one result whose answer is 2500/106, with the other two visible as the
    history behind it rather than as competing hits.

    A thread's score is its best-matching document's, so a rule surfaces on the
    strength of whichever of its documents states the matter most plainly —
    often the original, whose successors are terse amendments that would rank
    the whole rule down if scores were averaged.

    Standalone documents are threads of one and are returned alongside, because
    "this gazette amends nothing and nothing amends it" is an answer, not a
    reason to be excluded.
    """
    hits = search(con, query, limit=500, **filters)
    threads: dict[object, dict] = {}
    for h in hits:
        key = h["thread_id"] or f"solo:{h['no']}"
        t = threads.get(key)
        if t is None:
            t = threads[key] = dict(
                thread_id=h["thread_id"], score=h["score"], size=h["thread_size"] or 1,
                head_no=h["head_no"] or h["no"], subject=h["subject"], matches=[])
            t["current"] = con.execute(
                "SELECT g.no, g.published_date, g.title, g.effective_from, g.status, "
                "       s.summary FROM gazette g LEFT JOIN gazette_summary s ON s.no=g.no "
                "WHERE g.no=?", (t["head_no"],)).fetchone()
        t["score"] = min(t["score"], h["score"])
        t["matches"].append(h)
    out = sorted(threads.values(), key=lambda t: t["score"])[:limit]
    for t in out:
        t["matches"].sort(key=lambda h: h["published_date"])
    return out
