/** Shapes exported by `python3 -m vidhana export-web`. The Python side is the
 *  source of truth; these types describe what it writes, and the build fails
 *  loudly if the two drift. */

export type Standing = "current" | "amended" | "rescinded";

export interface Reference {
  to: string;
  rel: "amends" | "rescinds" | "last_amended_by";
}

export interface DatedFact {
  kind: string;
  date: string;
}

export interface Gazette {
  no: string;
  published_date: string;
  title: string;
  subject: string;
  enabling_act: string | null;
  status: string | null;
  rescinded_by: string | null;
  rescinded_from: string | null;
  effective_from: string | null;
  thread_id: number | null;
  /** `ird-listing` or `web-archive`. A document recovered from an archive must
   *  never be indistinguishable from one the department published. */
  source: string;
  source_detail: string | null;
  source_url: string;
  needs_ocr: number;
  summary: string | null;
  obligation: string | null;
  confidence: "high" | "medium" | "low" | null;
  notes: string | null;
  tags: string[];
  audience: string[];
  refs: Reference[];
  dates: DatedFact[];
  head_no: string | null;
  thread_size: number;
  /** Count of references in this rule pointing at gazettes the corpus lacks. */
  unresolved: number;
  /** The specific gazette numbers referenced but not held. */
  missing_refs: string[];
}

/** A pre-answered question about a rule. Written offline by a model from the
 *  rule's gazettes, checked deterministically against them (`vidhana/answers.py`)
 *  and reviewed in a pull request. Exported only while the rule is unchanged
 *  since it was written. */
export interface RuleQuestion {
  question: string;
  answer: string;
  cites: string[];
}

export interface Thread {
  thread_id: number;
  subject: string;
  enabling_act: string | null;
  root_no: string;
  head_no: string;
  first_date: string;
  last_date: string;
  size: number;
  unresolved: number;
  questions: RuleQuestion[];
}

export interface CorpusIndex {
  version: number;
  generated_from: string;
  counts: {
    gazettes: number;
    listed: number;
    recovered: number;
    threads: number;
    unresolved_threads: number;
  };
  gazettes: Gazette[];
  threads: Thread[];
}

export type Bodies = Record<string, string>;

/** `docs/data/health.json` — what the corpus knows about its own condition,
 *  written by `vidhana/health.py`. Deliberately carries no timestamp: it is
 *  committed, and a per-run field would make the nightly job commit nightly. */
export interface Health {
  corpus: {
    gazettes: number; listed: number; recovered: number; rescinded: number;
    rules: number; rules_with_holes: number; first: string; last: string;
  };
  validation: {
    fields: { field: string; agreed: number; compared: number }[];
    disagreements: { no: string; field: string; derived: string; model: string }[];
    reviewed: number;
  };
  confidence: Record<string, number>;
  parse_warnings: { no: string; warnings: string[] }[];
  needs_ocr: { no: string; pages: number }[];
  missing: { in_range: string[]; before_listing: number };
  answers: Record<"current" | "stale" | "failing" | "missing", number>;
}
