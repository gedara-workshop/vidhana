"""Phase 2: LLM structuring — plain-English summaries and audience inference.

Provider is OpenAI (Dinal's choice; the key lives in .env as OPENAI_API_KEY).
Default model is the cheapest current generation, gpt-5.6-luna, again by choice:
the whole corpus costs roughly $0.11 batched.

The two things this pass adds that Phase 1 cannot:

  * a plain-English summary, because gazettes are drafted as textual surgery
    ("substitute paragraph (i) of item (2) of the Schedule");
  * the affected audience, which Phase 0 found is simply absent from most
    documents — 9 of 21 sampled state no audience at all.

Everything else the model reports (effective date, enabling Act, authority) is
already derived deterministically in Phase 1 and is re-asked *only so it can be
checked*. See `check()` and `vidhana validate`.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3

from pydantic import BaseModel, Field

from .util import load_env

DEFAULT_MODEL = "gpt-5.6-luna"

# Phase 0 finding: audience is not in the documents, but the corpus rests on only
# five enabling Acts. Grounding the inference on a curated map is auditable;
# free-form inference is not. The model may narrow within an Act's audience but
# is told not to invent one.
ACT_AUDIENCE = {
    "Value Added Tax Act": [
        "VAT-registered businesses",
        "consumers (indirectly, through prices)",
    ],
    "Inland Revenue Act": [
        "income taxpayers",
        "withholding agents",
        "employers",
    ],
    "Stamp Duty (Special Provisions) Act": [
        "parties to leases, transfers and other stampable instruments",
        "notaries",
    ],
    "Casino Business (Regulation) Act": [
        "casino licence holders and applicants",
    ],
    "Economic Service Charge Act": [
        "businesses liable to the Economic Service Charge",
    ],
    # The five above are the Acts CORPUS-NOTES.md found across the 21-document
    # sample. Running the full 137 turned up seven more, each of which left the
    # model to infer an audience with no candidates at all — and it marked every
    # one of those documents `low` confidence, correctly. These lists are read
    # off the gazettes themselves, so they cover what the corpus actually
    # contains under each Act rather than the Act's full statutory scope.
    "Social Security Contribution Levy Act": [
        "businesses liable to the Social Security Contribution Levy",
    ],
    "Default Taxes (Special Provisions) Act": [
        "taxpayers with tax already in default",
    ],
    "Tax Appeals Commission Act": [
        "taxpayers appealing a Commissioner-General determination",
        "authorised representatives appearing before the Tax Appeals Commission",
    ],
    "Debits Tax Act": [
        "holders of current and savings accounts",
        "banks and financial institutions collecting debits tax",
    ],
    "Turnover Tax Act": [
        "businesses liable to turnover tax",
    ],
    "Stamp Duty Act": [
        "parties to leases, transfers and other stampable instruments",
        "notaries",
    ],
    # The Finance Act is a grab-bag: in this corpus it carries a departure levy
    # and a motor vehicle concessionary levy, which share no audience. Listing
    # both is honest about that; inventing a single "persons liable under the
    # Finance Act" would be a category, not an audience.
    "Finance Act": [
        "travellers leaving Sri Lanka",
        "persons claiming the permitted motor vehicle concession",
    ],
}

# The Act name is parsed from the PDF and the PDF is not always right: the
# corpus contains "Value Addded Tax Act" (a typo in the source, preserved) and
# "A Value Added Tax Act" (a parse artifact). Substring lookup misses both, so
# two plainly-VAT gazettes were summarised with no audience candidates at all.
# `subject` is classified from the Act *and* the title and survives that, so it
# is the fallback.
ACT_SUBJECT = {
    "vat": "Value Added Tax Act",
    "income-tax": "Inland Revenue Act",
    "stamp-duty": "Stamp Duty (Special Provisions) Act",
    "betting-gaming": "Casino Business (Regulation) Act",
    "esc": "Economic Service Charge Act",
    "sscl": "Social Security Contribution Levy Act",
}


def audience_candidates(act: str | None, subject: str | None = None) -> list[str] | None:
    """The audience list the model may narrow within, or None if the Act is
    genuinely unmapped. Never returns an invented candidate."""
    act = act or ""
    hit = next((v for k, v in ACT_AUDIENCE.items() if k.lower() in act.lower()), None)
    if hit:
        return hit
    mapped = ACT_SUBJECT.get(subject or "")
    return ACT_AUDIENCE.get(mapped) if mapped else None

SYSTEM = """You summarise Sri Lankan government gazettes for a compliance alerting product.

