/** Shapes exported by `python3 -m vidhana export-web`. The Python side is the
 *  source of truth; these types describe what it writes, and the build fails
 *  loudly if the two drift. */

export type Standing = "current" | "superseded" | "rescinded";

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
