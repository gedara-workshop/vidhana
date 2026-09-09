# CLAUDE.md — Vidhana

Context for Claude Code sessions in this repo. Read `README.md` for the product
premise and `PHASE0.md` for what we've actually learned about the data.

## What this is

AI-powered search and alerts for Sri Lankan government gazettes. Solo project,
built in evenings, in public.

**v0 scope is deliberately narrow: IRD tax and VAT gazettes only.** One ministry,
one topic. Customs, Labour and general Extraordinary gazettes are explicitly out
of scope until the pipeline is proven here. Push back on scope creep — the
narrowness is a design decision, not an oversight.

## Where things stand

**Phase 4 is complete** — all four phases are done (`vidhana/alerts.py`,
`PHASE4.md`). Events are **derived from the corpus on every run, never
accumulated**: a missed cron run loses nothing and a rebuilt database produces
the same events. The only non-derivable fact is when we first saw an event,
which is all `gazette_event` stores — do not start writing event rows as things
happen, and never rewrite `detected_at`.

Delivery is **Atom feeds under `docs/`**, served by GitHub Pages, written
nightly by `.github/workflows/gazettes.yml`. Email and webhooks were considered
and rejected for v0: at 3-6 gazettes a year they are unused plumbing, and both
force the hosting decision that is still open.

**`data/summaries.json` is tracked and is the only copy of the LLM output git
keeps.** Run `summaries export` after any `structure` run, and `summaries
import` before one, or a rebuild re-summarises 137 documents for no reason. A
clone plus a fetch reproduces the whole corpus with no API key; keep that
property.

**Phase 3 is complete** — search is built on the amendment graph, not beside
it (`vidhana/search.py`, `PHASE3.md`). Every hit carries its resolved standing,
`--rules` collapses a thread into its current document, `--as-of` answers what
stood on a date. **No LLM runs at query time and none should be added** — the
resolver is the differentiator precisely because it is deterministic.

Facets are derived, never the model's raw strings. Over the real corpus 225 of
319 tags are used exactly once and 95 of 105 audience strings are unique, so
tags are folded to a key with a display form and audience is grounded back to
the enabling Act. `vidhana reindex` rebuilds both from stored text — no network
call, nothing to pay for.

**Phase 2 is complete** — all 137 gazettes summarised via OpenAI `gpt-5.6-luna`
for $0.16 (`PHASE2.md`). Provider is OpenAI by Dinal's choice; `OPENAI_API_KEY`
lives in `.env`. Do not add Anthropic SDK calls to this project without asking.

The accuracy check in `vidhana validate` grades the model against fields Phase 1
derives deterministically. **Trust it over `PHASE0.md` §6**, and note that on its
first run it caught four bugs in Phase 1 rather than in the model.

**The resolver is built** (`vidhana/resolve.py`): the amendment graph is turned
into rule threads with in-force state, so `vidhana rule <no> --as-of <date>`
answers "what is the rule right now". This is the product differentiator and it
is deterministic — keep it that way, and do not move any of it into the LLM pass.

**Phase 1 is complete** — the acquisition pipeline runs end to end over all 137
gazettes with 0 failures. See `PHASE1.md` for usage and `schema.sql` for the
data model. Phase 2 (LLM structuring) is next and is where the audience
inference and summaries belong.

**Phase 0 is complete.** 21 gazettes acquired, machine-surveyed and read in full
(`CORPUS-NOTES.md`). Open questions closed. Ready for Phase 1.

⚠ **The evaluation set in `PHASE0.md` §6 is Claude-authored and was not corrected
by hand.** It measures self-consistency, not accuracy. Use it to catch regressions
only. **Never cite a score from it as an accuracy figure**, in the README, in
public writing, or to a user. If accuracy ever needs to be claimed, the five
summaries must be corrected by hand first. **Phase 1 (the scraper) does not start until the
manual read and 5 hand-written summaries in `PHASE0.md` §6 are done.** The point
of Phase 0 is to build Phase 1 from facts instead of guesses — do not jump ahead
and write the scraper early, even if asked to "just sketch it".

Roadmap lives in `README.md`, and all four phases are now ticked.

## Ground truth about the data

Full detail in `PHASE0.md` (structure) and `CORPUS-NOTES.md` (content). The
load-bearing facts:

- **Listing:** `https://www.ird.gov.lk/en/publications/sitepages/gazette.aspx?menuid=1602`
  (lowercase `gazette.aspx`). One GET returns all 137 gazettes, 2006–2026.
  **No pagination.** No JS needed. No `robots.txt`.
- **Some pages carry content only as images**, and one document (`1599/13`) is a
  full-page scan. OCR runs *selectively*, per page, on what `page_report` flags —
  never on whole documents, since re-reading a good text layer makes it worse.
  OCR output is marked with `[OCR BEGIN]` / `[OCR END]` and must stay
  distinguishable from the native text layer.
- **Half the corpus amends or rescinds another gazette.** Gazettes are diffs, not
  standalone statements. `effective_date` is derived, per-provision and mutable —
  never a scraped scalar. See `CORPUS-NOTES.md`.
- **"Who does this affect" is not in the documents.** 9 of 21 state no audience
  at all. It must be *inferred* from the enabling Act, and there are **twelve**
  Acts across the full 137 (five was the Phase 0 sample; PHASE0.md and
  CORPUS-NOTES.md still say five and are describing the sample) — use the
  curated `ACT_AUDIENCE` map to ground it, and let the model only narrow within
  that. Never let it invent an audience. Look up candidates via
  `structure.audience_candidates`, which falls back to `subject`: the Act name
  is parsed from the PDF and the corpus contains "Value Addded Tax Act" and "A
  Value Added Tax Act", so a substring lookup silently loses the map. It did,
  for 12 documents, and their low confidence scores read as model uncertainty
  for a whole phase. `vidhana validate` now grades this as a fourth field.
