import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Consequence, GapChip, StandingPill, WarnIcon } from "@/components/Standing";
import { allGazettes, gazette, missingFrom, thread, threadMembers } from "@/lib/corpus";
import { formatDate, fromSlug, standingOf, toSlug } from "@/lib/standing";

/* One static page per gazette. This is the reason for the framework: 144 pages
 * a crawler can read, where a single-page app offered none. Someone searching
 * for a tax invoice format should land here and learn, without ever having
 * heard of this site, that the document they found was superseded. */

export const dynamicParams = false;

export function generateStaticParams() {
  return allGazettes().map((g) => ({ slug: toSlug(g.no) }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const g = gazette(fromSlug(slug));
  if (!g) return { title: "Not found" };
  const s = standingOf(g);
  // The description leads with standing, because that is what a searcher needs
  // from the snippet before they decide whether to click.
  const lead = s.consequence ? `${s.pill}. ${s.consequence}.` : `${s.pill}.`;
  return {
    title: `${g.no} — ${g.title}`,
    description: `${lead} ${g.summary ?? ""}`.trim().slice(0, 300),
    alternates: { canonical: `/vidhana/gazette/${slug}/` },
  };
}

export default async function GazettePage(
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const g = gazette(fromSlug(slug));
  if (!g) notFound();

  const members = g.thread_id ? threadMembers(g.thread_id) : [g];
  const t = g.thread_id ? thread(g.thread_id) : undefined;
  const missing = missingFrom(members);
  const head = t ? members.find((m) => m.no === t.head_no) : undefined;
  const s = standingOf(g);

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Link className="btn mb-4" href="/">← Search the corpus</Link>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="chip">{g.subject}</span>
        {t ? <span className="chip">{t.size} documents in this rule</span>
           : <span className="chip">standalone</span>}
        {g.source !== "ird-listing" && (
          <span className="chip" title="Not in the IRD listing; recovered from the Internet Archive">
            recovered
          </span>
        )}
        <GapChip missing={missing} />
      </div>

      <div className="card rounded-[10px] p-6" style={{ borderLeftWidth: 4, borderLeftColor: `var(--${s.kind === "rescinded" ? "res" : s.kind === "superseded" ? "sup" : "ok"})` }}>
        <div className="flex flex-wrap items-center gap-3">
          <StandingPill g={g} />
          <span className="grow" />
          <span className="font-mono text-[11.5px]" style={{ color: "var(--dim)" }}>
            published {formatDate(g.published_date)}
            {g.effective_from && g.effective_from !== g.published_date &&
              ` · effective ${formatDate(g.effective_from)}`}
          </span>
        </div>
        <h1 className="mt-3 text-[24px] font-semibold leading-tight tracking-tight">
          <span className="font-mono">{g.no}</span> — {g.title}
        </h1>
        <Consequence g={g} />
        {g.summary && (
          <p className="mt-3 max-w-[700px] text-[14.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
            {g.summary}
          </p>
        )}
        {g.confidence && g.confidence !== "high" && (
          <p className="mt-2 text-[11.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
            This summary was generated with {g.confidence} confidence. Read the gazette before relying on it.
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-3">
          <a className="btn-primary" href={g.source_url} rel="noopener">Open the gazette PDF →</a>
          {head && head.no !== g.no && (
            <Link className="btn" href={`/gazette/${toSlug(head.no)}/`}>
              Go to {head.no}, the current document →
            </Link>
          )}
        </div>
      </div>

      {missing.length > 0 && (
        <div className="mt-3 flex items-start gap-3 rounded-[9px] p-4 text-[13px] leading-relaxed"
             style={{ background: "var(--sup-soft)", color: "var(--sup)" }}>
          <WarnIcon size={16} />
          <p>
            <strong>This rule’s history is incomplete.</strong>{" "}
            <span className="font-mono">{missing.join(", ")}</span>{" "}
            {missing.length > 1 ? "are" : "is"} referenced by a document we hold but missing from the
            IRD listing, so a change made by a gazette we do not hold would not appear below.
          </p>
        </div>
      )}

      {t && (
        <>
          <h2 className="kicker mt-8 mb-3">How this rule got here</h2>
          <ol className="panel rounded-[10px] px-5">
            {members.map((m, i) => {
              const ms = standingOf(m);
              return (
                <li key={m.no} className="flex gap-4"
                    style={{ borderTop: i === 0 ? "none" : "1px solid var(--line)" }}>
                  <div className="flex w-[18px] shrink-0 flex-col items-center">
                    <span className="w-[2px] grow" style={{ background: i === 0 ? "transparent" : "var(--line)" }} />
                    <span className="my-0 h-[11px] w-[11px] shrink-0 rounded-full"
                          style={{
                            background: m.no === t.head_no ? "var(--ok)" : "var(--dim)",
                            boxShadow: m.no === t.head_no
                              ? "0 0 0 3px var(--surface), 0 0 0 5px var(--ok)" : undefined,
                          }} />
                    <span className="w-[2px] grow"
                          style={{ background: i === members.length - 1 ? "transparent" : "var(--line)" }} />
                  </div>
                  <div className="min-w-0 grow py-4">
                    <div className="flex flex-wrap items-center gap-3">
                      <Link className="font-mono text-[13.5px] font-medium link" href={`/gazette/${toSlug(m.no)}/`}>
                        {m.no}
                      </Link>
                      <span className="font-mono text-[11.5px]" style={{ color: "var(--dim)" }}>
                        {formatDate(m.published_date)}
                      </span>
                      <span className={`pill pill-${ms.kind}`}>
                        <span className="pill-dot" aria-hidden />{ms.pill}
                      </span>
                      {m.no === g.no && <span className="chip">you are here</span>}
                    </div>
                    <p className="mt-1 text-[13.5px]" style={{ color: "var(--dim)" }}>{m.title}</p>
                  </div>
                </li>
              );
            })}
          </ol>
          <p className="mt-3">
            <Link className="link text-[13px] font-medium" href={`/rule/${t.thread_id}/`}>
              See this rule on its own page →
            </Link>
          </p>
        </>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="panel rounded-[10px] p-4">
          <h2 className="kicker">Who this affects</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {g.audience.length
              ? g.audience.map((a) => <span key={a} className="chip">{a}</span>)
              : <span className="chip">not stated</span>}
          </div>
          <p className="mt-3 text-[11.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
            Inferred from the enabling Act — gazettes rarely state who they bind, and the model may
            only narrow within the Act’s known audiences.
          </p>
        </div>
        <div className="panel rounded-[10px] p-4">
          <h2 className="kicker">Enabling Act</h2>
          <p className="mt-3 text-[14px] font-medium">{g.enabling_act ?? "not parsed"}</p>
          {g.source !== "ird-listing" && (
            <p className="mt-3 text-[11.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
              Recovered from the Internet Archive — this gazette is not in the IRD listing.
              <br />
              <span className="font-mono">{g.source_detail}</span>
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
