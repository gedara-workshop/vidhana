# Phase 1 — Acquisition

Scrape the IRD gazette listing, fetch every PDF, extract text, parse metadata,
and build the amendment graph. No LLM anywhere in this phase.

**Status: complete.** All 137 gazettes fetched and parsed, 0 failures, and the
amendment graph resolved into 19 rule threads.

## Running it

```bash
python3 -m vidhana init                  # create data/vidhana.db from schema.sql
python3 -m vidhana sync                  # refresh the listing (one HTTP request)
python3 -m vidhana fetch                 # fetch + parse anything not yet processed
python3 -m vidhana fetch --reparse       # re-extract from PDFs on disk, no downloads
python3 -m vidhana status                # counts, subjects, warnings, dangling edges
python3 -m vidhana show 2481/22          # one gazette and its graph edges
python3 -m vidhana chain 2500/106        # walk supersession both directions
python3 -m vidhana search "tax invoice"  # FTS5 full-text
```

Requires Python 3 (standard library only) and `poppler-utils` on PATH.

`fetch` is idempotent and resumable: it skips PDFs already on disk, sleeps 1.5s
between downloads, and keeps going past a failure rather than aborting the run.

## What it produces

```
gazettes in listing : 137
fetched + parsed    : 137
needing OCR         : 3
amendment edges     : 106  (13 pointing outside the listing)
typed dates         : 85

by subject:  income-tax 62 · vat 32 · stamp-duty 25 · other 10 · esc 5
             betting-gaming 2 · sscl 1
```

## How the Phase 0 findings are encoded

Each of these is a place where the obvious implementation is wrong. Details and
the evidence are in `PHASE0.md` and `CORPUS-NOTES.md`.

| Finding | Where it lives |
|---|---|
| Listing number is authoritative identity; the PDF header disagrees on padding | `util.normalise_no`, applied to every reference before it becomes an edge |
| Header regex must tolerate stray spaces, missing commas, em dashes, arbitrary casing | `parse.HEADER_RE` — 21/21 where the naive form gets 19/21 |
| Never take the date from the running page header (wrong in 3 of 21) | `parse.header` reads only the `No. NNNN/NN - DAY, MONTH DD, YYYY` line |
| Two legacy Sinhala encodings, neither visible to a charset check | `extract.is_legacy_sinhala`, three independent signals |
| `-layout` is required or clause numbers detach from clauses | `extract.to_text` |
| Verbs sit before *or* after a reference; a prior sentence must not leak in | `parse._relation` + `parse._current_sentence` |
| Effective dates are retroactive, plural per document, and mutable | `gazette_date` table, typed rows with the source clause |
| Audience is absent from most documents | deliberately **not** parsed here — it is a Phase 2 inference grounded on the enabling Act |
| Some content is inside images | `extract.page_report`, flags pages for OCR without doing it |
| The listing is not purely tax/VAT | `parse.subject`, classified from the Act rather than the title |

## Resolved state

The amendment graph on its own is an edge list. `resolve` turns it into the thing
a reader wants: **rule threads** — connected components over `amends`, `rescinds`
and `last_amended_by` — plus in-force status per document.

```
rule threads   : 19
in a thread    : 74
standalone     : 63
rescinded      : 17
```

A plain `cites` edge deliberately does not thread: several gazettes cite the same
depreciation-rates gazette (`1606/30`) without having anything to do with each
other.

```bash
python3 -m vidhana resolve                     # recompute, idempotent
python3 -m vidhana threads                     # list the threads
python3 -m vidhana rule 2481/22                # the whole history, with status
python3 -m vidhana rule 2481/22 --as-of 2026-09-09
```

The worked example is the one from the README:

```
rule thread #19  [vat]  2025-2026  3 documents
  2025-11-17    2463/05  rescinded   effective 2026-01-01  rescinded by 2481/22 from 2026-07-01
  2026-03-27    2481/22  in_force    effective 2026-10-01
* 2026-08-06   2500/106  in_force
current: 2500/106
```

**`2481/22` is effective 2026-10-01 — a fact stated in neither document.** It is
published with a July date; `2500/106` moves it to October and says nothing about
invoices. The resolver types the two dates in `2500/106` as `sets_effective_date`
and `replaces_effective_date` rather than treating either as its own effective
date, then propagates the former onto its target.

That makes `--as-of` answer correctly: on 2026-09-09 the new invoice format is
**not** yet in force, and on 2026-10-15 it is.

### What the resolver deliberately does not do

- **It does not merge amended text.** "Substitute paragraph (i) of item (2) of the
  Schedule" is a textual operation on a document we hold only as a PDF.
  Reconstructing consolidated text is a separate problem, probably an LLM one.
- **"In force" means "not rescinded by anything we hold"**, which is weaker than a
  legal determination. With 13 edges pointing outside the listing, a rescission we
  cannot see would not show up. Threads carrying such edges report an `unresolved`
  count, and `rule` warns on them.
- **`effective_from` falls back to the publication date** when a document states
  no effective date. That is a floor, not a truth. Every candidate date stays in
  `gazette_date` with the clause it came from.

## Deliberate non-goals

- **No OCR is performed.** Pages are flagged (`gazette.needs_ocr`) and left. Three
  documents are affected; wiring Tesseract in belongs with the extraction work in
  Phase 2, where the output has somewhere to go.
- **No audience or summary.** Both are inferences, not extractions, and both need
  the LLM pass. Phase 1 stops at what can be read off the page.
- **Dangling references are stored, not resolved.** 13 edges point at gazettes the
  IRD listing does not carry. They are kept as edges so the chain shows an honest
  end rather than a false one.

## Known limitations

- **Date typing is heuristic.** Roughly 85 typed dates across 137 documents; a
  handful are imprecise — a citation's own date following "effective from the
  same date" gets typed `effective`, and an end-of-period date in a range can be
  read as a start. The stored `context` column keeps every one auditable, and
  Phase 2 has the text to correct them.
- **`chain` walks edges, it does not resolve state.** It shows what amends what.
  Deciding which version of a rule is in force on a given date is Phase 2/3.
- **Completeness is unverified.** See `PHASE0.md` §7 — `documents.gov.lk` is
  currently unusable as a cross-check, so "we have every IRD tax gazette" remains
  an assumption.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

33 regression tests over the parsers and the resolver. Every fixture is a real string from a real
gazette, including the ones that look like typos — `Notificaiton`, `No. 2456 /02`,
`1,` for `I,` — because those are in the source documents.
