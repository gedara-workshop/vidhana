# Phase 3 — Search

Search across the corpus that answers with the *state of a rule*, not a list of
documents that mention it. No LLM runs at query time; everything here is
deterministic and reads what Phases 1 and 2 already stored.

**Status: complete.**

```bash
python3 -m vidhana search "tax invoice"                    # ranked, with standing
python3 -m vidhana search "tax invoice" --rules            # one result per rule
python3 -m vidhana search "transfer pricing" --as-of 2015-01-01
python3 -m vidhana search "lease" --audience notaries --in-force
python3 -m vidhana facets [--min-uses N]                   # what to filter on
python3 -m vidhana reindex                                 # rebuild index + facets
```

## The problem this phase exists to solve

Searching `tax invoice` returns three documents:

| gazette | published | what it is |
|---|---|---|
| `2463/05` | 2025-11-17 | specified the tax invoice format |
| `2481/22` | 2026-03-27 | rescinded `2463/05`, set a new format from July 2026 |
| `2500/106` | 2026-08-06 | amended `2481/22`, moved the start to October 2026 |

All three match the query equally well, because they are three drafts of one
rule. Ranked by relevance alone, the *rescinded* one comes first. A reader who
takes the top hit gets a format that is no longer law, from a source that looks
authoritative.

So every hit carries its standing:

```
  2463/05  2025-11-17  [vat]  rescinded by 2481/22 from 2026-07-01
  2481/22  2026-03-27  [vat]  in force, but 2500/106 is the current document in this rule
 2500/106  2026-08-06  [vat]  current document in a 3-document rule
```

and `--rules` collapses them into the answer:

```
[vat]  3 document(s) in this rule
  current: 2500/106  2026-08-06  effective 2026-08-06
  As amended by Gazette 2500/106, the prescribed format and specifications for tax
  invoices issued by every registered person under the VAT Act apply from October…
  matched earlier in this rule: 2463/05 (2025), 2481/22 (2026)
```

A thread scores as its **best**-matching document, not the average. Amendments
are terse by nature ("for the figure '25%' substitute '30%'"), so averaging would
rank down exactly the rules that have been amended most — the ones a reader is
least able to reconstruct unaided.

## `--as-of`, and why it is not `published_date <=`

Effective dates are retroactive often enough that publication order is not
chronological order. `2316/13` was published in January 2023 and took effect in
October 2022. So `--as-of` tests `effective_from`, and excludes a document only
if a rescission had actually bitten by that date.

Asked for transfer pricing as of 2015-01-01, the corpus answers `1823/05` — not
the 2008 regulations it replaced in 2013, and not the 2018 ones not yet written.
No single document in the corpus states that.

## What is indexed

`gazette_fts` carries `title`, `summary` and `body`, weighted 6 / 4 / 1.

- **title** is the listing description and is often the most direct statement of
  what a gazette does — but 34 of 137 are too terse to classify from, so it
  cannot dominate.
- **summary** is Phase 2's plain English, written to be read. It was not indexed
  at all before this phase.
- **body** is statutory prose, where a hit is as likely to be boilerplate as
  substance — weighted lowest while still being the reason full-text exists.

fts5 has no `ALTER TABLE ... ADD COLUMN`, so adding `summary` means dropping and
recreating the index. That is safe only because it is derived twice over — body
text on disk, summaries in `gazette_summary` — so `vidhana reindex` rebuilds it
with no network call and nothing to pay for. `db.migrate_fts` detects the drift
and reports it, because an emptied index otherwise looks like an empty corpus.

## Facets: what the model returns vs what a reader can navigate

The model's `tags` and `audience` are free text, and measured over the real
corpus they are almost entirely singletons:

| | distinct values | used exactly once |
|---|---|---|
| tags | 319 | 225 |
| audience strings | 105 | 95 |

They describe a document well and navigate it badly. A facet list longer than
the corpus is not a navigation aid.

**Tags** fold to a key — an alias map for pairs no rule catches (`vat` /
`value-added-tax`, `debit-tax` / `debits-tax`), then a plural fold on the final
token only, since that is where the head noun sits. Folding every token would
merge `debits-tax` into `debit-tax` by accident. Display form is the most-used
raw variant per key, ties broken alphabetically so the facet list does not
change shape when a document is re-summarised. 319 tags → 301 keys, of which 51
are used three or more times and are the ones listed. The cut is **display
only**: rare tags still filter and still search.

