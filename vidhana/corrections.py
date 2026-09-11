"""Human decisions about the corpus, recorded in git with their reasons.

The database is rebuilt from scratch every night, so a fix made in it by hand
is gone by morning. Anything a person decides has to live in a tracked file
and be applied deterministically on every build — the same arrangement as
data/summaries.json.

This was agreed as one of three pieces that replace an admin UI. It was built
when there was a concrete case for it, and the case turned out narrower than
expected: of the six disagreements `validate` reported, four were parser bugs
with general fixes (the "one-off" signatory on 1789/09 was one of six
documents with the same problem). A regex is the right tool for a pattern.
What remained were two places where a heuristic check is wrong and only a
person reading the document can say so.

So only what is needed exists. One field is supported, and anything else is
rejected rather than ignored, because an entry that silently does nothing is
worse than an error:

  audience   `from` is a string the model wrote for this gazette; `to` is the
             Act-map audience a reviewer has confirmed it narrows. `to` must
             already be one of the Act's candidates — a correction can place
             an audience, never invent one, which is the same rule the model
             is held to.

Every entry carries a reason. It is the audit trail; there is no other.
"""
from __future__ import annotations

import functools
import json
import os

CORRECTIONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "corrections.json")

FIELDS = {"audience": ("no", "from", "to", "reason")}


def _check(entries: list[dict]) -> list[dict]:
    for i, e in enumerate(entries):
        field = e.get("field")
        if field not in FIELDS:
            raise ValueError(f"correction {i}: unsupported field {field!r} "
                             f"(supported: {', '.join(sorted(FIELDS))})")
        missing = [k for k in FIELDS[field] if not str(e.get(k) or "").strip()]
        if missing:
            raise ValueError(f"correction {i} ({e.get('no')}): missing {', '.join(missing)}")
    return entries


@functools.lru_cache(maxsize=None)
def load(path: str = CORRECTIONS) -> tuple[dict, ...]:
    if not os.path.exists(path):
        return ()
    with open(path) as f:
        return tuple(_check(json.load(f)))


def audience(no: str | None, model_string: str,
             entries: tuple[dict, ...] | None = None) -> dict | None:
    """The reviewed placement for one of the model's audience strings, if any."""
    if not no:
        return None
    for e in (load() if entries is None else entries):
        if e["field"] == "audience" and e["no"] == no and e["from"] == model_string:
            return e
    return None


def stale(con, entries: tuple[dict, ...] | None = None) -> list[dict]:
    """Corrections that no longer match anything the model wrote.

    A re-summarised gazette gets new wording, and a correction keyed to the old
    wording then applies to nothing. That must be reported, not left to rot:
    the reviewer's decision was about a sentence that no longer exists.
    """
    out = []
    for e in (load() if entries is None else entries):
        row = con.execute("SELECT audience FROM gazette_summary WHERE no=?", (e["no"],)).fetchone()
        if row is None or e["from"] not in json.loads(row["audience"] or "[]"):
            out.append(e)
    return out
