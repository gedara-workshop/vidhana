import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

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
    <div className="h-full overflow-y-auto">
      <article className="mx-auto max-w-3xl px-5 py-6">
        <Link className="navlink -ml-[10px]" href="/rules/">← All rules</Link>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="tag">{t.subject}</span>
          <span className="tag">{t.size} documents</span>
          <span className="tag">{t.first_date.slice(0, 4)}–{t.last_date.slice(0, 4)}</span>
          {missing.length > 0 && <span className="tag tag-warn">history incomplete</span>}
        </div>

        <h1 className="mt-2 text-[24px] font-bold leading-snug tracking-tight">{head.title}</h1>

        <div className="mt-4 rounded-[8px] border p-4"
             style={{ borderColor: "var(--line)", background: "var(--panel)" }}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="state state-current">In force · current</span>
            <span className="grow" />
            <span className="mono text-[11px]" style={{ color: "var(--faint)" }}>
              effective {formatDate(head.effective_from)}
            </span>
          </div>
          <p className="mt-3 flex flex-wrap items-baseline gap-2">
            <Link className="mono text-[19px] font-bold link" href={`/gazette/${toSlug(head.no)}/`}>
              {head.no}
            </Link>
            <span className="text-[15px] font-medium">is the rule today</span>
          </p>
          {head.summary && (
            <p className="mt-2 text-[13.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
              {head.summary}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <a className="btn btn-primary" href={head.source_url} rel="noopener">
              Open the gazette PDF
            </a>
            <Link className="btn" href={`/gazette/${toSlug(head.no)}/`}>Document page</Link>
          </div>
        </div>

        {missing.length > 0 && (
          <p className="mt-3 rounded-[8px] px-4 py-3 text-[12.5px] leading-relaxed"
             style={{ background: "var(--sup-bg)", color: "var(--sup)" }}>
            <strong>This rule’s history is incomplete.</strong>{" "}
            <span className="mono">{missing.join(", ")}</span>{" "}
            {missing.length > 1 ? "are" : "is"} referenced by a document we hold but missing from
            the IRD listing, so a change made by a gazette we do not hold would not appear below.
          </p>
        )}

        <p className="sec mt-6 mb-2">Every document in this rule</p>
        <div className="overflow-hidden rounded-[8px] border" style={{ borderColor: "var(--line)" }}>
          {members.map((m) => {
            const ms = standingOf(m);
            return (
              <Link key={m.no} href={`/gazette/${toSlug(m.no)}/`}
                    className="block border-b px-4 py-3 last:border-0 hover:bg-[var(--raised)]"
                    style={{ borderColor: "var(--line-soft)" }}>
                <span className="flex flex-wrap items-center gap-2">
                  <span className="mono text-[12px] font-semibold">{m.no}</span>
                  <span className={`state state-${ms.kind}`}>{ms.pill}</span>
                  {m.source !== "ird-listing" && <span className="tag">recovered</span>}
                  <span className="grow" />
                  <span className="mono text-[10.5px]" style={{ color: "var(--faint)" }}>
                    {formatDate(m.published_date)}
                  </span>
                </span>
                <span className="mt-[3px] block text-[13px] font-medium">{m.title}</span>
                {ms.consequence && (
                  <span className="mt-[2px] block text-[11.5px]"
                        style={{ color: ms.kind === "rescinded" ? "var(--res)" : "var(--sup)" }}>
                    {ms.consequence}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      </article>
    </div>
  );
}
