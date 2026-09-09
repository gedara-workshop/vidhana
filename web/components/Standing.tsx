import type { Gazette } from "@/lib/types";
import { formatDate, standingOf } from "@/lib/standing";

/* The qualifier system, expressed without colour.
 *
 * The rule survives from the earlier design: state is a mark you recognise,
 * only the consequence gets words, and each caveat attaches to the claim it
 * weakens. What changed is the expression — a ruled mono mark instead of a
 * tinted pill, italics instead of a coloured line, opacity ranking the three
 * states rather than encoding them. The word is always present, so nothing
 * here depends on seeing a hue. */

export function Mark({ g, asOf }: { g: Gazette; asOf?: string | null }) {
  const s = standingOf(g, asOf);
  return <span className={`mark mark-${s.kind}`}>{s.pill}</span>;
}

export function Consequence({ g, asOf }: { g: Gazette; asOf?: string | null }) {
  const s = standingOf(g, asOf);
  if (!s.consequence) return null;
  return <p className="conseq mt-[6px] text-[15px]">{s.consequence}</p>;
}

export function WarnIcon({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden
         className="shrink-0">
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
      <path d="M12 9v4" /><path d="M12 17h.01" />
    </svg>
  );
}

/** Missing history. A dashed border rather than a colour — the same visual
 *  logic the timeline uses for a document it does not hold. */
export function GapTag({ missing }: { missing: string[] }) {
  if (!missing.length) return null;
  return (
    <span className="tag tag-warn"
          title="A change made by a gazette we do not hold would not appear here.">
      {missing.length} gazette{missing.length > 1 ? "s" : ""} missing from source
    </span>
  );
}

export function MetaRow({ g, missing }: { g: Gazette; missing: string[] }) {
  return (
    <div className="mt-[10px] flex flex-wrap items-center gap-[10px]">
      <span className="mono text-[11.5px] opacity-50">{formatDate(g.published_date)}</span>
      <span className="tag">{g.subject}</span>
      {g.thread_size > 1 && <span className="tag">{g.thread_size} in this rule</span>}
      <GapTag missing={missing} />
      {g.confidence && g.confidence !== "high" && (
        <span className="tag">summary · {g.confidence} confidence</span>
      )}
      {g.source !== "ird-listing" && (
        <span className="tag" title="Not in the IRD listing; recovered from the Internet Archive">
          recovered
        </span>
      )}
    </div>
  );
}
