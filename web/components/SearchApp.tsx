"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Consequence, MetaRow, StandingPill } from "@/components/Standing";
import { buildIndex, runSearch, type SearchIndex } from "@/lib/search";
import { toSlug } from "@/lib/standing";
import type { Bodies, CorpusIndex, Gazette } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const PAGE = 30;

type Status = "current" | "inforce" | "rescinded";

interface Facets {
  subject: [string, number][];
  audience: [string, number][];
  status: [string, number][];
}

/* The interactive island. Everything static — gazette pages, rule pages,
 * metadata — is rendered on the server; only the query box needs to be here.
 *
 * bodies.json is fetched once, in the background, after first paint. Until it
 * lands search covers titles and summaries, and the page says so rather than
 * silently returning fewer results. */
export default function SearchApp({
  corpus,
  facets,
}: {
  corpus: CorpusIndex;
  facets: Facets;
}) {
  const [q, setQ] = useState("");
  const [rules, setRules] = useState(false);
  const [subject, setSubject] = useState<string | null>(null);
  const [audience, setAudience] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [bodies, setBodies] = useState<Bodies | null>(null);
  const [bodiesPending, setPending] = useState(true);
  const [shown, setShown] = useState(PAGE);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const firstRun = useRef(true);

  // Restore state from the URL on mount, and keep it there — a result has to be
  // pasteable into an email, which is how a gazette reference actually travels.
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

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Sidebar
        facets={facets} counts={corpus.counts}
        subject={subject} audience={audience} status={status}
        open={filtersOpen} onToggle={() => setFiltersOpen((v) => !v)}
        onSubject={(s) => setSubject(subject === s ? null : s)}
        onAudience={(a) => setAudience(audience === a ? null : a)}
        onStatus={(s) => setStatus(status === s ? null : (s as Status))}
      />

      <div className="flex min-w-0 grow flex-col">
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 px-5 py-3 md:px-6"
             style={{ background: "var(--surface)", borderBottom: "1px solid var(--line)" }}>
          <div className="relative min-w-[220px] max-w-[520px] grow">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--dim)"
                 strokeWidth="2" strokeLinecap="round" aria-hidden
                 className="pointer-events-none absolute left-3 top-[11px]">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input
              type="search" value={q} onChange={(e) => setQ(e.target.value)}
              aria-label="Search gazettes"
              placeholder={`Search ${corpus.counts.gazettes} gazettes, full text`}
              className="w-full rounded-[7px] py-[9px] pl-9 pr-3 text-[14px]"
              style={{ background: "var(--bg)", border: "1px solid var(--line)" }}
            />
          </div>

          <div className="flex rounded-[7px] p-[2px]"
               style={{ background: "var(--bg)", border: "1px solid var(--line)" }} role="group"
               aria-label="Result grouping">
            {([["Documents", false], ["Rules", true]] as const).map(([label, val]) => (
              <button key={label} onClick={() => setRules(val)} aria-pressed={rules === val}
                      className="rounded-[5px] px-3 py-[5px] text-[12.5px] font-medium"
                      style={rules === val
                        ? { background: "var(--surface)", color: "var(--fg)", boxShadow: "var(--shadow)" }
                        : { color: "var(--dim)" }}>
                {label}
              </button>
            ))}
          </div>

          <button className="btn" aria-pressed={!!asOf}
                  onClick={() => setAsOf(asOf ? null : "2015-01-01")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" aria-hidden>
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
            </svg>
            {asOf ? `As of ${asOf}` : "As of today"}
          </button>
        </div>

        {asOf && (
          <div className="flex flex-wrap items-center gap-3 px-5 py-[10px] md:px-6"
               style={{ background: "var(--accent-soft)", borderBottom: "1px solid var(--line)" }}>
            <strong className="text-[12.5px]" style={{ color: "var(--accent)" }}>
              Showing the rule as it stood on
            </strong>
            <input type="date" value={asOf} aria-label="As-of date"
                   onChange={(e) => setAsOf(e.target.value || null)}
                   className="rounded-[6px] px-[9px] py-[5px] text-[12.5px]"
                   style={{ background: "var(--surface)", border: "1px solid var(--line)" }} />
            <span className="text-[12px]" style={{ color: "var(--dim)" }}>
              tested on the effective date, not publication
            </span>
            <button className="btn" onClick={() => setAsOf(null)}>Clear</button>
          </div>
        )}

        <div className="grow px-5 py-5 md:px-6">
          {bare ? <Hero counts={corpus.counts} onPick={(p) => {
            setQ(p.q ?? ""); setRules(!!p.rules); setAsOf(p.asOf ?? null);
            setAudience(p.audience ?? null);
          }} /> : (
            <>
              <div className="mb-3 flex flex-wrap items-baseline gap-3">
                <span className="text-[13px]" style={{ color: "var(--dim)" }}>
                  {results.length} {rules ? "rule" : "document"}{results.length === 1 ? "" : "s"}
                </span>
                {rules && (
                  <span className="chip" style={{ background: "var(--accent-soft)", color: "var(--accent)", borderColor: "transparent" }}>
                    one result per rule, answered by its current document
                  </span>
                )}
                {bodiesPending && q && (
                  <span className="chip">searching titles and summaries — full text still loading</span>
                )}
              </div>

              {results.length === 0 ? (
                <div className="rounded-[10px] p-12 text-center"
                     style={{ background: "var(--surface)", border: "1px dashed var(--line)", color: "var(--dim)" }}>
                  <b className="block text-[15px]" style={{ color: "var(--fg)" }}>
                    {q ? `Nothing matches “${q}”` : "Nothing matches these filters"}
                  </b>
                  <span className="mt-2 block text-[13px]">
                    {bodiesPending
                      ? "Full text is still loading — try again in a moment."
                      : "Every word of every gazette is searched, not just titles. All terms must appear."}
                  </span>
                </div>
              ) : (
                <>
                  <ol className="flex flex-col gap-3">
                    {results.slice(0, shown).map((g) => (
                      <li key={g.no}><ResultCard g={g} asOf={asOf} /></li>
                    ))}
                  </ol>
                  {results.length > shown && (
                    <button className="btn mt-4" onClick={() => setShown((s) => s + PAGE)}>
                      Show {Math.min(PAGE, results.length - shown)} more of {results.length}
                    </button>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultCard({ g, asOf }: { g: Gazette; asOf: string | null }) {
  return (
    <Link className="card block rounded-[10px] p-4" href={`/gazette/${toSlug(g.no)}/`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[13.5px] font-semibold">{g.no}</span>
        {g.source !== "ird-listing" && (
          <span className="chip" title="Not in the IRD listing; recovered from the Internet Archive">
            recovered
          </span>
        )}
        <span className="grow" />
        <StandingPill g={g} asOf={asOf} />
      </div>
      <h2 className="mt-2 text-[16px] font-semibold leading-snug tracking-tight">{g.title}</h2>
      <Consequence g={g} asOf={asOf} />
      {g.summary && (
        <p className="clamp-2 mt-[7px] text-[13.5px] leading-normal" style={{ color: "var(--dim)" }}>
          {g.summary}
        </p>
      )}
      <MetaRow g={g} missing={g.missing_refs} />
    </Link>
  );
}

function Hero({ counts, onPick }: {
  counts: CorpusIndex["counts"];
  onPick: (p: { q?: string; rules?: boolean; asOf?: string; audience?: string }) => void;
}) {
  const jobs = [
    { n: "1", q: "What is the rule right now?",
      how: "Search, then switch to Rules. One result per rule, answered by the document current today.",
      pick: { q: "tax invoice", rules: true } },
    { n: "2", q: "What applied back in 2015?",
      how: "Set an as-of date. Effective dates are often retroactive, so this differs from filtering by publication.",
      pick: { q: "transfer pricing", asOf: "2015-01-01" } },
    { n: "3", q: "Does this affect me?",
      how: "Filter by audience — notaries, employers, VAT-registered businesses — inferred from the enabling Act.",
      pick: { audience: "notaries" } },
  ];
  return (
    <div className="max-w-[900px] py-8">
      <h1 className="max-w-[640px] text-[34px] font-bold leading-[1.12] tracking-[-0.035em] md:text-[38px]">
        What the rule<br />actually is. Now.
      </h1>
      <p className="mt-4 max-w-[560px] text-[16px] leading-relaxed" style={{ color: "var(--dim)" }}>
        Half of these gazettes amend or rescind another one, so the current state of a rule
        frequently exists in no single document. Search returns the rule — not the documents
        that mention it.
      </p>
      <div className="mt-8 grid gap-3 md:grid-cols-3">
        {jobs.map((j) => (
          <button key={j.n} onClick={() => onPick(j.pick)}
                  className="card rounded-[10px] p-4 text-left">
            <span className="inline-flex h-[26px] w-[26px] items-center justify-center rounded-[7px] text-[12px] font-bold"
                  style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>{j.n}</span>
            <b className="mt-3 block text-[14.5px] font-semibold leading-snug">{j.q}</b>
            <span className="mt-[6px] block text-[12.5px] leading-normal" style={{ color: "var(--dim)" }}>
              {j.how}
            </span>
          </button>
        ))}
      </div>
      <div className="panel mt-8 rounded-[10px] p-5">
        <h2 className="text-[13px] font-semibold">What this cannot tell you</h2>
        <p className="mt-2 text-[12.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
          The IRD listing omits gazettes from inside its own date range — {counts.recovered} were
          recovered from the Internet Archive and are marked as such. A gazette nobody indexes,
          which rescinds one we hold, would be invisible here. Where a rule’s history has a hole,
          results say so.
        </p>
      </div>
    </div>
  );
}

function Sidebar(props: {
  facets: Facets; counts: CorpusIndex["counts"];
  subject: string | null; audience: string | null; status: Status | null;
  open: boolean; onToggle: () => void;
  onSubject: (s: string) => void; onAudience: (a: string) => void; onStatus: (s: string) => void;
}) {
  const { facets, counts } = props;
  const LABEL: Record<string, string> = {
    current: "Current documents", inforce: "In force", rescinded: "Rescinded",
  };
  const SWATCH: Record<string, string> = {
    current: "var(--ok)", inforce: "var(--ok)", rescinded: "var(--res)",
  };
  const item = (key: string, label: string, n: number, active: boolean,
                onClick: () => void, swatch?: string) => (
    <button key={key} onClick={onClick} aria-pressed={active}
            className="flex w-full items-center gap-2 rounded-[6px] px-2 py-[5px] text-left text-[12.5px]"
            style={active
              ? { background: "var(--accent-soft)", color: "var(--accent)", fontWeight: 600 }
              : undefined}>
      <span className="h-[7px] w-[7px] shrink-0 rounded-full" style={{ background: swatch ?? "transparent" }} />
      <span className="grow truncate">{label}</span>
      <span className="font-mono text-[11px] opacity-55">{n}</span>
    </button>
  );

  return (
    <aside className="shrink-0 md:sticky md:top-0 md:h-screen md:w-[236px] md:overflow-y-auto"
           style={{ background: "var(--surface)", borderRight: "1px solid var(--line)" }}>
      <div className="flex items-center gap-[9px] px-[18px] py-4">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden className="shrink-0">
          <rect x="1.5" y="1.5" width="21" height="21" rx="5" fill="var(--accent)" />
          <path d="M7 8.5h10M7 12h10M7 15.5h6" stroke="var(--surface)" strokeWidth="1.9" strokeLinecap="round" />
        </svg>
        <span>
          <b className="block text-[15px] font-bold tracking-tight">Vidhana</b>
          <span className="block text-[10.5px]" style={{ color: "var(--dim)" }}>IRD gazettes, resolved</span>
        </span>
        <button className="btn ml-auto md:hidden" onClick={props.onToggle}
                aria-expanded={props.open}>Filters</button>
      </div>

      <div className={`px-3 pb-3 ${props.open ? "" : "hidden md:block"}`}>
        <div className="mb-4">
          <div className="kicker px-2 pb-[6px]">Status</div>
          {facets.status.map(([k, n]) =>
            item(k, LABEL[k] ?? k, n, props.status === k, () => props.onStatus(k), SWATCH[k]))}
        </div>
        <div className="mb-4">
          <div className="kicker px-2 pb-[6px]">Subject</div>
          {facets.subject.map(([s, n]) =>
            item(s, s, n, props.subject === s, () => props.onSubject(s)))}
        </div>
        <div className="mb-4">
          <div className="kicker px-2 pb-[6px]">Who it affects</div>
          {facets.audience.slice(0, 8).map(([a, n]) =>
            item(a, a, n, props.audience === a, () => props.onAudience(a)))}
        </div>
        <div className="px-2 pt-3 text-[11px] leading-normal"
             style={{ color: "var(--dim)", borderTop: "1px solid var(--line)" }}>
          {counts.gazettes} gazettes · 2006–2026<br />
          {counts.recovered} recovered from the archive
        </div>
      </div>
    </aside>
  );
}
