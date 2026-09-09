-- Vidhana schema. Shaped by Phase 0 findings; see PHASE0.md and CORPUS-NOTES.md.
--
-- Three findings drive the non-obvious parts:
--   * dates are plural and typed (effective != published != signed), so they get
--     their own table rather than columns on gazette;
--   * half the corpus amends or rescinds another gazette, so references are
--     first-class edges;
--   * the listing number and the PDF header number disagree on zero-padding, so
--     both are stored and the listing's is authoritative.

CREATE TABLE IF NOT EXISTS gazette (
    no              TEXT PRIMARY KEY,   -- normalised NNNN/NN from the LISTING (authoritative identity)
    year            INTEGER NOT NULL,
    published_date  TEXT NOT NULL,      -- ISO yyyy-mm-dd, from the listing
    title           TEXT NOT NULL,      -- listing description; often too terse to classify from
    source_url      TEXT NOT NULL,

    -- acquisition
    pdf_path        TEXT,
    pdf_sha256      TEXT,
    pdf_bytes       INTEGER,
    pages           INTEGER,
    fetched_at      TEXT,

    -- parsed from the PDF itself
    header_no       TEXT,               -- as printed; may differ in padding from `no`
    header_date     TEXT,               -- ISO; NEVER taken from the running page header
    enabling_act    TEXT,
    enabling_act_no TEXT,
    authority       TEXT,               -- signatory name
    authority_role  TEXT,               -- CGIR / Minister of Finance / ...
    subject         TEXT,               -- classified from enabling_act, not from title

    -- Where this document came from. The IRD listing is the identity source of
    -- truth, but it is demonstrably incomplete: 8 gazettes referenced by
    -- documents we hold fall inside its own covered range and are absent from
    -- ird.gov.lk entirely. Anything recovered from elsewhere must stay
    -- distinguishable from what the department itself published, because the
    -- provenance is weaker and a reader is entitled to know.
    source          TEXT NOT NULL DEFAULT 'ird-listing',  -- ird-listing | web-archive
    source_detail   TEXT,               -- archive snapshot URL, when backfilled

    -- extraction health
    text_path       TEXT,
    text_chars      INTEGER,
    needs_ocr       INTEGER NOT NULL DEFAULT 0,  -- any page with a big image and no text
    parse_warnings  TEXT,                         -- newline-separated, for triage

    -- resolved state, derived from the amendment graph (see resolve.py).
    -- Recomputed wholesale by `vidhana resolve`; never hand-edited.
    thread_id       INTEGER REFERENCES rule_thread(thread_id),
    status          TEXT,     -- in_force | rescinded | standalone
    rescinded_by    TEXT,     -- gazette number that rescinded this one
    rescinded_from  TEXT,     -- ISO date the rescission takes effect
    effective_from  TEXT      -- best single effective date; falls back to published
);

-- A rule thread is a connected component of the amendment graph: the set of
-- gazettes that between them define one rule over time. The current state of a
-- rule generally exists in no single document, which is the whole reason this
-- table exists.
CREATE TABLE IF NOT EXISTS rule_thread (
    thread_id     INTEGER PRIMARY KEY,
    label         TEXT,
    subject       TEXT,
    enabling_act  TEXT,
    root_no       TEXT,      -- earliest document in the thread
    head_no       TEXT,      -- latest document still in force
    first_date    TEXT,
    last_date     TEXT,
    size          INTEGER,   -- documents in the thread that are in the listing
    unresolved    INTEGER    -- edges pointing at gazettes the listing does not carry
);

-- Dates are per-provision, sometimes retroactive, sometimes several per document.
CREATE TABLE IF NOT EXISTS gazette_date (
    no       TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    kind     TEXT NOT NULL,   -- published | signed | effective | deadline | rescind_effective
    date     TEXT NOT NULL,   -- ISO
    context  TEXT,            -- the clause it was found in, so kind stays auditable
    PRIMARY KEY (no, kind, date, context)
);

-- The amendment graph. dst_no is normalised; it may point at a gazette not yet
-- fetched, so this is deliberately not a foreign key.
CREATE TABLE IF NOT EXISTS gazette_reference (
    src_no    TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    dst_no    TEXT NOT NULL,
    relation  TEXT NOT NULL,  -- amends | rescinds | last_amended_by | cites
    raw       TEXT,           -- literal text, for auditing a wrong edge
    PRIMARY KEY (src_no, dst_no, relation)
);

CREATE TABLE IF NOT EXISTS gazette_page (
    no              TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    page            INTEGER NOT NULL,
    chars           INTEGER NOT NULL,
    max_image_width INTEGER NOT NULL DEFAULT 0,
    needs_ocr       INTEGER NOT NULL DEFAULT 0,
    ocr_chars       INTEGER,   -- NULL until OCR has run on this page
    PRIMARY KEY (no, page)
);

CREATE INDEX IF NOT EXISTS idx_gazette_thread    ON gazette(thread_id);
CREATE INDEX IF NOT EXISTS idx_gazette_status    ON gazette(status);
CREATE INDEX IF NOT EXISTS idx_gazette_subject   ON gazette(subject);
CREATE INDEX IF NOT EXISTS idx_gazette_published ON gazette(published_date);
CREATE INDEX IF NOT EXISTS idx_ref_dst           ON gazette_reference(dst_no);
CREATE INDEX IF NOT EXISTS idx_date_kind         ON gazette_date(kind, date);

