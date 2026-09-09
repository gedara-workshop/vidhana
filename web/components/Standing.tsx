import type { Gazette } from "@/lib/types";
import { formatDate, standingOf } from "@/lib/standing";

/** State as a pill you recognise; only the consequence gets words.
 *  "In force · current" carries no consequence at all — there is nothing to
 *  act on, and a sentence there would be noise that trains readers to skip. */
export function StandingPill({ g, asOf }: { g: Gazette; asOf?: string | null }) {
  const s = standingOf(g, asOf);
  return (
    <span className={`pill pill-${s.kind}`}>
      <span className="pill-dot" aria-hidden />
      {s.pill}
    </span>
  );
}

export function Consequence({ g, asOf }: { g: Gazette; asOf?: string | null }) {
  const s = standingOf(g, asOf);
  if (!s.consequence) return null;
  const colour =
    s.kind === "rescinded" ? "var(--res)" : s.kind === "superseded" ? "var(--sup)" : "var(--dim)";
  return (
    <p className="mt-[5px] text-[13px] font-medium" style={{ color: colour }}>
      {s.consequence}
    </p>
  );
}

export function WarnIcon({ size = 11 }: { size?: number }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
      className="shrink-0"
    >
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  );
}

/** The incomplete-history disclosure. Sits with the facts rather than in the
 *  prose, because it weakens the standing claim rather than the document. */
export function GapChip({ missing }: { missing: string[] }) {
  if (!missing.length) return null;
  return (
    <span
      className="chip chip-warn"
      title="A change made by a gazette we do not hold would not appear here."
    >
      <WarnIcon />
      {missing.length} gazette{missing.length > 1 ? "s" : ""} missing from source
    </span>
  );
}

export function MetaRow({ g, missing }: { g: Gazette; missing: string[] }) {
  return (
    <div className="mt-[11px] flex flex-wrap items-center gap-2">
      <span className="font-mono text-[11.5px]" style={{ color: "var(--dim)" }}>
        {formatDate(g.published_date)}
      </span>
      <span className="chip">{g.subject}</span>
      {g.thread_size > 1 && <span className="chip">{g.thread_size} documents in rule</span>}
      <GapChip missing={missing} />
      {g.confidence && g.confidence !== "high" && (
        <span className="chip">AI summary · {g.confidence} confidence</span>
      )}
    </div>
  );
}
