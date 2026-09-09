"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Consequence, Mark, MetaRow } from "@/components/Standing";
import { buildIndex, runSearch, type SearchIndex } from "@/lib/search";
import { toSlug } from "@/lib/standing";
import type { Bodies, CorpusIndex, Gazette } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const PAGE = 25;

type Status = "current" | "inforce" | "rescinded";

interface Facets {
  subject: [string, number][];
  audience: [string, number][];
  status: [string, number][];
}

/* One column, ruled. The dashboard sidebar is gone: facets sit in a strip
 * under the search line the way a newspaper sets its sections, which keeps the
 * page a single measure and the eye on one thing at a time. */
export default function SearchApp({ corpus, facets }: { corpus: CorpusIndex; facets: Facets }) {
  const [q, setQ] = useState("");
  const [rules, setRules] = useState(false);
  const [subject, setSubject] = useState<string | null>(null);
  const [audience, setAudience] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [bodies, setBodies] = useState<Bodies | null>(null);
  const [bodiesPending, setPending] = useState(true);
  const [shown, setShown] = useState(PAGE);
  const [openFacets, setOpenFacets] = useState(false);
  const firstRun = useRef(true);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ(p.get("q") ?? "");
    setRules(p.get("mode") === "rules");
    setSubject(p.get("subject"));
    setAudience(p.get("audience"));
    setStatus((p.get("status") as Status | null) ?? null);
    setAsOf(p.get("as_of"));
  }, []);

  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; }
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (rules) p.set("mode", "rules");
    if (subject) p.set("subject", subject);
    if (audience) p.set("audience", audience);
    if (status) p.set("status", status);
    if (asOf) p.set("as_of", asOf);
    const qs = p.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
    setShown(PAGE);
  }, [q, rules, subject, audience, status, asOf]);

  useEffect(() => {
    let live = true;
    fetch(`${BASE}/data/bodies.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((b: Bodies) => { if (live) { setBodies(b); setPending(false); } })
      .catch(() => { if (live) setPending(false); });
    return () => { live = false; };
  }, []);

  const byNo = useMemo(
    () => new Map(corpus.gazettes.map((g) => [g.no, g])), [corpus.gazettes]);
  const index: SearchIndex = useMemo(
    () => buildIndex(corpus.gazettes, bodies), [corpus.gazettes, bodies]);
  const results = useMemo(
    () => runSearch(corpus.gazettes, index, byNo, {
      query: q, rules, subject, audience, status, asOf }),
    [corpus.gazettes, index, byNo, q, rules, subject, audience, status, asOf]);

  const bare = !q && !subject && !audience && !status && !asOf;
  const filters: [string, string | null, () => void][] = [
    [subject ?? "", subject, () => setSubject(null)],
    [audience ?? "", audience, () => setAudience(null)],
    [status ?? "", status, () => setStatus(null)],
  ];

  return (
    <main className="mx-auto max-w-[820px] px-6 pb-10 pt-9 md:px-14">
      <label className="label block" htmlFor="q">Search</label>
      <input
        id="q" type="search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="tax invoice"
        className="field mt-[6px]"
      />

      {/* the section strip */}
      <div className="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-2 border-b pb-3"
           style={{ borderColor: "var(--hair)" }}>
        <button className="label !opacity-100 underline underline-offset-4"
                style={{ textDecorationColor: rules ? "currentColor" : "transparent" }}
                aria-pressed={rules} onClick={() => setRules(!rules)}>
          {rules ? "By rule" : "By document"}
        </button>
        <button className="label !opacity-100 underline underline-offset-4"
                style={{ textDecorationColor: asOf ? "currentColor" : "transparent" }}
                aria-pressed={!!asOf} onClick={() => setAsOf(asOf ? null : "2015-01-01")}>
          {asOf ? `As of ${asOf}` : "As of today"}
        </button>
        <button className="label !opacity-100 underline underline-offset-4"
                style={{ textDecorationColor: openFacets ? "currentColor" : "transparent" }}
                aria-expanded={openFacets} onClick={() => setOpenFacets(!openFacets)}>
          Narrow
        </button>
        <span className="grow" />
        <span className="mono text-[11.5px] opacity-50">
          {results.length} {rules ? "rule" : "document"}{results.length === 1 ? "" : "s"}
          {bodiesPending && q ? " · full text still loading" : ""}
        </span>
      </div>

      {asOf && (
        <div className="mt-3 flex flex-wrap items-center gap-3 border-b pb-3"
             style={{ borderColor: "var(--hair)" }}>
          <span className="text-[15px] italic">Showing the rule as it stood on</span>
          <input type="date" value={asOf} aria-label="As-of date"
                 onChange={(e) => setAsOf(e.target.value || null)}
                 className="mono border-b bg-transparent pb-[2px] text-[13px]"
                 style={{ borderColor: "var(--ink)" }} />
          <span className="text-[13px] italic opacity-60">
            tested on the effective date, not publication
          </span>
        </div>
      )}

      {openFacets && (
        <FacetStrip
          facets={facets} subject={subject} audience={audience} status={status}
          onSubject={(s) => setSubject(subject === s ? null : s)}
          onAudience={(a) => setAudience(audience === a ? null : a)}
          onStatus={(s) => setStatus(status === s ? null : (s as Status))}
        />
      )}

      {filters.some(([, v]) => v) && (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-[13px] italic opacity-75">
          Narrowed to
          {filters.filter(([, v]) => v).map(([label, , clear]) => (
            <button key={label} className="tag not-italic" onClick={clear}
                    title="Remove this filter">{label} ✕</button>
          ))}
        </p>
      )}

      {bare ? <Opening counts={corpus.counts} onPick={(p) => {
        setQ(p.q ?? ""); setRules(!!p.rules);
        setAsOf(p.asOf ?? null); setAudience(p.audience ?? null);
      }} /> : (
        <>
          {results.length === 0 ? (
            <p className="mt-10 text-[17px] italic opacity-65">
              {q ? <>Nothing matches “{q}”.</> : "Nothing matches these filters."}{" "}
              {bodiesPending
                ? "The full text is still loading — try again in a moment."
                : "Every word of every gazette is searched, and all terms must appear."}
            </p>
          ) : (
            <>
              <ol className="mt-1">
                {results.slice(0, shown).map((g) => (
                  <li key={g.no}><Entry g={g} asOf={asOf} /></li>
                ))}
              </ol>
              {results.length > shown && (
                <button className="label !opacity-100 mt-6 underline underline-offset-4"
                        onClick={() => setShown((s) => s + PAGE)}>
                  Show {Math.min(PAGE, results.length - shown)} more of {results.length}
                </button>
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}

function Entry({ g, asOf }: { g: Gazette; asOf: string | null }) {
  return (
    <Link className="entry block py-[22px]" href={`/gazette/${toSlug(g.no)}/`}>
      <div className="flex items-baseline gap-[14px]">
        <span className="mono text-[15px] font-medium">{g.no}</span>
        <span className="grow" />
        <Mark g={g} asOf={asOf} />
      </div>
      <h2 className="mt-[7px] max-w-[640px] text-[21px] leading-[1.32]">{g.title}</h2>
      <Consequence g={g} asOf={asOf} />
      {g.summary && (
        <p className="clamp-2 mt-2 max-w-[640px] text-[14.5px] opacity-[.68]">{g.summary}</p>
      )}
      <MetaRow g={g} missing={g.missing_refs} />
    </Link>
  );
}

function FacetStrip(props: {
  facets: Facets; subject: string | null; audience: string | null; status: Status | null;
  onSubject: (s: string) => void; onAudience: (a: string) => void; onStatus: (s: string) => void;
}) {
  const LABEL: Record<string, string> = {
    current: "current documents", inforce: "in force", rescinded: "rescinded",
  };
  const group = (title: string, items: [string, number][], active: string | null,
                 pick: (k: string) => void, label?: Record<string, string>) => (
    <div>
      <p className="label">{title}</p>
      <ul className="mt-[6px]">
        {items.map(([k, n]) => (
          <li key={k}>
            <button onClick={() => pick(k)} aria-pressed={active === k}
                    className="flex w-full items-baseline gap-3 py-[3px] text-left text-[14px]"
                    style={active === k ? { fontWeight: 600 } : { opacity: 0.8 }}>
              <span className="grow truncate">{label?.[k] ?? k}</span>
              <span className="mono text-[11px] opacity-50">{n}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <div className="mt-4 grid gap-8 border-b pb-5 md:grid-cols-3"
         style={{ borderColor: "var(--hair)" }}>
      {group("Standing", props.facets.status, props.status, props.onStatus, LABEL)}
      {group("Subject", props.facets.subject, props.subject, props.onSubject)}
      {group("Who it affects", props.facets.audience.slice(0, 8), props.audience, props.onAudience)}
    </div>
  );
}

function Opening({ counts, onPick }: {
  counts: CorpusIndex["counts"];
  onPick: (p: { q?: string; rules?: boolean; asOf?: string; audience?: string }) => void;
}) {
  const jobs: [string, string, { q?: string; rules?: boolean; asOf?: string; audience?: string }][] = [
    ["What is the rule right now?",
     "Search, then read by rule. One entry per rule, answered by the document current today.",
     { q: "tax invoice", rules: true }],
    ["What applied back in 2015?",
     "Set an as-of date. Effective dates are often retroactive, so this is not the same as filtering by publication.",
     { q: "transfer pricing", asOf: "2015-01-01" }],
    ["Does this affect me?",
     "Narrow by audience — notaries, employers, VAT-registered businesses — inferred from the enabling Act.",
     { audience: "notaries" }],
  ];
  return (
    <div className="mt-9">
      <p className="max-w-[600px] text-[19px] leading-[1.55]">
        Half of these gazettes amend or rescind another one, so the current state of a rule
        frequently exists in <em>no single document</em>. Search returns the rule — not the
        documents that mention it.
      </p>
      <ol className="mt-8 border-t" style={{ borderColor: "var(--hair)" }}>
        {jobs.map(([q, how, pick], i) => (
          <li key={q} className="entry">
            <button className="w-full py-[18px] text-left" onClick={() => onPick(pick)}>
              <span className="mono mr-3 text-[12px] opacity-45">{i + 1}</span>
              <span className="text-[19px]">{q}</span>
              <span className="mt-[5px] block max-w-[580px] text-[14.5px] italic opacity-[.68]">
                {how}
              </span>
            </button>
          </li>
        ))}
      </ol>
      <p className="mt-8 max-w-[640px] text-[14px] italic leading-relaxed opacity-[.68]">
        <strong className="not-italic font-semibold">What this cannot tell you.</strong>{" "}
        The IRD listing omits gazettes from inside its own date range — {counts.recovered} were
        recovered from the Internet Archive and are marked as such. A gazette nobody indexes,
        which rescinds one we hold, would be invisible here. Where a rule’s history has a hole,
        entries say so.
      </p>
    </div>
  );
}