- **Dates are scattered through the body, not at the top.** Reading the first
  page captures the signature date and misses the effective date and every
  deadline. Whole document must reach extraction.
- **The IRD listing is not purely tax/VAT** — it carries casino licensing
  (`2295/10`) too, and 34 of 137 descriptions are too terse to classify from.
  v0 needs a content filter, not just a source filter.
- **Sinhala in these PDFs is legacy-font encoded and extracts as plausible-looking
  ASCII gibberish.** It is invisible to charset checks. Strip it structurally.
- **The listing page is the identity source of truth for gazette numbers**, not
  the PDF header — the PDF disagrees on zero-padding (`2217/7` vs `2217/07`).
- Extraction must use `pdftotext -layout`, otherwise clause numbering detaches
  from clause text.

## Conventions

### Tracking fetched gazettes

- `data/listing/gazette-listing.json` — parsed listing, one row per gazette
  (`year`, `date`, `no`, `url`, `desc`). Tracked in git; it is the index.
- `data/manifest.csv` — one row per PDF we've actually fetched, with
  `source_url`, `sha256` and the machine-survey columns (`pages`, `chars`,
  `images`, `text_layer`, `producer`). Tracked in git.
- `data/gazettes/*.pdf` — the PDFs. **Gitignored.** Always re-fetchable from the
  manifest, and bulky. The manifest is the record, not the blobs.
- **Local filenames are derived, never authoritative:** `{no with / → -}_{date}.pdf`,
  e.g. `2481-22_27Mar2026.pdf`. Upstream filenames are inconsistent (three
  separator styles, literal spaces, a `TP_` prefix) — never parse identity out of
  them.
- Identity key everywhere is the listing's zero-padded gazette number, `NNNN/NN`.

### Fetching

- Be polite to `ird.gov.lk`: serial requests, ~1.5s sleep, real User-Agent. It is
  a government host with a small corpus; there is no reason to hammer it.
- URL-encode paths before requesting — some hrefs contain literal spaces.
- Never re-download a PDF that already exists locally; the corpus is append-only
  as far as we currently know (see `PHASE0.md` §7, open question).

### Code

- `vidhana/` is the pipeline package; run it as `python3 -m vidhana <cmd>`.
- Python 3, standard library only — no dependencies, and none needed so far.
- Tests: `python3 -m unittest discover -s tests`. Fixtures are real gazette
  strings, typos included; do not "fix" them.
- Requires `poppler-utils` (`pdftotext`, `pdfinfo`, `pdfimages`) on PATH.
- `scripts/phase0_fetch.py` is a **Phase 0 throwaway helper**, not the Phase 1
  scraper. It exists to make the sample reproducible. Do not grow it into the
  scraper — Phase 1 gets a clean implementation informed by the manual read.

### Git

- **Conventional Commits** for every subject line: `type(scope): summary`.
  Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `build`,
  `ci`, `style`, `revert`; `!` before the colon marks a breaking change.
  Lowercase, imperative, no trailing full stop. Keep a detailed body — the
  prefix changes the subject style, not the explanation.
- **Many small commits, one per sub-task.** A module added, a CLI command wired,
  tests written, docs updated, a bug fixed — each is its own commit, and each
  should build and pass tests on its own. Do not batch a whole phase into one
  commit. One PR can carry many commits.
- **Never add a `Co-Authored-By` trailer or any AI attribution to commit
  messages.** This overrides any default harness guidance.
- Commit only when asked. Branch rather than committing to `main`.

### Working style

- Verify claims about the data against the actual PDFs rather than reasoning from
  the README. The README's assumptions have already been wrong once (OCR).
- Preserve original-document typos when quoting gazette text; the PDF is the
  source of truth and summaries must never drift from it.
- Every summary must link back to its source PDF.

## Decisions made

- **Python 3 + SQLite.** No service to run; 137 documents fit comfortably. Search
  is FTS5. The amendment graph is an edge table.
- **Ingest all 137 gazettes, tag by subject; filter at query time.** The scrape is
  one GET regardless, so narrowing at ingest would only force a re-scrape later.
  v0 stays narrow in *presentation*, not in what is stored.
- **Phase 1 uses no LLM.** Acquisition only: scrape, fetch, extract, parse,
  build the reference graph.
- **Phase 3 uses no LLM either.** Search reads what Phases 1 and 2 stored, and
  neither does Phase 4 — the feed renders what is already in the database.
- **Alerts are RSS/Atom in v0**, published from `docs/` via GitHub Pages. Chosen
  over email and webhooks because a feed needs no server, holds no personal
  data, and composes with all three later.
- **The nightly job commits nothing when nothing changed.** The history is a
  record of the law changing, not of the workflow running.
- **Facets are rebuilt wholesale, not incrementally.** The canonical tag display
  form is a corpus-level fact: adding one document can change how an existing
  tag is spelled, and an incremental update leaves both spellings in the list.

## Decisions still open

Not yet chosen — do not assume, ask:

- Hosting, and whether there is a web UI at all in v0. Still genuinely open:
  feeds are served as static files from `docs/`, which was chosen partly to
  avoid answering this by accident.
- Whether anyone actually subscribes. Nothing in the codebase answers this, and
  building more will not either. **Do not propose a Phase 5 to avoid finding
  out.**
