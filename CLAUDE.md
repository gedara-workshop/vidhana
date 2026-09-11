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

**Corpus completeness is answered** (`COMPLETENESS.md`). The corpus is **144
gazettes: 137 from the IRD listing, 7 recovered from the Internet Archive**.
Load-bearing facts, all learned the hard way:

- **documents.gov.lk is offline** — the official index of Extraordinary
  Gazettes now serves an unconfigured proxy page. There is no authoritative
  enumeration to verify against, so every completeness claim is a lower bound.
- **The IRD listing omits gazettes from inside its own range** (1439–2500).
  Eight were found; seven recovered. `1680/21` is still missing.
- **`ird.gov.lk` answers `HEAD` with 404 and the same URL with 200 on `GET`.**
  Any existence check must use a ranged GET or it concludes everything is gone.
- **Never trust a gazette number parsed out of a URL.** Verify it against the
  PDF's own printed header. A near-miss URL ingested a Provincial Councils
  Elections gazette as an IRD tax one, and passed every check that existed.
- **Never swallow an archive lookup error.** A completeness check that reports
  rate-limiting as "does not exist" is worse than none — it claims to have
  looked. `archive.ArchiveUnavailable` exists for this.
- **`source` is `ird-listing` or `web-archive` and must stay visible.** A
  recovered document is never indistinguishable from one the department
  published.
- **"In force" is disclosed as conditional wherever a rule's chain has a hole**,
  in search *and* in the feed. This is not a placeholder for better data — the
  dangerous case (a gazette nobody indexes that rescinds one we hold) is
  invisible by construction, so the disclosure is permanent.

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
  building more will not either.

## The web front end

**Next.js 15 App Router + TypeScript, in `web/`.** Statically exported
(`output: "export"`) and deployed to Pages by `.github/workflows/pages.yml`.

- **The reason for the framework is SSG, not DX.** 144 gazette pages and 20
  rule pages are pre-rendered so search engines can read them; the previous
  single-page app offered a crawler nothing. Do not add routes that cannot be
  statically generated without saying what that costs.
- **`web/lib/` must agree with `vidhana/search.py`.** Same documents match,
  terms ANDed, standing identical. Ranking need not match — fts5 stems with
  porter. `tests/test_web.py` runs the TypeScript through node's type stripping
  to check this across both languages.
- **`standing()` reads the resolver's output and never recomputes it.** A
  second implementation is a second answer.
- **Run `python3 -m vidhana export-web` before building the site**;
  `scripts/copy-data.mjs` copies `docs/data` into `web/public` and fails loudly
  when it is absent.
- Gazette numbers contain a slash, so URLs use `2500-106`. The slash form stays
  the identity everywhere else.
- **The visual direction is a dense, dark-first product UI**: layered near-black
  surfaces, Space Grotesk + JetBrains Mono, 13px base, three panes. It took
  three attempts. Two quiet, document-like directions were rejected as
  characterless, and an archival one (serif on paper, no colour) was rejected
  as *too plain, too much text, no furniture, doesn't feel like an app*. The
  brief was density and structure. **Do not drift back towards a spare,
  typographic page** — it has been tried twice and rejected twice.
- **The brand is achromatic on purpose.** The only saturated colour belongs to
  the three standing states, so the thing a reader must act on is the thing
  that draws the eye. Do not introduce a brand accent colour.
- **Theme is system/light/dark**, applied by an inline script before paint.
  Keep "system" reachable.
- **`web/lib/site.ts` owns every absolute URL.** `basePath` is applied by Next
  to links and assets but *not* to sitemap or robots contents, and canonical
  tags were hardcoded to `/vidhana/` until they were routed through `url()`.
  Add a route and it must be added to `sitemapEntries` — `npm run check:sitemap`
  fails the build if a rendered page is missing from the sitemap or vice versa,
  and CI runs it before the deploy.
- **`robots.txt` at `/vidhana/robots.txt` is not honoured by crawlers.**
  robots.txt is read only at the origin root, and
  `https://gedara-workshop.github.io/robots.txt` belongs to a
  `gedara-workshop.github.io` repo that does not exist. The file is still built
  — it becomes authoritative on a custom domain — but **sitemap discovery today
  is the Search Console submission, not the file.** Do not "fix" a reported
  discovery problem by editing `robots.ts`.

## Agreed direction

**Administration is deferred, and its shape is already decided — do not build an
admin UI.** Measured over the corpus there are ~10 things a human might ever
want to correct (1 parse warning in 144, 6 validate disagreements, 3 needing
OCR, 30 non-high-confidence summaries), growing by 3-6 gazettes a year. An
admin UI would need auth and a backend, which would destroy the property that
has been load-bearing since Phase 1: no server, no hosting decision, everything
serves as static files. GitHub already is the admin surface — Actions runs the
pipeline, commits are the audit log, PRs are the review queue.

When it is time, build these three instead:

1. **`data/corrections.json`** — tracked in git, applied deterministically after
   parsing, keyed by gazette number and field, each entry carrying a reason.
   Same pattern as `data/summaries.json`. This closes a real gap: today a parse
   fix made in the database is thrown away by the next rebuild, so the only
   durable fix is changing a regex — the wrong tool for a one-off like
   `1789/09`, whose signatory is read off an address line.
2. **PR-on-warning in the nightly job** — a new gazette that is clean publishes
   itself; one with a parse warning or a low-confidence summary opens a PR and
   waits. That is the actual job an admin UI would have done.
3. **A public corpus-health page** on the Pages site — validation scores, parse
   warnings, missing gazettes, last run. No auth, no backend, and it suits
   building in public better than hiding the numbers behind a login.

**The front end is built.** A lesson worth keeping from how it went: "production
grade" meant a real application stack that can be extended, and it was first
built as dependency-free vanilla JavaScript because I inferred constraints and
then recorded my own inference here as a settled decision. **Do not do that** —
when the stack is not stated, ask.

Whatever the UI shows, it must carry the disclosures the CLI and the feed
carry: incomplete rule history, low model confidence, and archive provenance.
The resolver stays deterministic — **no LLM at query time**.