-- Full-text over the cleaned English text, plus the Phase 2 summary.
--
-- The summary is indexed as its own column rather than appended to the body,
-- because it needs a different weight: it is plain English written to be read,
-- while the body is statutory prose where the searched term is often incidental
-- boilerplate. See search.py for the bm25 weights.
--
-- Changing these columns needs a DROP, not an ALTER — fts5 has no ADD COLUMN.
-- db.migrate() detects the drift and rebuilds; `vidhana reindex` repopulates
-- from the text already on disk, so no PDF is re-downloaded.
CREATE VIRTUAL TABLE IF NOT EXISTS gazette_fts USING fts5(
    no UNINDEXED, title, summary, body, tokenize = 'porter unicode61'
);


-- ---------------------------------------------------------------------------
-- Phase 2: LLM structuring. Kept in separate tables so a bad model run can be
-- deleted without touching anything Phase 1 derived deterministically.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gazette_summary (
    no              TEXT PRIMARY KEY REFERENCES gazette(no) ON DELETE CASCADE,
    model           TEXT NOT NULL,
    summary         TEXT,     -- plain English, 2-4 sentences
    audience        TEXT,     -- JSON array, grounded on the enabling Act
    obligation      TEXT,     -- obligation | information
    effective_date  TEXT,     -- as the model read it; checked against Phase 1
    enabling_act    TEXT,     -- ditto
    authority       TEXT,     -- ditto
    tags            TEXT,     -- JSON array
    confidence      TEXT,     -- high | medium | low, model's own
    notes           TEXT,     -- anything the model flags as unclear
    generated_at    TEXT,
    input_tokens    INTEGER,
    output_tokens   INTEGER
);

-- Accuracy check: the model re-reads fields Phase 1 already derives by rule.
-- Disagreement is a real signal and needs no hand-written reference summaries.
CREATE TABLE IF NOT EXISTS summary_check (
    no             TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    field          TEXT NOT NULL,
    deterministic  TEXT,
    model_value    TEXT,
    agrees         INTEGER NOT NULL,
    PRIMARY KEY (no, field)
);

CREATE INDEX IF NOT EXISTS idx_check_agrees ON summary_check(field, agrees);


-- Batch API jobs. The Batch API is half price and runs server-side in parallel,
-- but it is asynchronous (up to a 24h window), so a job has to survive process
-- restarts — hence a table rather than an in-memory handle.
CREATE TABLE IF NOT EXISTS batch_job (
    id              TEXT PRIMARY KEY,   -- OpenAI batch id
    model           TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    status          TEXT,
    n_requests      INTEGER,
    input_file_id   TEXT,
    output_file_id  TEXT,
    collected_at    TEXT,
    n_collected     INTEGER,
    n_failed        INTEGER
);


-- ---------------------------------------------------------------------------
-- Phase 3: search facets.
--
-- The model's `tags` and `audience` come back as free text, and measured over
-- the real corpus that text is nearly all singletons: 225 of 319 distinct tags
-- are used exactly once, and 95 of 105 audience strings are unique. They are
-- descriptive, not navigational, so they are normalised into these tables
-- rather than filtered on as stored. Both are derived from gazette_summary and
-- are rebuilt wholesale by `vidhana reindex`; never hand-edited.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gazette_tag (
    no    TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    tag   TEXT NOT NULL,   -- normalised through search.TAG_ALIAS
    raw   TEXT NOT NULL,   -- as the model wrote it, kept so drift stays visible
    PRIMARY KEY (no, tag)
);
CREATE INDEX IF NOT EXISTS idx_tag ON gazette_tag(tag);

-- Audience is grounded on the enabling Act (see structure.ACT_AUDIENCE): the
-- model may only narrow within the Act's candidates. `coarse` is the candidate
-- a model string grounded to, and is what search filters on. A NULL coarse
-- means the string did not ground to its Act's map — which is the invented-
-- audience signal, so it is recorded rather than dropped.
CREATE TABLE IF NOT EXISTS gazette_audience (
    no        TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    audience  TEXT NOT NULL,   -- the model's own string, verbatim
    coarse    TEXT,            -- ACT_AUDIENCE candidate it grounded to, or NULL
    PRIMARY KEY (no, audience)
);
CREATE INDEX IF NOT EXISTS idx_audience_coarse ON gazette_audience(coarse);


-- ---------------------------------------------------------------------------
-- Phase 4: alerts.
--
-- Events are *derived* from the corpus, not accumulated as it changes: "2500/106
-- amends 2481/22" is a fact about the data, true whenever it is asked, so
-- deriving it is idempotent and a missed run loses nothing. The only thing that
-- cannot be re-derived is when we first saw it, which is what this table pins —
-- so a feed entry keeps its identity and timestamp across runs instead of
-- churning every time the pipeline is re-run.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gazette_event (
    event_id     TEXT PRIMARY KEY,  -- kind:no:target, stable across runs
    kind         TEXT NOT NULL,     -- published | amends | rescinds | effective_change
    no           TEXT NOT NULL REFERENCES gazette(no) ON DELETE CASCADE,
    target_no    TEXT,              -- the gazette acted on, for the relation kinds
    event_date   TEXT NOT NULL,     -- publication date of `no`; the feed orders on this
    detected_at  TEXT NOT NULL      -- first run that saw it; never rewritten
);
CREATE INDEX IF NOT EXISTS idx_event_date ON gazette_event(event_date DESC);
