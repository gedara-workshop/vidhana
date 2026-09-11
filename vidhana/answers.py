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

# Money and rates: after dates, the thing most damaging to get wrong. Written
# many ways in the corpus ("Rs. 2,000.00", "Rs.25, 000.00", "10%of"), so both
# sides are reduced to bare numbers before comparing.
AMOUNT = re.compile(
    r"(?:Rs\.?|LKR|USD|US\s?\$)\s?(\d[\d,\s]*(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s?(?:%|per\s?cent)", re.I)

# The prompt's framing, which means nothing to a reader of a public page.
FRAMING = re.compile(
    r"\b(?:supplied|provided|given)\s+(?:documents?|texts?|facts|gazettes?)\b"
    r"|\bthe\s+(?:documents?|texts?|facts)\s+(?:supplied|provided|given|above|below)\b"
    r"|\bresolver\b|\bprompt\b", re.I)


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
    """Every date the rule's documents contain, or the resolver derived from them.

    From the text itself, not only the dates the parser typed: "optional until
    30.06.2026" is a date the document states even though no pattern classifies
    it, and refusing it would reject a true answer.
    """
    out: set[str] = set()
    for m in members(con, root_no):
        for k in ("published_date", "effective_from", "rescinded_from"):
            if m[k]:
                out.add(m[k])
        out.update(r["date"] for r in con.execute(
            "SELECT date FROM gazette_date WHERE no=?", (m["no"],)))
        if m["text_path"]:
            try:
                with open(m["text_path"]) as fh:
                    out |= _dates_in(fh.read())
            except OSError:
                pass
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


def _amount(raw: str) -> str:
    """"2,000.00" and "2000" and "2, 000" are one amount."""
    v = re.sub(r"[,\s]", "", raw)
    return re.sub(r"\.0+$", "", v)


def _amounts_in(text: str) -> set[str]:
    return {_amount(a or b) for a, b in AMOUNT.findall(text)}


