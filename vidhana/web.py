"""Export the corpus as a static search index for the web front end.

The whole point of `docs/` being static is that there is no server to run and
no hosting decision to make. That works here because the corpus is small: 144
documents, 1.1 MB of body text, which gzips to a fraction of that over GitHub
Pages. So the browser gets the *real* corpus and can run the same search the
CLI runs, rather than a cut-down preview that quietly answers a different
question.

Two files, because they have different urgencies:

    index.json   metadata, summaries, threads, facets — everything needed to
                 render, filter and browse. Small, fetched first, blocking.
    bodies.json  the full statutory text. Large, fetched in the background;
                 until it lands, search covers titles and summaries and the
                 page says so rather than silently returning fewer results.

Nothing here is derived differently from the CLI. Standing, thread heads and
the incomplete-history flag all come from the same resolver output, so the two
surfaces cannot drift into disagreeing about whether a rule is in force.
"""
from __future__ import annotations

import json
import os

SCHEMA_VERSION = 1


def _rows(con, sql, *a):
    return [dict(r) for r in con.execute(sql, a)]


def build(con) -> tuple[dict, dict]:
    """Return (index, bodies). Pure: reads the database, writes nothing."""
    gazettes = _rows(con, """
        SELECT g.no, g.published_date, g.title, g.subject, g.enabling_act,
               g.status, g.rescinded_by, g.rescinded_from, g.effective_from,
               g.thread_id, g.source, g.source_detail, g.source_url,
               g.needs_ocr, s.summary, s.obligation, s.confidence, s.notes
        FROM gazette g LEFT JOIN gazette_summary s ON s.no = g.no
        ORDER BY g.published_date DESC""")

    threads = {t["thread_id"]: t for t in _rows(con, """
        SELECT thread_id, subject, enabling_act, root_no, head_no,
               first_date, last_date, size, unresolved FROM rule_thread""")}

    tags: dict[str, list[str]] = {}
    for r in con.execute("SELECT no, tag FROM gazette_tag ORDER BY tag"):
        tags.setdefault(r["no"], []).append(r["tag"])
    audience: dict[str, list[str]] = {}
    for r in con.execute("SELECT no, coarse, audience FROM gazette_audience"):
        v = r["coarse"] or r["audience"]
        audience.setdefault(r["no"], [])
        if v not in audience[r["no"]]:
            audience[r["no"]].append(v)

    refs: dict[str, list[dict]] = {}
    for r in con.execute("SELECT src_no, dst_no, relation FROM gazette_reference "
                         "WHERE relation != 'cites'"):
        refs.setdefault(r["src_no"], []).append(dict(to=r["dst_no"], rel=r["relation"]))

    dates: dict[str, list[dict]] = {}
    for r in con.execute("SELECT no, kind, date FROM gazette_date ORDER BY date"):
        dates.setdefault(r["no"], []).append(dict(kind=r["kind"], date=r["date"]))

    held = {g["no"] for g in gazettes}
    for g in gazettes:
        t = threads.get(g["thread_id"])
        g["tags"] = tags.get(g["no"], [])
        g["audience"] = audience.get(g["no"], [])
        g["refs"] = refs.get(g["no"], [])
        g["dates"] = dates.get(g["no"], [])
        g["head_no"] = t["head_no"] if t else None
        g["thread_size"] = t["size"] if t else 1
        # The disclosure the CLI and the feed both carry, precomputed so the
        # page cannot render a result without it being available.
        g["unresolved"] = (t["unresolved"] or 0) if t else 0
        g["missing_refs"] = [r["to"] for r in g["refs"] if r["to"] not in held]

    index = dict(
        version=SCHEMA_VERSION,
        generated_from="https://www.ird.gov.lk/en/publications/sitepages/gazette.aspx?menuid=1602",
        counts=dict(
            gazettes=len(gazettes),
            listed=sum(1 for g in gazettes if g["source"] == "ird-listing"),
            recovered=sum(1 for g in gazettes if g["source"] != "ird-listing"),
            threads=len(threads),
            unresolved_threads=sum(1 for t in threads.values() if t["unresolved"]),
        ),
        gazettes=gazettes,
        threads=list(threads.values()),
    )
    bodies = {}
    for g in gazettes:
        row = con.execute("SELECT text_path FROM gazette WHERE no=?", (g["no"],)).fetchone()
        if not row or not row["text_path"]:
            continue
        try:
            with open(row["text_path"]) as f:
                bodies[g["no"]] = f.read()
        except OSError:
            continue          # PDFs are gitignored; a fresh clone has no text yet
    return index, bodies


def export(con, out_dir: str = "docs/data") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    index, bodies = build(con)
    out = {}
    for name, payload in (("index.json", index), ("bodies.json", bodies)):
        path = os.path.join(out_dir, name)
        # Separators without spaces, keys sorted: the file is committed, so a
        # rebuild that changed nothing must produce a byte-identical diff.
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")) + "\n"
        old = None
        if os.path.exists(path):
            with open(path) as f:
                old = f.read()
        if old != text:
            with open(path, "w") as f:
                f.write(text)
        out[name] = dict(path=path, bytes=len(text.encode()), changed=old != text)
    return out
