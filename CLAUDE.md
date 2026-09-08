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

Roadmap lives in `README.md`. Note that `README.md` currently ends mid-sentence in
the Phase 1 bullet; it needs finishing.

## Ground truth about the data

Full detail in `PHASE0.md` (structure) and `CORPUS-NOTES.md` (content). The
load-bearing facts:

- **Listing:** `https://www.ird.gov.lk/en/publications/sitepages/gazette.aspx?menuid=1602`
  (lowercase `gazette.aspx`). One GET returns all 137 gazettes, 2006–2026.
  **No pagination.** No JS needed. No `robots.txt`.
- **No source PDF is a scan, but some embed rasterised form pages.** `2414/14`
  pp. 5–7 are images and extract as nothing. OCR is needed *selectively* — flag
  pages with a >1000px image and <400 chars of text, not whole documents.
- **Half the corpus amends or rescinds another gazette.** Gazettes are diffs, not
  standalone statements. `effective_date` is derived, per-provision and mutable —
  never a scraped scalar. See `CORPUS-NOTES.md`.
- **"Who does this affect" is not in the documents.** 9 of 21 state no audience
  at all. It must be *inferred* from the enabling Act, and there are only five
  Acts across the corpus — use a curated Act→audience map to ground it, and let
  the model only narrow within that. Never let it invent an audience.
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

- Python 3, standard library only so far — no dependencies added yet.
- Requires `poppler-utils` (`pdftotext`, `pdfinfo`, `pdfimages`) on PATH.
- `scripts/phase0_fetch.py` is a **Phase 0 throwaway helper**, not the Phase 1
  scraper. It exists to make the sample reproducible. Do not grow it into the
  scraper — Phase 1 gets a clean implementation informed by the manual read.

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

## Decisions still open

Not yet chosen — do not assume, ask:

- Which LLM handles structuring, and whether summarisation is one pass or two.
  (Phase 2. Load the `claude-api` skill before recommending a model.)
- Hosting, and whether there is a web UI at all in v0.
- Alert delivery mechanism (email, RSS, webhook).