def known_amounts(con, root_no: str) -> set[str]:
    """Every figure in the rule's documents, amounts or not.

    Deliberately generous: an amount in an answer only has to appear somewhere
    in the documents as a number. What this catches is an invented figure, not
    a misattributed one — that is what reading the pull request is for.
    """
    out: set[str] = set()
    for m in members(con, root_no):
        if not m["text_path"]:
            continue
        try:
            with open(m["text_path"]) as fh:
                text = fh.read()
        except OSError:
            continue
        joined = re.sub(r"(\d),\s+(\d)", r"\1,\2", text)      # "25, 000.00"
        out |= {_amount(n) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", joined)}
    return out


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
    amounts = known_amounts(con, root_no)
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
        for amt in sorted(_amounts_in(a) - amounts):
            problems.append(f"{where}: states the figure {amt}, which no document here contains")
        f = FRAMING.search(q + " " + a)
        if f:
            problems.append(f"{where}: {f.group(0)!r} is how the question was put to you, "
                            f"not something a reader knows — say 'the gazettes in this rule'")
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


# --- writing them ---------------------------------------------------------------

SYSTEM = """You write the questions people actually ask about one Sri Lankan tax rule, \
and answer them, for a public page on a gazette-tracking site.

Readers are business owners, their accountants and tax practitioners. A rule is \
usually several gazettes: one sets it up, later ones amend or rescind it. You are given \
the resolver's facts about every document in the rule — which one is current, what \
superseded what, and when — and the documents' text.

Rules:

1. Write 3 to 5 questions a reader would really ask about this rule — what it requires, \
who it binds, from when, what changed, what happens if they do nothing. Not questions about \
gazette numbers for their own sake.
2. Answer ONLY from the documents and facts given. Never add a date, amount, rate, form, \
deadline or exception the documents do not state. If the documents cannot answer something, \
do not ask that question.
3. The resolver's facts are authoritative about which document is current and what was \
superseded or rescinded. Never present a superseded or rescinded provision as the rule.
4. Cite the gazettes each answer rests on, by number, in `cites`, and mention them in the \
answer text where it helps. Always cite the current document somewhere in the set.
5. Write dates as "1 October 2026". Never write relative time — no "currently", "now", \
"will", "soon", "next year", "recently". The page is read long after it is written, so \
state what applies from which date: "From 1 October 2026, every VAT-registered business \
must…", not "Businesses will have to…".
6. Plain English, no legalese, at most 110 words per answer. Do not give advice beyond what \
the documents say, and do not tell the reader to consult anyone.
7. If the facts say the rule's history is incomplete, do not claim that nothing else \
changed it."""


def _schema():
    from pydantic import BaseModel, Field

    class QA(BaseModel):
        question: str = Field(description="A question a reader would ask, ending in ?")
        answer: str = Field(description="Plain English, at most 110 words, dated, no relative time")
        cites: list[str] = Field(description="Gazette numbers (NNNN/NN) the answer rests on")

    class RuleQuestions(BaseModel):
        questions: list[QA]

    return RuleQuestions


def _standing(m: dict, head: str) -> str:
    """What the resolver says, in words that do not overstate it.

    Not "superseded": in the tax-invoice rule 2481/22 is still the format in
    force — 2500/106 only moved its start date — and the resolver's status for
    it is in_force. Calling it superseded invites an answer saying the format
    no longer applies.
    """
    if m["status"] == "rescinded":
        return f"RESCINDED by {m['rescinded_by']} from {m['rescinded_from']}"
    if m["no"] == head:
        return "in force; the latest document in force in this rule"
    return f"in force, as amended by later documents in this rule (the latest is {head})"


# Character budgets. The largest rule in the corpus carries 300,000 characters
# of text; the current document matters most, the others mostly for history.
HEAD_CHARS, OTHER_CHARS, TOTAL_CHARS = 24_000, 5_000, 70_000


def build_prompt(con, root_no: str) -> str:
    t = rule(con, root_no)
    ms = members(con, root_no)
    summaries = {r["no"]: r["summary"] for r in con.execute(
        "SELECT no, summary FROM gazette_summary WHERE no IN (%s)" % ",".join("?" * len(ms)),
        [m["no"] for m in ms])}
    missing = sorted({r["dst_no"] for m in ms for r in con.execute(
        "SELECT dst_no FROM gazette_reference WHERE src_no=? AND dst_no NOT IN "
        "(SELECT no FROM gazette)", (m["no"],))})

    parts = [f"RULE: {t['label']}", f"Enabling Act: {t['enabling_act']}",
             f"Latest document in force: {t['head_no']}", "",
             "The summaries below are earlier paraphrases and may round a date or infer "
             "one; where a summary and the document text differ, the text wins.", "",
             "DOCUMENTS, oldest first:"]
    for m in ms:
        parts.append(f"- {m['no']}, published {m['published_date']}: {m['title']}\n"
                     f"  standing: {_standing(m, t['head_no'])}; "
                     f"effective from {m['effective_from']}\n"
                     f"  summary: {summaries.get(m['no']) or '(none)'}")
    if missing:
        parts.append(f"\nHISTORY INCOMPLETE: these gazettes are referenced but not held: "
                     f"{', '.join(missing)}. A change made by one of them would not appear here.")

    used = 0
    for m in sorted(ms, key=lambda m: m["no"] != t["head_no"]):   # current document first
        if not m["text_path"]:
            continue
        with open(m["text_path"]) as fh:
            body = fh.read()
        cap = min(HEAD_CHARS if m["no"] == t["head_no"] else OTHER_CHARS, TOTAL_CHARS - used)
        if cap <= 0:
            parts.append(f"\n--- TEXT OF {m['no']} omitted for length ---")
            continue
        if len(body) > cap:
            body = body[:cap] + "\n[... truncated ...]"
        used += len(body)
        parts.append(f"\n--- TEXT OF {m['no']} ---\n{body}")
    return "\n".join(parts)


def generate(con, root_no: str, model: str, attempts: int = 3) -> dict:
    """Write one rule's questions, retrying with the checker's objections.

    Returns the set with `problems` empty if it passed, or the last attempt's
    problems if it never did — in which case nothing is stored for the rule.
    """
    import datetime as dt

    from .structure import _client

    client, schema = _client(), _schema()
    prompt = build_prompt(con, root_no)
    feedback = ""
    tin = tout = 0
    for _ in range(attempts):
        r = client.responses.parse(
            model=model, instructions=SYSTEM,
            input=[{"role": "user", "content": prompt + feedback}], text_format=schema)
        tin += r.usage.input_tokens
        tout += r.usage.output_tokens
        qs = [q.model_dump() for q in r.output_parsed.questions]
        problems = verify(con, root_no, qs)
        if not problems:
            break
        feedback = ("\n\nA PREVIOUS ATTEMPT FAILED THESE CHECKS. Rewrite the whole set so "
                    "none of them apply:\n- " + "\n- ".join(problems))
    return dict(rule=root_no, basis=basis(con, root_no), model=model,
                generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                questions=qs, problems=problems, input_tokens=tin, output_tokens=tout)


def status(con, path: str = ANSWERS) -> list[dict]:
    """Every rule, and whether its answers are current, stale, failing or missing."""
    sets = load(path)
    out = []
    for r in con.execute("SELECT root_no, head_no FROM rule_thread ORDER BY root_no"):
        s = sets.get(r["root_no"])
        if not s:
            state = "missing"
        elif s["basis"] != basis(con, r["root_no"]):
            state = "stale"
        elif verify(con, r["root_no"], s["questions"]):
            state = "failing"
        else:
            state = "current"
        out.append(dict(rule=r["root_no"], state=state,
                        questions=len(s["questions"]) if s else 0))
    return out
