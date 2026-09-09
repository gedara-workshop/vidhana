"use client";

import Link from "next/link";

import { formatDate, standingOf, toSlug } from "@/lib/standing";
import type { CorpusIndex, Gazette } from "@/lib/types";

/* The third pane. It answers the question the list raises — "is this still the
 * rule?" — without losing the list, because the answer is usually a comparison
 * between a document and its siblings. */
export default function DetailPane({ g, corpus, byNo, asOf, onClose, onOpen }: {
  g: Gazette | null;
  corpus: CorpusIndex;
  byNo: Map<string, Gazette>;
  asOf: string | null;
  onClose: () => void;
  onOpen: (no: string) => void;
}) {
  if (!g) {
    return (
      <aside className="pane hidden w-[380px] shrink-0 xl:block">
        <div className="flex h-full flex-col items-center justify-center px-8 text-center">
          <p className="text-[13px] font-medium">Select a document</p>
          <p className="mt-1 text-[12px] leading-relaxed" style={{ color: "var(--dim)" }}>
            Its standing, the rule it belongs to and the full amendment history open here —
            without losing your results.
          </p>
          <p className="mt-4 flex items-center gap-1 text-[11px]" style={{ color: "var(--faint)" }}>
            <span className="kbd">j</span><span className="kbd">k</span> to move
            <span className="mx-1">·</span><span className="kbd">/</span> to search
          </p>
        </div>
      </aside>
    );
  }

  const s = standingOf(g, asOf);
  const members = g.thread_id
    ? corpus.gazettes.filter((m) => m.thread_id === g.thread_id)
        .sort((a, b) => (a.published_date < b.published_date ? -1 : 1))
    : [g];
  const missing = [...new Set(members.flatMap((m) => m.missing_refs))].sort();
  const head = g.head_no ? byNo.get(g.head_no) : undefined;

  return (
    <aside className="pane fixed inset-0 z-30 flex w-full flex-col md:static md:z-auto
                      md:w-[360px] md:shrink-0 xl:w-[380px]">
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2"
           style={{ borderColor: "var(--line)" }}>
        <span className="mono text-[13px] font-semibold">{g.no}</span>
        <span className={`state state-${s.kind}`}>{s.pill}</span>
        <span className="grow" />
        <button className="btn" onClick={onClose} aria-label="Close detail">✕</button>
      </div>

      <div className="min-h-0 grow overflow-y-auto px-3 py-3">
        <h2 className="text-[15px] font-semibold leading-snug">{g.title}</h2>
        {s.consequence && (
          <p className="mt-[6px] text-[12.5px] font-medium"
             style={{ color: s.kind === "rescinded" ? "var(--res)" : "var(--sup)" }}>
            {s.consequence}
          </p>
        )}

        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-[5px] text-[12px]">
          <dt style={{ color: "var(--faint)" }}>Published</dt>
          <dd className="mono">{formatDate(g.published_date)}</dd>
          <dt style={{ color: "var(--faint)" }}>Effective</dt>
          <dd className="mono">{formatDate(g.effective_from) || "—"}</dd>
          <dt style={{ color: "var(--faint)" }}>Act</dt>
          <dd>{g.enabling_act ?? "—"}</dd>
          <dt style={{ color: "var(--faint)" }}>Affects</dt>
          <dd>{g.audience.length ? g.audience.join("; ") : "not stated"}</dd>
          <dt style={{ color: "var(--faint)" }}>Source</dt>
          <dd>{g.source === "ird-listing" ? "IRD listing" : "Internet Archive"}</dd>
        </dl>

        {g.summary && (
          <>
            <p className="sec mt-4">Summary</p>
            <p className="mt-1 text-[12.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
              {g.summary}
            </p>
            {g.confidence && g.confidence !== "high" && (
              <p className="mt-1 text-[11px]" style={{ color: "var(--sup)" }}>
                Generated with {g.confidence} confidence — read the gazette before relying on it.
              </p>
            )}
          </>
        )}

        {missing.length > 0 && (
          <div className="mt-4 rounded-[6px] px-[10px] py-2 text-[11.5px] leading-relaxed"
               style={{ background: "var(--sup-bg)", color: "var(--sup)" }}>
            <strong>History incomplete.</strong>{" "}
            <span className="mono">{missing.join(", ")}</span>{" "}
            {missing.length > 1 ? "are" : "is"} referenced but not held, so a change made by a
            gazette we do not have would not appear below.
          </div>
        )}

        {members.length > 1 && (
          <>
            <p className="sec mt-4 mb-2">
              The rule, over time · {members.length} documents
            </p>
            <div className="tl">
              {members.map((m) => {
                const ms = standingOf(m, asOf);
                const here = m.no === g.no;
                const current = head ? m.no === head.no : false;
                return (
                  <button key={m.no} onClick={() => onOpen(m.no)}
                          className="relative block w-full rounded-[5px] px-2 py-[6px] text-left hover:bg-[var(--raised)]">
                    <span className={`tl-node ${current ? "tl-node-current" : ""} ${here ? "tl-node-here" : ""}`} />
                    <span className="flex items-center gap-2">
                      <span className="mono text-[11.5px]"
                            style={{ fontWeight: current ? 600 : 400 }}>{m.no}</span>
                      <span className="mono text-[10.5px]" style={{ color: "var(--faint)" }}>
                        {formatDate(m.published_date)}
                      </span>
                      {here && <span className="tag">here</span>}
                    </span>
                    <span className="clamp-1 mt-[2px] block text-[11.5px]"
                          style={{ color: current ? "var(--ok)" : "var(--dim)" }}>
                      {current ? "the rule now" : ms.pill.toLowerCase()} · {m.title}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        )}
      </div>

      <div className="flex shrink-0 gap-2 border-t px-3 py-2" style={{ borderColor: "var(--line)" }}>
        <a className="btn btn-primary grow justify-center" href={g.source_url} rel="noopener">
          Open PDF
        </a>
        <Link className="btn grow justify-center" href={`/gazette/${toSlug(g.no)}/`}>
          Full page
        </Link>
      </div>
    </aside>
  );
}
