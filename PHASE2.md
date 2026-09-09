# Phase 2 — Structuring

Plain-English summaries and audience inference over the corpus. This is the only
phase that calls an LLM.

**Status: complete.** All 137 gazettes summarised for **$0.16**.

## Provider and model

OpenAI, `gpt-5.6-luna` — the cheapest current-generation model, chosen
deliberately. The key lives in `.env` as `OPENAI_API_KEY` (gitignored).

Cost is not a meaningful constraint at this scale. The whole corpus is 352k input
and 77k output tokens. Reprocessing everything from scratch costs 16 cents, and
steady state is 3-6 new gazettes a year.

```bash
python3 -m vidhana structure [--limit N] [--only 2481/22] [--force] [--model M]
python3 -m vidhana validate                  # grade against Phase 1
python3 -m vidhana batch submit [--dry-run]  # half price, async, parallel
python3 -m vidhana batch status  [ID]
python3 -m vidhana batch collect [ID]
```

`batch --dry-run` builds the request and reports prompt size and schema without
submitting or spending anything.

## What the model is asked for, and what it isn't

Only two things here cannot be derived deterministically, and they are the reason
this phase exists:

- **the plain-English summary**, because gazettes are drafted as textual surgery
  ("substitute paragraph (i) of item (2) of the Schedule");
- **the affected audience**, which Phase 0 found is simply absent from most
  documents — 9 of 21 sampled state no audience at all.

Audience is **grounded on the enabling Act**, not inferred freely. The corpus rests
on five Acts, so `ACT_AUDIENCE` supplies candidates and the prompt tells the model
to narrow within them and never invent an audience the Act does not bind. Where
there is no map, it is told to lower confidence rather than guess.

Everything else the model returns — effective date, enabling Act, authority — is
already known from Phase 1 and is asked for **only so it can be checked**.

## Accuracy: measured, not asserted

`PHASE0.md` §6's reference summaries are Claude-written and were never
hand-corrected, so they measure self-consistency rather than accuracy. This check
does not have that problem: it compares the model against fields Phase 1 derives
by regex from the source text, and it covers exactly where being wrong is
expensive.

```
effective_date    53/55  agree  (96%)
enabling_act     137/137 agree  (100%)
authority        136/137 agree  (99%)
```

Two deliberate exclusions keep these honest: effective dates are only graded where
Phase 1 found one **stated** (its fallback to the publication date is a floor, not
a claim), and rows where neither side found a value are skipped rather than
counted as misses.

### The validation caught bugs in Phase 1, not the model

This was the surprise. The first run scored 83% on effective dates and 81% on
authority. Nearly every disagreement was **Phase 1 being wrong**:

| Bug | Effect | Fix |
|---|---|---|
| `effective_from` took `MIN()` over every date typed `effective` | `2217/07` resolved to 2018-12-31 — the date of the gazette it *rescinds* — instead of 2020-04-01 | don't type a date as `effective` when it directly follows a gazette citation |
| Bracketed historical asides were read as operative | `2316/13` resolved to 2012-01-01 from "[With effect from 01.01.2012 ...]" instead of 2022-10-01 | skip dates inside square brackets |
| `ROLE_RE` knew only CGIR and Minister of Finance | 26 of 137 signatories lost; gazettes 2006-2015 are signed by the **President** under Article 44(2), and the Tax Appeals Commission rules by its Chairman | add those roles, and accept `President.` as well as `President,` |
| Name matching was substring-only | "D. M. L. I. Dissanayake" vs "Dissanayake Mudiyanselage Lalith Ivan Dissanayake" scored as a miss | compare the longest name token |

Those effective-date bugs mattered beyond the score: `effective_from` feeds the
resolver, so `vidhana rule --as-of` was giving wrong answers for those documents.

## Amendment context

The first run summarised `2481/22` as "From 1 July 2026...", faithful to the
document but wrong in practice — `2500/106` moved it to October. The model flagged
this itself:

> "Gazette 2500/106 is stated to amend this Gazette, but that later document was
> not provided."

Amending documents are now supplied in the prompt. The result:

> "**As amended by Gazette 2500/106, from 1 October 2026** VAT-registered
> businesses must issue tax invoices using the specified format..."

while `effective_date` still records **2026-07-01**, the date *this* document
states, with `notes` explaining the divergence. That split is deliberate: the
field stays faithful to the source PDF so the two cannot drift, and the prose
tells the reader the rule as it actually stands.

## Remaining disagreements (4 of 328 comparisons)

None is a clear model error:

- `1868/10` — Phase 1 says 2011-01-01, model says 2014-01-01. **Genuine ambiguity**:
  the document takes effect 01.01.2014 "subject to the specific dates mentioned in
  the Schedule", and the Schedule contains a real 01.01.2011 provision. Earliest-
  anything versus main-operative-date; both defensible.
- `1478/08` — "with effect from the **mid night of** 31st December 2006". The model
  reads 2007-01-01, Phase 1 reads the literal 2006-12-31. Ordinary English is
  ambiguous about which side of midnight is meant.
- `1789/09` — Phase 1 picked up an address line as the signatory. A residual
  name-extraction bug, small enough to leave documented rather than over-fit.
- `1599/13` — the full-page scan. Phase 1 has no text at all; the model returned an
  Act inferred from the listing title **and set confidence to low**, noting the
  text was not supplied. Correct behaviour under the circumstances; the real fix
  is OCR.

## OCR

Six pages across three documents carried content only as images. They are now
rendered at 300dpi and read with tesseract, and the result is appended under
explicit `[OCR BEGIN]` / `[OCR END]` markers rather than merged into the body —
OCR here is materially noisier than the text layer ("ae virtue" for "BY virtue"),
so it has to stay distinguishable.

| Gazette | Pages | Recovered |
|---|---|---|
| `1599/13` | 1 | 1,739 chars — the document had **none** at all |
| `2064/59` | 2, 5 | 1,495 + 1,920 |
| `2414/14` | 5, 6, 7 | 1,961 + 682 + 837 |

`1599/13` is the clearest win. It is a 2009 full-page scan that yielded a single
byte of text; Phase 1 could parse nothing from it. It now yields its enabling Act
and its signatory (Sahampathi Angammana), and the summary traces its whole chain
— amended by `1604/14`, then repealed and replaced by `1704/18` — while correctly
reporting low confidence and noting that the OCR contains errors.

`2414/14` is the other one worth noting: its item 9 read "Format of the Tax
Clearance Application" followed by nothing at all, because the form was an image.
The Tax Calculation table is now readable.

## Known limitations

- **Self-reported confidence is not calibrated.** It is a triage hint, not a
  measurement. It does move in the right direction on OCR'd documents — both
  `1599/13` and `2064/59` came back `low` — but that is an observation, not a
  guarantee.
- **OCR text is noisier than the text layer** and is marked as such. It is good
  enough for summarisation and for parsing the header block; it should not be
  quoted verbatim as if it were the source.
- **`_tidy` still lets some OCR noise through** — the legacy-Sinhala line survives
  as consonant soup on some pages. Harmless in context, since the markers say the
  block is machine-read.
