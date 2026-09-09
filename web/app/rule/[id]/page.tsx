import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { GapChip, StandingPill, WarnIcon } from "@/components/Standing";
import { allThreads, missingFrom, thread, threadMembers } from "@/lib/corpus";
import { formatDate, standingOf, toSlug } from "@/lib/standing";

/* One static page per rule. The answer a reader wants usually exists in no
 * single gazette, so this is the page that states it: the current document
 * first, the history that produced it below. */

export const dynamicParams = false;

export function generateStaticParams() {
  return allThreads().map((t) => ({ id: String(t.thread_id) }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ id: string }> },
): Promise<Metadata> {
  const { id } = await params;
  const t = thread(Number(id));
  if (!t) return { title: "Not found" };
  const members = threadMembers(t.thread_id);
  const head = members.find((m) => m.no === t.head_no);
  return {
    title: `${head?.title ?? t.subject} — the rule now`,
    description:
      `${t.size} gazettes between ${t.first_date.slice(0, 4)} and ${t.last_date.slice(0, 4)} define this rule. ` +
      `${t.head_no} is the current document. ${head?.summary ?? ""}`.slice(0, 300),
    alternates: { canonical: `/vidhana/rule/${id}/` },
  };
}

export default async function RulePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = thread(Number(id));
  if (!t) notFound();

  const members = threadMembers(t.thread_id);
  const head = members.find((m) => m.no === t.head_no);
  const missing = missingFrom(members);
  if (!head) notFound();

  return (
    <main className="mx-auto max-w-4xl px-6 py-8">
      <Link className="btn mb-4" href="/">← Search the corpus</Link>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="chip">{t.subject}</span>
        <span className="chip">{t.size} documents</span>
        <span className="chip">
          {t.first_date.slice(0, 4)} – {t.last_date.slice(0, 4)}
        </span>
        <GapChip missing={missing} />
      </div>

      <h1 className="text-[30px] font-bold leading-[1.15] tracking-tight">{head.title}</h1>

      <div className="card mt-5 rounded-[10px] p-6"
           style={{ borderLeftWidth: 4, borderLeftColor: "var(--ok)" }}>
        <div className="flex flex-wrap items-center gap-3">
          <StandingPill g={head} />
          <span className="grow" />
          <span className="font-mono text-[11.5px]" style={{ color: "var(--dim)" }}>
            effective {formatDate(head.effective_from)}
          </span>
        </div>
        <p className="mt-3 flex flex-wrap items-baseline gap-3">
          <Link className="font-mono text-[22px] font-semibold link" href={`/gazette/${toSlug(head.no)}/`}>
            {head.no}
          </Link>
          <span className="text-[17px] font-semibold">is the rule today</span>
        </p>
        {head.summary && (
          <p className="mt-2 max-w-[700px] text-[14.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
            {head.summary}
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-3">
          <a className="btn-primary" href={head.source_url} rel="noopener">Open the gazette PDF →</a>
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

      <h2 className="kicker mt-8 mb-3">Every document in this rule</h2>
      <ol className="flex flex-col gap-3">
        {members.map((m) => {
          const s = standingOf(m);
          return (
            <li key={m.no}>
              <Link className="card block rounded-[10px] p-4" href={`/gazette/${toSlug(m.no)}/`}>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-[13.5px] font-semibold">{m.no}</span>
                  {m.source !== "ird-listing" && <span className="chip">recovered</span>}
                  <span className="grow" />
                  <StandingPill g={m} />
                </div>
                <p className="mt-2 text-[15px] font-semibold leading-snug">{m.title}</p>
                <p className="mt-[11px] font-mono text-[11.5px]" style={{ color: "var(--dim)" }}>
                  {formatDate(m.published_date)}
                </p>
              </Link>
            </li>
          );
        })}
      </ol>
    </main>
  );
}
