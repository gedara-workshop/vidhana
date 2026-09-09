import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Consequence, Mark } from "@/components/Standing";
import { allThreads, missingFrom, thread, threadMembers } from "@/lib/corpus";
import { formatDate, toSlug } from "@/lib/standing";

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
    <article className="mx-auto max-w-[820px] px-6 pb-10 pt-8 md:px-14">
      <Link className="label !opacity-100 underline underline-offset-4" href="/">
        ← Search the corpus
      </Link>

      <p className="label mt-6">
        {t.subject} · {t.size} documents · {t.first_date.slice(0, 4)}–{t.last_date.slice(0, 4)}
      </p>
      <h1 className="mt-2 max-w-[700px] text-[34px] leading-[1.18]">{head.title}</h1>

      <div className="mt-6 border-y py-5" style={{ borderColor: "var(--hair-strong)" }}>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
          <Mark g={head} />
          <span className="grow" />
          <span className="mono text-[12px] opacity-50">
            effective {formatDate(head.effective_from)}
          </span>
        </div>
        <p className="mt-3 flex flex-wrap items-baseline gap-x-3 text-[24px]">
          <Link className="mono font-semibold link" href={`/gazette/${toSlug(head.no)}/`}>
            {head.no}
          </Link>
          <span className="italic">is the rule today</span>
        </p>
        {head.summary && (
          <p className="mt-3 max-w-[660px] text-[16px] leading-[1.6] opacity-[.82]">
            {head.summary}
          </p>
        )}
        <p className="mt-4">
          <a className="text-[16px] font-semibold link" href={head.source_url} rel="noopener">
            Open the gazette PDF →
          </a>
        </p>
      </div>

      {missing.length > 0 && (
        <p className="mt-5 border-l-2 border-dashed py-1 pl-4 text-[14.5px] italic leading-relaxed"
           style={{ borderColor: "var(--hair-strong)" }}>
          <strong className="not-italic font-semibold">This rule’s history is incomplete.</strong>{" "}
          <span className="mono not-italic text-[13.5px]">{missing.join(", ")}</span>{" "}
          {missing.length > 1 ? "are" : "is"} referenced by a document we hold but missing from the
          IRD listing, so a change made by a gazette we do not hold would not appear below.
        </p>
      )}

      <h2 className="label mt-10">Every document in this rule</h2>
      <ol className="mt-2">
        {members.map((m) => (
          <li key={m.no}>
            <Link className="entry block py-[20px]" href={`/gazette/${toSlug(m.no)}/`}>
              <div className="flex items-baseline gap-[14px]">
                <span className="mono text-[15px] font-medium">{m.no}</span>
                <span className="mono text-[11.5px] opacity-50">
                  {formatDate(m.published_date)}
                </span>
                <span className="grow" />
                <Mark g={m} />
              </div>
              <p className="mt-[7px] max-w-[640px] text-[20px] leading-[1.32]">{m.title}</p>
              <Consequence g={m} />
              {m.summary && (
                <p className="clamp-2 mt-2 max-w-[640px] text-[14.5px] opacity-[.62]">
                  {m.summary}
                </p>
              )}
            </Link>
          </li>
        ))}
      </ol>
    </article>
  );
}