Readers are business owners and their accountants. They need to know what changed, \
who it binds, and from when. The PDF is the source of truth and your summary is a \
convenience — it must never state anything the document does not support.

Rules:

1. Write the summary in plain English, 2-4 sentences, no legalese. If the gazette is \
textual surgery on an earlier one ("substitute paragraph (i) of item (2)"), say what \
that change actually does in practice, not what it does grammatically.
2. AUDIENCE: most gazettes never state who they affect. Infer it from the enabling Act \
using the candidates supplied, narrowing where the text clearly narrows (for example \
"non-resident persons supplying services through an electronic platform"). Never invent \
an audience the Act does not bind. If you genuinely cannot tell, return the Act-level \
audience unchanged and set confidence to "low".
3. EFFECTIVE DATE: report only a date the document itself states. Effective dates are \
often retroactive, sometimes several per document, and sometimes buried at the end. If \
there are several, give the earliest one that starts an obligation. If none is stated, \
return null — do not substitute the publication date.
4. Preserve the document's own typos when quoting; do not silently correct them.
5. OBLIGATION vs INFORMATION: "obligation" if someone must do something by a date, \
otherwise "information".
6. If anything is unclear, ambiguous, or looks like it depends on a document you have \
not been shown, say so in `notes` rather than guessing.
7. AMENDED POSITION: if a later gazette is supplied that amends this one, summarise the \
position AS AMENDED and say so explicitly ("as amended by 2500/106, from 1 October 2026"). \
A reader acting on the original date would be acting on a superseded rule. Set \
`effective_date` to the date stated in THIS document, but make the summary text state \
the amended position — the two are allowed to differ, and `notes` should explain why."""


class GazetteSummary(BaseModel):
    summary: str = Field(description="Plain English, 2-4 sentences, what changed and why it matters")
    audience: list[str] = Field(description="Who this binds; grounded on the enabling Act")
    obligation: str = Field(description='"obligation" or "information"')
    effective_date: str | None = Field(description="ISO yyyy-mm-dd stated in the document, else null")
    enabling_act: str | None = Field(description="Act name as printed, without the number")
    authority: str | None = Field(description="Name of the signatory")
    tags: list[str] = Field(description="3-6 lowercase kebab-case topic tags")
    confidence: str = Field(description='"high", "medium" or "low"')
    notes: str | None = Field(description="Anything unclear or dependent on an unseen document")


def strict_schema() -> dict:
    """OpenAI structured outputs require a strict JSON schema: every property required
    and `additionalProperties: false` throughout.

    The SDK ships a helper for this but it lives in a private module, so it is
    tried first and a self-contained conversion backs it up. GazetteSummary is
    flat (strings and arrays of strings), which is why the fallback can be short.
    """
    try:
        from openai.lib._pydantic import to_strict_json_schema
        return to_strict_json_schema(GazetteSummary)
    except Exception:
        schema = GazetteSummary.model_json_schema()

        def harden(node):
            if isinstance(node, dict):
                if node.get("type") == "object" or "properties" in node:
                    node["additionalProperties"] = False
                    node["required"] = list(node.get("properties", {}))
                for v in node.values():
                    harden(v)
            elif isinstance(node, list):
                for v in node:
                    harden(v)
            return node

        return harden(schema)


def _request_body(con, no: str, model: str) -> dict:
    """The body shared by the live and batched paths, so they cannot drift."""
    return {
        "model": model,
        "instructions": SYSTEM,
        "input": [{"role": "user", "content": build_prompt(con, no)}],
        "text": {"format": {"type": "json_schema", "name": "GazetteSummary",
                            "schema": strict_schema(), "strict": True}},
    }


def _client():
    load_env()
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set (looked at the environment and .env)")
    from openai import OpenAI
    return OpenAI()


def build_prompt(con: sqlite3.Connection, no: str) -> str:
    """One document, plus the resolved thread state around it.

    The thread context matters: half the corpus amends or rescinds something, and
    a summary written as if the document stood alone is how you end up telling
    someone the invoice deadline is July when 2500/106 moved it to October.
    """
    g = con.execute("SELECT * FROM gazette WHERE no=?", (no,)).fetchone()
    if not g:
        raise KeyError(no)
    with open(g["text_path"]) as fh:
        text = fh.read()

    act = (g["enabling_act"] or "").replace("The ", "")
    candidates = audience_candidates(act, g["subject"])

    parts = [
        f"GAZETTE {g['no']}, published {g['published_date']}.",
        f"Listing description: {g['title']}",
        f"Enabling Act (parsed deterministically): {g['enabling_act']}, No. {g['enabling_act_no']}",
    ]
    if candidates:
        parts.append("Audience candidates for this Act (narrow within these, do not invent): "
                     + "; ".join(candidates))
    else:
        parts.append("No audience map for this Act — infer conservatively and set confidence low.")

    refs = con.execute(
        "SELECT relation, dst_no FROM gazette_reference WHERE src_no=? "
        "AND relation != 'cites'", (no,)).fetchall()
    inc = con.execute(
        "SELECT relation, src_no FROM gazette_reference WHERE dst_no=? "
        "AND relation != 'cites'", (no,)).fetchall()
    if refs:
        parts.append("This gazette " + "; ".join(f"{r['relation']} {r['dst_no']}" for r in refs))
    if inc:
        parts.append("Later gazettes acting on this one: "
                     + "; ".join(f"{r['src_no']} {r['relation']} it" for r in inc))
        # Include the amending text, not just the reference. Without it the model
        # can only summarise the document as published — which for 2481/22 means
        # saying the invoice format starts in July, when 2500/106 moved it to
        # October. The model flagged this itself on the first run.
        for r in inc:
            amender = con.execute(
                "SELECT no, published_date, text_path FROM gazette WHERE no=?",
                (r["src_no"],)).fetchone()
            if not amender or not amender["text_path"]:
                continue
            with open(amender["text_path"]) as fh:
                body = fh.read()
            if len(body) > 6000:      # amendments are short; long ones get their head
                body = body[:6000] + "\n[... truncated, see the gazette itself ...]"
            parts.append(f"\n--- TEXT OF {amender['no']} ({amender['published_date']}), "
                         f"which {r['relation']} this gazette ---\n{body}")
    if g["needs_ocr"]:
        parts.append("WARNING: part of this document is an image and is missing from the text "
                     "below. Say so in notes and lower confidence.")

    parts.append("\n--- DOCUMENT TEXT ---\n" + text)
    return "\n".join(parts)


def summarise(con: sqlite3.Connection, no: str, model: str = DEFAULT_MODEL) -> dict:
    client = _client()
    r = client.responses.parse(
        model=model,
        instructions=SYSTEM,
        input=[{"role": "user", "content": build_prompt(con, no)}],
        text_format=GazetteSummary,
    )
    out = r.output_parsed
    row = dict(
        no=no, model=model, summary=out.summary,
        audience=json.dumps(out.audience), obligation=out.obligation,
        effective_date=out.effective_date, enabling_act=out.enabling_act,
        authority=out.authority, tags=json.dumps(out.tags),
        confidence=out.confidence, notes=out.notes,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        input_tokens=r.usage.input_tokens, output_tokens=r.usage.output_tokens)
    con.execute(
        "INSERT OR REPLACE INTO gazette_summary "
        "(no, model, summary, audience, obligation, effective_date, enabling_act, "
        " authority, tags, confidence, notes, generated_at, input_tokens, output_tokens) "
        "VALUES (:no,:model,:summary,:audience,:obligation,:effective_date,:enabling_act,"
        ":authority,:tags,:confidence,:notes,:generated_at,:input_tokens,:output_tokens)", row)
    con.commit()
    return row


# ---------------------------------------------------------------------------
# Batch API: half price, parallel server-side, asynchronous.
# ---------------------------------------------------------------------------

def submit_batch(con: sqlite3.Connection, nos: list[str], model: str = DEFAULT_MODEL) -> str:
    """Upload a JSONL of requests and start a batch. Returns the batch id."""
    import io

    client = _client()
    lines = []
    for no in nos:
        lines.append(json.dumps({
            "custom_id": no.replace("/", "-"),   # custom_id has a restricted charset
            "method": "POST",
            "url": "/v1/responses",
            "body": _request_body(con, no, model),
        }))
    payload = ("\n".join(lines) + "\n").encode()

    up = client.files.create(file=("vidhana-batch.jsonl", io.BytesIO(payload)), purpose="batch")
    batch = client.batches.create(input_file_id=up.id, endpoint="/v1/responses",
                                  completion_window="24h")
    con.execute(
        "INSERT OR REPLACE INTO batch_job (id, model, submitted_at, status, n_requests, "
        "input_file_id) VALUES (?,?,?,?,?,?)",
        (batch.id, model, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         batch.status, len(nos), up.id))
    con.commit()
    return batch.id


def poll_batch(con: sqlite3.Connection, batch_id: str) -> dict:
    client = _client()
    b = client.batches.retrieve(batch_id)
    con.execute("UPDATE batch_job SET status=?, output_file_id=? WHERE id=?",
                (b.status, getattr(b, "output_file_id", None), batch_id))
    con.commit()
    counts = getattr(b, "request_counts", None)
    return dict(id=b.id, status=b.status,
                completed=getattr(counts, "completed", None),
                failed=getattr(counts, "failed", None),
                total=getattr(counts, "total", None))


def collect_batch(con: sqlite3.Connection, batch_id: str) -> dict:
    """Read a finished batch's output file into gazette_summary.

    Results come back in arbitrary order, so rows are keyed by custom_id — never
    by position.
    """
    client = _client()
    b = client.batches.retrieve(batch_id)
    if b.status != "completed":
        return dict(status=b.status, collected=0, failed=0)
    text = client.files.content(b.output_file_id).text
    job = con.execute("SELECT model FROM batch_job WHERE id=?", (batch_id,)).fetchone()
    model = job["model"] if job else DEFAULT_MODEL

    collected = failed = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        no = rec["custom_id"].replace("-", "/", 1)
        body = (rec.get("response") or {}).get("body")
        if rec.get("error") or not body:
            failed += 1
            continue
        try:
            blob = next(c["text"] for item in body["output"]
                        if item.get("type") == "message"
                        for c in item["content"] if c.get("type") == "output_text")
            out = GazetteSummary.model_validate_json(blob)
        except Exception:
            failed += 1
            continue
        usage = body.get("usage") or {}
        con.execute(
            "INSERT OR REPLACE INTO gazette_summary VALUES "
            "(:no,:model,:summary,:audience,:obligation,:effective_date,:enabling_act,"
            ":authority,:tags,:confidence,:notes,:generated_at,:input_tokens,:output_tokens)",
            dict(no=no, model=model, summary=out.summary,
                 audience=json.dumps(out.audience), obligation=out.obligation,
                 effective_date=out.effective_date, enabling_act=out.enabling_act,
                 authority=out.authority, tags=json.dumps(out.tags),
                 confidence=out.confidence, notes=out.notes,
                 generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 input_tokens=usage.get("input_tokens"),
                 output_tokens=usage.get("output_tokens")))
        collected += 1
    con.execute("UPDATE batch_job SET status=?, collected_at=?, n_collected=?, n_failed=? "
                "WHERE id=?",
                (b.status, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 collected, failed, batch_id))
    con.commit()
    return dict(status=b.status, collected=collected, failed=failed)


def _norm_act(v: str | None) -> str:
    return "".join(c for c in (v or "").lower() if c.isalnum())


def _norm_name(v: str | None) -> str:
    return "".join(c for c in (v or "").lower() if c.isalnum())


def _same_person(a: str | None, b: str | None) -> bool:
    """Sri Lankan names here appear both in full and as initials plus surname —
    Phase 1 reads "D. M. L. I. Dissanayake" from the signature block where the
    model reads "Dissanayake Mudiyanselage Lalith Ivan Dissanayake" from the
    operative clause. Substring matching fails on that; comparing the longest
    name token does not."""
    if not a or not b:
        return False
    na, nb = _norm_name(a), _norm_name(b)
    if na in nb or nb in na:
        return True
    longest = lambda v: max((t for t in re.findall(r"[A-Za-z]{3,}", v)), key=len, default="")
    la, lb = longest(a).lower(), longest(b).lower()
    return bool(la) and (la == lb or la in nb or lb in na)


def check(con: sqlite3.Connection) -> dict:
    """Grade the model against fields Phase 1 derived by rule.

    This is the whole point of asking the model for things we already know. The
    reference summaries in PHASE0.md were Claude-written and never hand-corrected,
    so they measure self-consistency rather than accuracy (see PHASE0.md §6).
    These three fields do not have that problem: they come from regexes over the
    source text, and they cover exactly where being wrong is expensive.
    """
    con.execute("DELETE FROM summary_check")
    rows = con.execute(
        "SELECT g.no, g.effective_from, g.enabling_act, g.authority, "
        "       s.effective_date AS m_eff, s.enabling_act AS m_act, s.authority AS m_auth, "
        "       s.audience AS m_audience, g.subject "
        "FROM gazette g JOIN gazette_summary s ON s.no=g.no").fetchall()
    from .resolve import stated_effective
    for r in rows:
        # Only compare effective dates where Phase 1 actually found one stated;
        # its fallback to the publication date is a floor, not a claim. Graded
        # against the same rule the resolver uses, so validate measures the
        # value the product shows rather than a second opinion of its own.
        stated = stated_effective(con, r["no"])
        if stated:
            con.execute(
                "INSERT OR REPLACE INTO summary_check VALUES (?,?,?,?,?)",
                (r["no"], "effective_date", stated, r["m_eff"], int(stated == r["m_eff"])))
        # Where neither side found a value there is nothing to compare, so the
        # row is skipped rather than counted as a disagreement. 1599/13 is a
        # full-page scan with no text layer: both correctly return nothing, and
        # scoring that as a miss would understate accuracy and hide the real
        # problem, which is that the document needs OCR.
        if r["enabling_act"] or r["m_act"]:
            con.execute("INSERT OR REPLACE INTO summary_check VALUES (?,?,?,?,?)",
                        (r["no"], "enabling_act", r["enabling_act"], r["m_act"],
                         int(_norm_act(r["m_act"]) in _norm_act(r["enabling_act"])
                             or _norm_act(r["enabling_act"]) in _norm_act(r["m_act"])
                             if r["enabling_act"] and r["m_act"] else 0)))
        if r["authority"] or r["m_auth"]:
            con.execute("INSERT OR REPLACE INTO summary_check VALUES (?,?,?,?,?)",
                        (r["no"], "authority", r["authority"], r["m_auth"],
                         int(_same_person(r["authority"], r["m_auth"]))))
        # Audience is the one field with no deterministic counterpart in the
        # text — it is not in the documents at all. What can be checked is
        # whether the model stayed inside the candidate list it was given, which
        # is the instruction most likely to be quietly disobeyed. Documents
        # whose Act has no map are skipped: there was nothing to obey, and
        # scoring them would grade our curation as the model's error.
        from .search import ground_audience
        cands = audience_candidates((r["enabling_act"] or "").replace("The ", ""), r["subject"])
        strings = json.loads(r["m_audience"] or "[]")
        if cands and strings:
            results = [ground_audience(r["enabling_act"], a, r["subject"], no=r["no"])
                       for a in strings]
            con.execute("INSERT OR REPLACE INTO summary_check VALUES (?,?,?,?,?)",
                        (r["no"], "audience_grounded", "; ".join(cands),
                         "; ".join(strings),
                         int(all(why in ("grounded", "reviewed") for _, why in results))))
    con.commit()
    out = {}
    for f in ("effective_date", "enabling_act", "authority", "audience_grounded"):
        tot = con.execute("SELECT COUNT(*) c FROM summary_check WHERE field=?", (f,)).fetchone()["c"]
        ok = con.execute("SELECT COUNT(*) c FROM summary_check WHERE field=? AND agrees=1",
                         (f,)).fetchone()["c"]
        out[f] = (ok, tot)
    return out


# ---------------------------------------------------------------------------
# Export / import.
#
# The database is gitignored and deliberately disposable: everything in it can
# be rebuilt from the listing and the PDFs — except this. Summaries are the one
# artefact that cost money and cannot be reproduced byte for byte, so they are
# exported to a tracked file. That makes the repository self-contained (clone,
# fetch the PDFs, import, and the corpus is whole with no API key at all) and it
# means a rebuilt database never pays for the same 137 documents twice.
# ---------------------------------------------------------------------------

SUMMARY_EXPORT = "data/summaries.json"

_EXPORT_COLUMNS = ("no", "model", "summary", "audience", "obligation",
                   "effective_date", "enabling_act", "authority", "tags",
                   "confidence", "notes", "generated_at",
                   "input_tokens", "output_tokens")


def export_summaries(con: sqlite3.Connection, path: str = SUMMARY_EXPORT) -> int:
    """Write every summary to a tracked JSON file.

    Sorted by gazette number and written with a stable key order, so a re-export
    after summarising one new document produces a one-record diff rather than a
    reshuffled file. The point of tracking it is to be able to read that diff.

    Merges, never prunes. A row already in the file whose summary this database
    does not hold is kept as it is. The file is the ledger of what we paid the
    model for; the database is rebuilt from scratch every night, and "not in
    tonight's database" has already once meant "a document the rebuild failed
    to re-acquire" — the export then deleted seven paid-for summaries and the
    nightly job committed the deletion. Removing a summary is a deliberate edit.
    """
    import os

    rows = {r["no"]: {c: r[c] for c in _EXPORT_COLUMNS}
            for r in con.execute(
                f"SELECT {', '.join(_EXPORT_COLUMNS)} FROM gazette_summary")}
    if os.path.exists(path):
        with open(path) as f:
            for kept in json.load(f):
                rows.setdefault(kept["no"], {c: kept.get(c) for c in _EXPORT_COLUMNS})
    out = [rows[no] for no in sorted(rows)]
    with open(path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    return len(out)


def import_summaries(con: sqlite3.Connection, path: str = SUMMARY_EXPORT,
                     overwrite: bool = False) -> dict:
    """Load exported summaries into the database.

    Skips gazettes we do not hold — the export can run ahead of a fetch — and by
    default skips ones already summarised, so importing never silently discards
    a fresher local run. `overwrite` is for restoring a database on purpose.
    """
    import os

    if not os.path.exists(path):
        return dict(loaded=0, skipped=0, unknown=0)
    with open(path) as f:
        rows = json.load(f)
    held = {r["no"] for r in con.execute("SELECT no FROM gazette")}
    have = {r["no"] for r in con.execute("SELECT no FROM gazette_summary")}
    loaded = skipped = unknown = 0
    for row in rows:
        if row["no"] not in held:
            unknown += 1
            continue
        if row["no"] in have and not overwrite:
            skipped += 1
            continue
        con.execute(
            f"INSERT OR REPLACE INTO gazette_summary ({', '.join(_EXPORT_COLUMNS)}) "
            f"VALUES ({', '.join(':' + c for c in _EXPORT_COLUMNS)})",
            {c: row.get(c) for c in _EXPORT_COLUMNS})
        loaded += 1
    con.commit()
    return dict(loaded=loaded, skipped=skipped, unknown=unknown)