**Audience** is grounded back to the enabling Act's candidate list, so 105 free
strings become 18 facets:

```
   59  income taxpayers
   36  VAT-registered businesses
   24  parties to leases, transfers and other stampable instruments
   23  notaries
   16  employers
   11  withholding agents
    …
```

This is the facet worth having, because it is the question the corpus never
answers directly — 9 of 21 gazettes in the Phase 0 sample state no audience at
all.

## What Phase 3 found in Phase 2

Building the audience facet meant checking, for the first time, whether the
model had obeyed the instruction to narrow within its Act's candidates rather
than invent. It had. What had not obeyed anything was our own curation.

**12 of 137 gazettes reached the model with no audience candidates at all.**
The prompt told each one "No audience map for this Act — infer conservatively
and set confidence low", and the model complied: all 12 came back `low`
confidence. The gap had been visible in the output the whole time, counted as
model uncertainty rather than as a missing input.

Two causes:

- **Two were lookup misses.** The Act name is parsed from the PDF and the PDF is
  not always right — the corpus contains `Value Addded Tax Act` (a typo in the
  source, which we preserve) and `A Value Added Tax Act` (a parse artifact).
  Substring matching misses both, so two plainly-VAT gazettes lost their
  candidates to a spelling mistake. `subject` is classified from the Act *and*
  the listing title and survives that, so it is now the fallback.
- **Ten were genuinely unmapped.** `CORPUS-NOTES.md` found five enabling Acts
  across the 21-document sample. The full 137 carry twelve. The seven new lists
  are read off the gazettes themselves, so they cover what the corpus actually
  contains under each Act rather than the Act's full statutory scope.

The Finance Act gets two unrelated candidates rather than one tidy line: in this
corpus it carries a departure levy and a motor vehicle concessionary levy, which
share no audience. A single "persons liable under the Finance Act" would be a
category dressed up as an audience.

Re-running those 12 documents cost **$0.0115**. All 12 came back `high`
confidence.

## Grading the audience

`vidhana validate` gains a fourth field. Audience has no deterministic
counterpart in the text — that is why it is inferred — but whether the model
stayed inside its candidate list is checkable, and it is the instruction most
likely to be disobeyed quietly, since an invented audience reads perfectly
plausibly.

```
  effective_date      53/55  agree  (96%)
  enabling_act       137/137 agree  (100%)
  authority          136/137 agree  (99%)
  audience_grounded  135/137 agree  (98%)
```

`ground_audience` returns a reason, not a boolean, because three outcomes mean
three different things:

| | meaning |
|---|---|
| `grounded` | narrowed within a candidate; `coarse` is what search filters on |
| `no-map` | the Act has no candidate list, so there was nothing to obey |
| `ungrounded` | it had a list and left it — the only finding about the model |

Collapsing the first two is exactly the mistake that let 12 missing inputs
masquerade as model uncertainty.

The 2 remaining ungrounded documents (`1778/32`, `1933/14`) are stamp-duty
gazettes whose audience drops the candidate's head noun entirely ("companies
issuing qualifying shares…", "parties to bonds and mortgages…"). Both are
arguably correct narrowings. They are left visible rather than tuned away, and
ungrounded strings are stored with a NULL `coarse` rather than dropped — they
stay searchable as text and they stay countable.

## Known limits

- **Ranking is pure relevance.** Demoting rescinded documents would hide the
  history, and the history is frequently the answer. `--in-force`, `--as-of` and
  `--rules` are where that choice belongs.
- **Search cannot produce the consolidated text of an amended rule.** It reports
  which document is current, not what the rule reads like after four amendments
  are applied to it. That is a textual operation on PDFs and remains unsolved
  (see `resolve.py`).
- **"In force" means "not rescinded by another document we hold."** 13 of 106
  graph edges point at gazettes the IRD listing does not carry, so a rescission
  we cannot see would not show up. Threads carrying such edges are marked
  `unresolved`.
- **Tag folding is deliberately shallow.** 206 of 301 keys are still used once.
  Over-merging destroys distinctions the model got right, and the long tail is a
  fact about the corpus rather than noise.
