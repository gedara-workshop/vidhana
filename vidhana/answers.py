"""Pre-answered questions for each rule.

People do not ask a search box for "gazette 2481/22". They ask "do I need to
change my invoices?". This writes a handful of those questions for each rule,
with answers, and publishes them on the rule page — where they are also what
a person types into a search engine.

The standing risk is a confident, wrong answer about the law, and everything
here is arranged around it:

- **The resolver decides; the model only phrases.** The prompt carries the
  resolver's facts — which document is current, what superseded what, every
  date — and the documents' own text. The model is told to answer only from
  those, and to cite them.
- **A deterministic check, not the model, decides what is published.** Every
  cited gazette must belong to the rule; every gazette number and every date
  in an answer must appear in the documents; the current document must be
  cited; and wording that goes stale on its own ("currently", "will", "next
  year") is refused, because a static page is read long after it was written.
- **A stale answer is never shown.** Each set records a fingerprint of the
  rule's state when it was written. A new amendment changes the fingerprint,
  and the set disappears from the site until it is regenerated.
- **Generated offline, reviewed as a pull request, tracked in git**
  (data/answers.json), like data/summaries.json. No model runs when someone
  reads the page.

Live question-and-answer was considered alongside this and deferred: it needs
a server to hold the API key, which forces the hosting decision that is still
open, and answers nobody has read.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from . import parse

ANSWERS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "answers.json")

# Wording a static page cannot keep true. "From 1 October 2026 every
# VAT-registered business must..." stays right for as long as the rule does;
# "will have to... from next month" is wrong the day the date passes, with no
# change to the rule to make the answer stale.
STALE_WORDING = re.compile(
    r"\b(currently|at present|presently|recently|soon|upcoming|will|shall soon"
    r"|next (?:week|month|year)|this (?:week|month|year)|last (?:week|month|year)"
    r"|today|tomorrow|yesterday)\b", re.I)

GAZETTE_NO = re.compile(r"\b(\d{3,4})\s*/\s*(\d{1,3})\b")

MIN_QUESTIONS, MAX_QUESTIONS = 3, 6


def members(con, root_no: str) -> list[dict]:
    """The rule's documents, oldest first, with what the resolver says of each."""
    t = con.execute("SELECT thread_id FROM rule_thread WHERE root_no=?", (root_no,)).fetchone()
    if not t:
        raise KeyError(root_no)
    return [dict(r) for r in con.execute(
        "SELECT no, published_date, title, status, rescinded_by, rescinded_from, "
        "       effective_from, pdf_sha256, text_path "
        "FROM gazette WHERE thread_id=? ORDER BY published_date, no", (t["thread_id"],))]


def rule(con, root_no: str) -> dict:
    return dict(con.execute("SELECT * FROM rule_thread WHERE root_no=?", (root_no,)).fetchone())


def basis(con, root_no: str) -> str:
    """A fingerprint of everything an answer about this rule rests on.

    Membership, the current document, each document's standing and dates, and
    the PDFs themselves. Anything that could make a written answer wrong changes
    it; nothing else does, so answers are not hidden for no reason.
    """
    t = rule(con, root_no)
    state = dict(
        head=t["head_no"],
        unresolved=t["unresolved"],
        members=[{k: m[k] for k in ("no", "status", "rescinded_by", "rescinded_from",
                                     "effective_from", "pdf_sha256")}
                 for m in members(con, root_no)],
    )
    blob = json.dumps(state, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def known_dates(con, root_no: str) -> set[str]:
    """Every date the rule's documents state or the resolver derived from them."""
    out: set[str] = set()
    for m in members(con, root_no):
        for k in ("published_date", "effective_from", "rescinded_from"):
            if m[k]:
                out.add(m[k])
        out.update(r["date"] for r in con.execute(
            "SELECT date FROM gazette_date WHERE no=?", (m["no"],)))
    return out


def known_numbers(con, root_no: str) -> set[str]:
    """The rule's documents, and every gazette they refer to."""
    nos = {m["no"] for m in members(con, root_no)}
    for n in list(nos):
        nos.update(r["dst_no"] for r in con.execute(
            "SELECT dst_no FROM gazette_reference WHERE src_no=?", (n,)))
    return nos


def _numbers_in(text: str) -> set[str]:
    return {f"{int(a):d}/{int(b):02d}" for a, b in GAZETTE_NO.findall(text)}


def _dates_in(text: str) -> set[str]:
    return {d for d in (parse.parse_date(m.group(1)) for m in parse.DATE_TOKEN.finditer(text)) if d}


def verify(con, root_no: str, questions: list[dict]) -> list[str]:
    """Reasons this set must not be published. Empty means it may be.

    Deliberately strict and deliberately dumb: it cannot tell whether an answer
    is wise, only whether it claims anything the documents do not contain. The
    pull request is where a person reads them.
    """
    t = rule(con, root_no)
    in_rule = {m["no"] for m in members(con, root_no)}
    numbers = known_numbers(con, root_no)
    dates = known_dates(con, root_no)
    problems: list[str] = []

    if not MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS:
        problems.append(f"{len(questions)} questions; want {MIN_QUESTIONS}-{MAX_QUESTIONS}")

    cited_anywhere: set[str] = set()
    for i, qa in enumerate(questions, 1):
        q, a, cites = qa["question"].strip(), qa["answer"].strip(), qa["cites"]
        where = f"Q{i}"
        if not q.endswith("?"):
            problems.append(f"{where}: the question is not a question")
        if not cites:
            problems.append(f"{where}: cites nothing")
        for c in cites:
            if c not in in_rule:
                problems.append(f"{where}: cites {c}, which is not part of this rule")
        cited_anywhere.update(cites)
        for n in _numbers_in(q + " " + a) - numbers:
            problems.append(f"{where}: mentions gazette {n}, which no document here refers to")
        for d in _dates_in(q + " " + a) - dates:
            problems.append(f"{where}: states {d}, a date no document here contains")
        m = STALE_WORDING.search(a)
        if m:
            problems.append(f"{where}: {m.group(0)!r} goes stale on a static page — "
                            f"state the date instead")
        if len(a) > 900:
            problems.append(f"{where}: answer is {len(a)} characters; keep it under 900")

    if t["head_no"] not in cited_anywhere:
        problems.append(f"the current document, {t['head_no']}, is never cited")
    return problems


def load(path: str = ANSWERS) -> dict[str, dict]:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {r["rule"]: r for r in json.load(f)}


def save(sets: dict[str, dict], path: str = ANSWERS) -> None:
    """Sorted by rule, stable key order: regenerating one rule is a one-record diff."""
    with open(path, "w") as f:
        json.dump([sets[k] for k in sorted(sets)], f, indent=2, ensure_ascii=False)
        f.write("\n")


def publishable(con, path: str = ANSWERS) -> dict[str, list[dict]]:
    """Answer sets that may be shown, by rule root: current and still passing.

    Re-verified on every export rather than trusted from when they were written,
    because the corpus around them moves.
    """
    out = {}
    for root, s in load(path).items():
        try:
            current = basis(con, root)
        except KeyError:
            continue                      # the rule no longer exists in this shape
        if s["basis"] == current and not verify(con, root, s["questions"]):
            out[root] = s["questions"]
    return out
