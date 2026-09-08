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
    PRIMARY KEY (no, page)
);

CREATE INDEX IF NOT EXISTS idx_gazette_thread    ON gazette(thread_id);
CREATE INDEX IF NOT EXISTS idx_gazette_status    ON gazette(status);
CREATE INDEX IF NOT EXISTS idx_gazette_subject   ON gazette(subject);
CREATE INDEX IF NOT EXISTS idx_gazette_published ON gazette(published_date);
CREATE INDEX IF NOT EXISTS idx_ref_dst           ON gazette_reference(dst_no);
CREATE INDEX IF NOT EXISTS idx_date_kind         ON gazette_date(kind, date);

-- Full-text over the cleaned English text.
CREATE VIRTUAL TABLE IF NOT EXISTS gazette_fts USING fts5(
    no UNINDEXED, title, body, tokenize = 'porter unicode61'
);
