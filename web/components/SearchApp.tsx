"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import DetailPane from "@/components/DetailPane";
import { buildIndex, runSearch, type SearchIndex } from "@/lib/search";
import { formatDate, standingOf, toSlug } from "@/lib/standing";
import type { Bodies, CorpusIndex, Gazette } from "@/lib/types";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const PAGE = 60;

type Status = "current" | "inforce" | "rescinded";

interface Facets {
  subject: [string, number][];
  audience: [string, number][];
  status: [string, number][];
}

/* Three panes: filters, results, detail. The detail opens beside the list
 * rather than navigating away, because the question people actually have —
 * "is this still the rule?" — is answered by comparing a document with its
 * siblings, and losing the list to answer it is the wrong trade.
 *
 * The static /gazette/[slug] pages still exist and are what a search engine
 * and a shared link land on. This is the workspace; those are the documents. */
export default function SearchApp({ corpus, facets }: { corpus: CorpusIndex; facets: Facets }) {
  const [q, setQ] = useState("");
  const [rules, setRules] = useState(false);
  const [subject, setSubject] = useState<string | null>(null);
  const [audience, setAudience] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [bodies, setBodies] = useState<Bodies | null>(null);
  const [pending, setPending] = useState(true);
  const [shown, setShown] = useState(PAGE);
  const [railOpen, setRailOpen] = useState(false);
  const boot = useRef(true);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ(p.get("q") ?? "");
    setRules(p.get("mode") === "rules");
    setSubject(p.get("subject"));
    setAudience(p.get("audience"));
    setStatus((p.get("status") as Status | null) ?? null);
    setAsOf(p.get("as_of"));
    setSelected(p.get("no"));
  }, []);

  useEffect(() => {
    if (boot.current) { boot.current = false; return; }
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (rules) p.set("mode", "rules");
    if (subject) p.set("subject", subject);
    if (audience) p.set("audience", audience);
    if (status) p.set("status", status);
    if (asOf) p.set("as_of", asOf);
    if (selected) p.set("no", selected);
    const qs = p.toString();
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [q, rules, subject, audience, status, asOf, selected]);

  useEffect(() => { setShown(PAGE); }, [q, rules, subject, audience, status, asOf]);

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

  // Keyboard: slash focuses search, j/k walk the list, escape clears selection.
  // A dense list is only fast if the hands stay off the mouse.
  const move = useCallback((delta: number) => {
    if (!results.length) return;
    const i = results.findIndex((g) => g.no === selected);
    const next = results[Math.max(0, Math.min(results.length - 1, i < 0 ? 0 : i + delta))];
    if (next) setSelected(next.no);
  }, [results, selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement &&
        /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (e.key === "/" && !typing) { e.preventDefault(); box.current?.focus(); return; }
      if (e.key === "Escape") { (e.target as HTMLElement)?.blur?.(); setSelected(null); return; }
      if (typing) return;
      if (e.key === "j") { e.preventDefault(); move(1); }
      if (e.key === "k") { e.preventDefault(); move(-1); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [move]);

  const active = selected ? byNo.get(selected) ?? null : null;
  const chips: [string, () => void][] = [
    ...(subject ? [[subject, () => setSubject(null)] as [string, () => void]] : []),
    ...(audience ? [[audience, () => setAudience(null)] as [string, () => void]] : []),
    ...(status ? [[status, () => setStatus(null)] as [string, () => void]] : []),
    ...(asOf ? [[`as of ${asOf}`, () => setAsOf(null)] as [string, () => void]] : []),
  ];

  return (
    <div className="flex h-full">
      {/* ── rail ─────────────────────────────────────────────────────── */}
      <aside className={`rail shrink-0 overflow-y-auto p-2 ${railOpen ? "absolute inset-y-0 left-0 z-20" : "hidden"} md:block`}>
        <FacetGroup title="Standing" items={facets.status} active={status}
          label={{ current: "Current documents", inforce: "In force", rescinded: "Rescinded" }}
          dot={{ current: "var(--ok)", inforce: "var(--ok)", rescinded: "var(--res)" }}
          onPick={(k) => setStatus(status === k ? null : (k as Status))} />
        <FacetGroup title="Subject" items={facets.subject} active={subject}
          onPick={(k) => setSubject(subject === k ? null : k)} />
        <FacetGroup title="Who it affects" items={facets.audience.slice(0, 9)} active={audience}
          onPick={(k) => setAudience(audience === k ? null : k)} />
        <div className="mt-3 border-t px-2 pt-3 text-[11px] leading-relaxed"
             style={{ borderColor: "var(--line)", color: "var(--faint)" }}>
          {corpus.counts.recovered} of {corpus.counts.gazettes} recovered from the
          Internet Archive. {corpus.counts.unresolved_threads} rule
          {corpus.counts.unresolved_threads === 1 ? " has" : "s have"} a hole in its history.
        </div>
      </aside>

      {/* ── list ─────────────────────────────────────────────────────── */}
      <section className="flex min-w-0 grow flex-col">
        <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2"
             style={{ borderColor: "var(--line)" }}>
          <button className="btn md:hidden" onClick={() => setRailOpen(!railOpen)}
                  aria-pressed={railOpen}>Filters</button>
          <div className="relative min-w-0 grow">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--faint)"
                 strokeWidth="2" strokeLinecap="round" aria-hidden
                 className="pointer-events-none absolute left-[10px] top-[9px]">
              <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
            </svg>
            <input ref={box} id="q" type="search" value={q} className="input"
                   onChange={(e) => setQ(e.target.value)}
                   placeholder="Search full text…" aria-label="Search gazettes" />
            <span className="kbd pointer-events-none absolute right-[8px] top-[8px] hidden sm:block">/</span>
          </div>
          <button className="btn" aria-pressed={rules} onClick={() => setRules(!rules)}
                  title="Collapse to one result per rule">
            {rules ? "By rule" : "By document"}
          </button>
          <button className="btn" aria-pressed={!!asOf}
                  onClick={() => setAsOf(asOf ? null : "2015-01-01")} title="Time travel">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" aria-hidden>
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
            </svg>
            <span className="hidden lg:inline">{asOf ? asOf : "As of today"}</span>
          </button>
        </div>

        {(asOf || chips.length > 0) && (
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-[6px]"
               style={{ borderColor: "var(--line)" }}>
            {asOf && (
              <>
                <span className="text-[11.5px]" style={{ color: "var(--sup)" }}>
                  as it stood on
                </span>
                <input type="date" value={asOf} aria-label="As-of date"
                       onChange={(e) => setAsOf(e.target.value || null)}
                       className="mono rounded-[5px] border px-[6px] py-[2px] text-[11.5px]"
                       style={{ borderColor: "var(--line)", background: "var(--bg)" }} />
                <span className="text-[11px]" style={{ color: "var(--faint)" }}>
                  effective date, not publication
                </span>
              </>
            )}
            {chips.map(([label, clear]) => (
              <button key={label} className="tag" onClick={clear} title="Remove filter">
                {label} <span style={{ color: "var(--faint)" }}>✕</span>
              </button>
            ))}
          </div>
        )}

        <div className="flex shrink-0 items-center gap-3 border-b px-3 py-[5px]"
             style={{ borderColor: "var(--line)" }}>
          <span className="mono text-[11px]" style={{ color: "var(--faint)" }}>
            {results.length} {rules ? "rule" : "document"}{results.length === 1 ? "" : "s"}
          </span>
          {pending && q && (
            <span className="text-[11px]" style={{ color: "var(--sup)" }}>
              indexing full text…
            </span>
          )}
          <span className="grow" />
          <span className="hidden items-center gap-1 text-[11px] lg:flex"
                style={{ color: "var(--faint)" }}>
            <span className="kbd">j</span><span className="kbd">k</span> to move
          </span>
        </div>

        <div className="min-h-0 grow overflow-y-auto">
          {results.length === 0 ? (
            <div className="px-4 py-16 text-center">
              <p className="text-[14px] font-medium">
                {q ? `Nothing matches “${q}”` : "Nothing matches these filters"}
              </p>
              <p className="mt-1 text-[12.5px]" style={{ color: "var(--dim)" }}>
                {pending ? "The full text is still loading."
                         : "Every word of every gazette is searched, and all terms must appear."}
              </p>
            </div>
          ) : (
            <>
              {results.slice(0, shown).map((g) => (
                <Row key={g.no} g={g} asOf={asOf} selected={g.no === selected}
                     onSelect={() => setSelected(g.no)} />
              ))}
              {results.length > shown && (
                <div className="p-3">
                  <button className="btn w-full justify-center"
                          onClick={() => setShown((s) => s + PAGE)}>
                    Show {Math.min(PAGE, results.length - shown)} more
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>

      {/* ── detail ───────────────────────────────────────────────────── */}
      <DetailPane g={active} corpus={corpus} byNo={byNo} asOf={asOf}
                  onClose={() => setSelected(null)} onOpen={(no) => setSelected(no)} />
    </div>
  );
}

function Row({ g, asOf, selected, onSelect }: {
  g: Gazette; asOf: string | null; selected: boolean; onSelect: () => void;
}) {
  const s = standingOf(g, asOf);
  return (
    <button className="rowitem" aria-selected={selected} onClick={onSelect}>
      <div className="flex items-center gap-2">
        <span className="mono shrink-0 text-[12px] font-semibold">{g.no}</span>
        <span className={`state state-${s.kind}`}>{s.pill}</span>
        <span className="grow" />
        <span className="mono shrink-0 text-[10.5px]" style={{ color: "var(--faint)" }}>
          {formatDate(g.published_date)}
        </span>
      </div>
      <p className="clamp-1 mt-[3px] text-[13px] font-medium">{g.title}</p>
      <div className="mt-[4px] flex items-center gap-[6px]">
        <span className="tag">{g.subject}</span>
        {g.thread_size > 1 && <span className="tag">{g.thread_size} in rule</span>}
        {g.missing_refs.length > 0 && (
          <span className="tag tag-warn" title="A gazette this rule references is not held">
            gap
          </span>
        )}
        {g.confidence && g.confidence !== "high" && (
          <span className="tag">{g.confidence} conf.</span>
        )}
        {g.source !== "ird-listing" && <span className="tag">recovered</span>}
        {s.consequence && (
          <span className="clamp-1 text-[11.5px]"
                style={{ color: s.kind === "rescinded" ? "var(--res)" : "var(--sup)" }}>
            {s.consequence}
          </span>
        )}
      </div>
    </button>
  );
}

function FacetGroup({ title, items, active, onPick, label, dot }: {
  title: string; items: [string, number][]; active: string | null;
  onPick: (k: string) => void;
  label?: Record<string, string>; dot?: Record<string, string>;
}) {
  return (
    <div className="mb-3">
      <p className="sec px-2 pb-1">{title}</p>
      {items.map(([k, n]) => (
        <button key={k} className="facet" aria-pressed={active === k} onClick={() => onPick(k)}>
          {dot?.[k]
            ? <span className="h-[6px] w-[6px] shrink-0 rounded-full" style={{ background: dot[k] }} />
            : <span className="h-[6px] w-[6px] shrink-0" />}
          <span className="grow truncate">{label?.[k] ?? k}</span>
          <span className="n">{n}</span>
        </button>
      ))}
    </div>
  );
}
