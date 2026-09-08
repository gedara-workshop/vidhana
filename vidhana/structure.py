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
}

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
    text = open(g["text_path"]).read()

    act = (g["enabling_act"] or "").replace("The ", "")
    candidates = next((v for k, v in ACT_AUDIENCE.items() if k.lower() in act.lower()), None)

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
            body = open(amender["text_path"]).read()
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
        "       (SELECT MIN(date) FROM gazette_date d WHERE d.no=g.no AND d.kind='effective') AS stated_eff "
        "FROM gazette g JOIN gazette_summary s ON s.no=g.no").fetchall()
    for r in rows:
        # Only compare effective dates where Phase 1 actually found one stated;
        # its fallback to the publication date is a floor, not a claim.
        if r["stated_eff"]:
            con.execute(
                "INSERT OR REPLACE INTO summary_check VALUES (?,?,?,?,?)",
                (r["no"], "effective_date", r["stated_eff"], r["m_eff"],
                 int(r["stated_eff"] == r["m_eff"])))
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
    con.commit()
    out = {}
    for f in ("effective_date", "enabling_act", "authority"):
        tot = con.execute("SELECT COUNT(*) c FROM summary_check WHERE field=?", (f,)).fetchone()["c"]
        ok = con.execute("SELECT COUNT(*) c FROM summary_check WHERE field=? AND agrees=1",
                         (f,)).fetchone()["c"]
        out[f] = (ok, tot)
    return out
